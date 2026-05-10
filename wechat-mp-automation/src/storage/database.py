"""
SQLite 数据库管理模块
=====================

本模块负责微信公众号自动化系统的数据持久化，是整个系统的"记忆中枢"。

核心职责：
1. 存储采集的原始内容（contents 表）
2. 存储改写结果（rewrites 表）
3. 存储格式化输出（formatted 表）
4. 存储发布记录（published 表）
5. 记录工作流执行日志（execution_log 表）

设计决策：
- 使用 SQLite 而非 PostgreSQL/MySQL：MVP 阶段无需分布式，SQLite 零部署，单文件便于迁移
- 使用 aiosqlite 而非 sqlite3：整个系统是异步架构，数据库也必须异步
- 单例模式：避免多个连接导致"database is locked"错误

数据流：
内容采集 → contents(status='collected')
    ↓
改写处理 → contents(status='processing') → rewrites
    ↓
格式化 → formatted
    ↓
发布 → published(status='draft'/'published')

使用示例：
    db = await get_database("./data/content.db")
    content_id = await db.insert_content({...})
    contents = await db.get_contents_by_status("collected")
"""

import aiosqlite
from loguru import logger
from pathlib import Path
from typing import Any
import json
import uuid


# ============================================================================
# 数据库表结构定义
# ============================================================================

SCHEMA_SQL = """
-- ============================================================
-- contents 表：存储从各数据源采集的原始内容
-- ============================================================
-- 数据流：采集 → contents → 改写 → rewrites
-- 状态机：collected → processing → processed
-- 去重机制：url 字段 UNIQUE 约束，插入前检查
-- ============================================================
CREATE TABLE IF NOT EXISTS contents (
    id TEXT PRIMARY KEY,              -- UUID，全局唯一
    source_id TEXT NOT NULL,          -- 数据源ID，关联 config/sources/*.yaml
    source_type TEXT NOT NULL,        -- 数据源类型：rss/wechat/zhihu/youtube等
    url TEXT UNIQUE,                  -- 原文链接，用于去重（UNIQUE约束）
    title TEXT NOT NULL,              -- 文章标题
    content TEXT,                     -- 正文内容（HTML或纯文本）
    summary TEXT,                     -- 摘要（由数据源提供或自动生成）
    author TEXT,                      -- 作者名称
    published_at DATETIME,            -- 发布时间（原文发布时间，非入库时间）
    metadata JSON,                    -- 扩展字段：阅读量、点赞数、标签等
    status TEXT DEFAULT 'collected',  -- 状态：collected/processing/processed
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,  -- 入库时间
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP   -- 最后更新时间
);

-- ============================================================
-- rewrites 表：存储改写结果
-- ============================================================
-- 一个 content 可以有多个 rewrite（不同策略、不同风格）
-- 通过 content_id 关联原始内容
-- ============================================================
CREATE TABLE IF NOT EXISTS rewrites (
    id TEXT PRIMARY KEY,              -- UUID
    content_id TEXT REFERENCES contents(id),  -- 关联原始内容
    strategy TEXT NOT NULL,           -- 改写策略：summarize/style_transfer/paraphrase/rewrite/expand
    style TEXT,                       -- 改写风格：professional/casual/humorous等
    title TEXT,                       -- 改写后的标题（可能重新起标题）
    content TEXT NOT NULL,            -- 改写后的正文（Markdown格式）
    word_count INTEGER,               -- 字数统计（用于质量检查）
    quality_score JSON,               -- 质量评分：{readability: 0.8, originality: 0.7}
    model TEXT,                       -- 使用的LLM模型：gpt-4o/claude-3-sonnet等
    tokens_used INTEGER,              -- 消耗的token数（用于成本核算）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- formatted 表：存储格式化后的发布稿
-- ============================================================
-- 将 Markdown 转换为公众号 HTML
-- 记录封面图、文章内图、导出文件路径
-- ============================================================
CREATE TABLE IF NOT EXISTS formatted (
    id TEXT PRIMARY KEY,
    rewrite_id TEXT REFERENCES rewrites(id),  -- 关联改写结果
    format TEXT NOT NULL,             -- 格式类型：wechat_mp/xiaohongshu/douyin等
    html TEXT,                        -- 格式化后的HTML（公众号专用）
    cover_image TEXT,                 -- 封面图路径
    images JSON,                      -- 文章内图片列表：[{path, position, url}]
    exports JSON,                     -- 导出文件路径：{markdown: "path/to/file.md"}
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- published 表：存储发布记录
-- ============================================================
-- 记录发布到公众号的结果
-- 支持草稿箱模式和直接发布模式
-- ============================================================
CREATE TABLE IF NOT EXISTS published (
    id TEXT PRIMARY KEY,
    formatted_id TEXT REFERENCES formatted(id),  -- 关联格式化结果
    account_id TEXT NOT NULL,         -- 公众号账号ID（支持多账号）
    media_id TEXT,                    -- 微信返回的media_id（用于修改草稿）
    status TEXT DEFAULT 'draft',      -- 状态：draft/published/deleted/failed
    publish_time DATETIME,            -- 发布时间（实际发布成功的时间）
    article_url TEXT,                 -- 发布后的文章链接
    error TEXT,                       -- 错误信息（发布失败时记录）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- execution_log 表：记录工作流执行日志
-- ============================================================
-- 用于追踪每次执行的详细信息
-- 支持错误恢复：查询最近一次失败的位置，从那里继续
-- ============================================================
CREATE TABLE IF NOT EXISTS execution_log (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,           -- 批次ID（格式：YYYYMMDD_HHMMSS）
    step TEXT NOT NULL,               -- 步骤名称：collect/rewrite/format/publish
    status TEXT NOT NULL,             -- 状态：started/completed/failed
    input_count INTEGER,              -- 输入数量（采集了多少篇/改写了多少篇）
    output_count INTEGER,             -- 输出数量（成功了多少篇）
    error TEXT,                       -- 错误信息
    duration_seconds REAL,            -- 执行耗时（秒）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 索引：优化高频查询
-- ============================================================
-- contents.status：按状态查询待处理内容
-- contents.source_id：按数据源查询
-- rewrites.content_id：查询某内容的所有改写版本
-- formatted.rewrite_id：查询某改写的格式化结果
-- published.formatted_id：查询某格式化结果的发布状态
-- execution_log.batch_id：查询某次执行的所有步骤日志
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_contents_status ON contents(status);
CREATE INDEX IF NOT EXISTS idx_contents_source_id ON contents(source_id);
CREATE INDEX IF NOT EXISTS idx_rewrites_content_id ON rewrites(content_id);
CREATE INDEX IF NOT EXISTS idx_formatted_rewrite_id ON formatted(rewrite_id);
CREATE INDEX IF NOT EXISTS idx_published_formatted_id ON published(formatted_id);
CREATE INDEX IF NOT EXISTS idx_execution_log_batch_id ON execution_log(batch_id);
"""


class Database:
    """
    SQLite 异步数据库管理类
    
    使用方式：
        db = Database("./data/content.db")
        await db.connect()
        
        # 插入内容
        content_id = await db.insert_content({
            "id": str(uuid.uuid4()),
            "source_id": "tech-rss",
            "source_type": "rss",
            "url": "https://example.com/article",
            "title": "文章标题",
            "content": "正文...",
        })
        
        # 查询待处理内容
        contents = await db.get_contents_by_status("collected")
        
        # 更新状态
        await db.update_content_status(content_id, "processing")
        
        await db.close()
    
    设计说明：
    - 所有方法都是异步的，适配整个系统的异步架构
    - 使用 aiosqlite.Row 作为 row_factory，返回字典而非元组
    - insert 方法会自动处理 JSON 序列化
    - 不使用 ORM，直接写 SQL，便于调试和优化
    """
    
    def __init__(self, db_path: str = "./data/content.db"):
        """
        初始化数据库实例
        
        参数：
            db_path: 数据库文件路径，相对或绝对路径均可
        
        注意：
            构造函数不会立即连接，需要显式调用 connect()
            这样设计是为了支持依赖注入和测试 mock
        """
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
    
    async def connect(self):
        """
        连接数据库并初始化表结构
        
        执行流程：
        1. 创建数据目录（如果不存在）
        2. 打开数据库连接
        3. 设置 row_factory 为 Row（返回字典）
        4. 执行建表 SQL（幂等，表已存在则跳过）
        5. 提交事务
        
        注意：
            每次连接都会执行 SCHEMA_SQL，这是故意的——
            便于开发阶段修改表结构后重新启动程序
        """
        # 确保数据目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 打开连接
        self._conn = await aiosqlite.connect(self.db_path)
        
        # 设置返回字典而非元组
        self._conn.row_factory = aiosqlite.Row
        
        # 执行建表 SQL
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()
        
        logger.info(f"Database connected: {self.db_path}")
    
    async def close(self):
        """
        关闭数据库连接
        
        建议在程序退出前调用，避免数据丢失
        """
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("Database closed")
    
    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """
        执行单条 SQL（INSERT/UPDATE/DELETE）
        
        参数：
            sql: SQL 语句
            params: 参数元组
        
        返回：
            Cursor 对象，可获取 lastrowrowid 等
        
        注意：
            执行后会自动 commit，无需手动提交
        """
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor
    
    async def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """
        批量执行 SQL
        
        参数：
            sql: SQL 语句（使用 ? 占位符）
            params_list: 参数列表
        
        用例：
            await db.execute_many(
                "INSERT INTO contents (id, title) VALUES (?, ?)",
                [(id1, title1), (id2, title2)]
            )
        """
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        await self._conn.executemany(sql, params_list)
        await self._conn.commit()
    
    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """
        查询单条记录
        
        返回：
            字典（列名→值）或 None（无结果）
        """
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """
        查询多条记录
        
        返回：
            字典列表
        """
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    
    # ========================================================================
    # 业务方法：内容管理
    # ========================================================================
    
    async def insert_content(self, data: dict) -> str:
        """
        插入原始内容
        
        参数：
            data: 内容字典，必须包含 id、source_id、source_type、title
        
        返回：
            内容 ID（已存在则返回已存在的 ID）
        
        去重机制：
            1. 先查询 URL 是否已存在
            2. 存在则跳过插入，返回已有 ID
            3. 不存在则插入新记录
        
        这样设计的原因：
            - INSERT OR IGNORE 无法返回已存在的 ID
            - 需要知道 ID 才能继续后续处理
        """
        content_id = data["id"]
        
        # 去重检查：URL 是否已存在
        if data.get("url"):
            existing = await self.fetch_one(
                "SELECT id FROM contents WHERE url = ?",
                (data["url"],)
            )
            if existing:
                logger.debug(f"Content already exists (URL dedup): {data['url']}")
                return existing["id"]
        
        # 插入新记录
        await self.execute(
            """INSERT OR IGNORE INTO contents 
            (id, source_id, source_type, url, title, content, summary, 
             author, published_at, metadata, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                content_id,
                data["source_id"],
                data["source_type"],
                data.get("url"),
                data["title"],
                data.get("content", ""),
                data.get("summary", ""),
                data.get("author", ""),
                data.get("published_at"),
                json.dumps(data.get("metadata", {}), ensure_ascii=False),
                data.get("status", "collected"),
            ),
        )
        return content_id
    
    async def get_contents_by_status(self, status: str, limit: int = 100) -> list[dict]:
        """
        按状态查询内容
        
        参数：
            status: 状态值（collected/processing/processed）
            limit: 最大返回数量
        
        返回：
            内容字典列表，按创建时间倒序
        """
        return await self.fetch_all(
            "SELECT * FROM contents WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        )
    
    async def update_content_status(self, content_id: str, status: str):
        """
        更新内容状态
        
        状态转换：
            collected → processing：开始改写
            processing → processed：改写完成
            processing → collected：改写失败，重新入队
        """
        await self.execute(
            "UPDATE contents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, content_id),
        )
    
    # ========================================================================
    # 业务方法：改写管理
    # ========================================================================
    
    async def insert_rewrite(self, data: dict) -> str:
        """
        插入改写结果
        
        参数：
            data: 改写结果字典，必须包含 id、content_id、strategy、content
        
        副作用：
            自动将关联的 content 状态更新为 'processed'
        
        设计说明：
            一个 content 可以有多个 rewrite（不同策略、不同风格）
            每个 rewrite 是独立记录，便于对比效果
        """
        rewrite_id = data["id"]
        await self.execute(
            """INSERT INTO rewrites 
            (id, content_id, strategy, style, title, content, word_count, 
             quality_score, model, tokens_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rewrite_id,
                data["content_id"],
                data["strategy"],
                data.get("style"),
                data["title"],
                data["content"],
                data.get("word_count", 0),
                json.dumps(data.get("quality_score", {}), ensure_ascii=False),
                data.get("model", ""),
                data.get("tokens_used", 0),
            ),
        )
        # 更新原始内容状态
        await self.update_content_status(data["content_id"], "processed")
        return rewrite_id
    
    async def get_rewrite_for_content(self, content_id: str) -> dict | None:
        """
        获取某内容的最新改写版本
        
        如果存在多个改写版本，返回最新的一个
        """
        return await self.fetch_one(
            "SELECT * FROM rewrites WHERE content_id = ? ORDER BY created_at DESC LIMIT 1",
            (content_id,),
        )
    
    # ========================================================================
    # 业务方法：格式化管理
    # ========================================================================
    
    async def insert_formatted(self, data: dict) -> str:
        """
        插入格式化结果
        
        参数：
            data: 格式化结果字典
                - id: UUID
                - rewrite_id: 关联的改写记录
                - format: 格式类型（wechat_mp）
                - html: 转换后的 HTML
                - cover_image: 封面图路径（可选）
                - images: 文章内图片列表（可选）
                - exports: 导出文件路径（可选）
        """
        formatted_id = data["id"]
        await self.execute(
            """INSERT INTO formatted 
            (id, rewrite_id, format, html, cover_image, images, exports)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                formatted_id,
                data["rewrite_id"],
                data["format"],
                data.get("html", ""),
                data.get("cover_image"),
                json.dumps(data.get("images", []), ensure_ascii=False),
                json.dumps(data.get("exports", {}), ensure_ascii=False),
            ),
        )
        return formatted_id
    
    async def get_formatted_for_rewrite(self, rewrite_id: str) -> dict | None:
        """
        获取某改写的最新格式化结果
        """
        return await self.fetch_one(
            "SELECT * FROM formatted WHERE rewrite_id = ? ORDER BY created_at DESC LIMIT 1",
            (rewrite_id,),
        )
    
    # ========================================================================
    # 业务方法：发布管理
    # ========================================================================
    
    async def insert_published(self, data: dict) -> str:
        """
        插入发布记录
        
        参数：
            data: 发布记录字典
                - id: UUID
                - formatted_id: 关联的格式化记录
                - account_id: 公众号账号ID
                - media_id: 微信返回的 media_id（用于修改草稿）
                - status: 状态（draft/published/failed）
        
        状态说明：
            draft: 已创建草稿，待人工审核
            published: 已发布成功
            deleted: 草稿已删除
            failed: 发布失败
        """
        pub_id = data["id"]
        await self.execute(
            """INSERT INTO published 
            (id, formatted_id, account_id, media_id, status, publish_time, article_url, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pub_id,
                data["formatted_id"],
                data["account_id"],
                data.get("media_id"),
                data.get("status", "draft"),
                data.get("publish_time"),
                data.get("article_url"),
                data.get("error"),
            ),
        )
        return pub_id
    
    async def update_published(self, pub_id: str, data: dict):
        """
        更新发布记录
        
        用于更新发布状态、media_id、错误信息等
        """
        sets = []
        values = []
        for key in ["media_id", "status", "publish_time", "article_url", "error"]:
            if key in data:
                sets.append(f"{key} = ?")
                values.append(data[key])
        if sets:
            values.append(pub_id)
            await self.execute(
                f"UPDATE published SET {', '.join(sets)} WHERE id = ?",
                tuple(values),
            )
    
    # ========================================================================
    # 业务方法：执行日志
    # ========================================================================
    
    async def insert_execution_log(self, data: dict):
        """
        插入执行日志
        
        参数：
            data: 日志字典
                - id: UUID
                - batch_id: 批次ID（格式：YYYYMMDD_HHMMSS）
                - step: 步骤名称（collect/rewrite/format/publish）
                - status: 状态（started/completed/failed）
                - input_count: 输入数量
                - output_count: 输出数量
                - error: 错误信息
                - duration_seconds: 执行耗时
        
        用途：
            1. 监控每次执行的效率
            2. 错误恢复：查询最近一次失败的位置
            3. 数据分析：统计各步骤的平均耗时
        """
        await self.execute(
            """INSERT INTO execution_log 
            (id, batch_id, step, status, input_count, output_count, error, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                data["batch_id"],
                data["step"],
                data["status"],
                data.get("input_count", 0),
                data.get("output_count", 0),
                data.get("error"),
                data.get("duration_seconds", 0.0),
            ),
        )


# ============================================================================
# 单例模式
# ============================================================================

_db_instance: Database | None = None


async def get_database(db_path: str = "./data/content.db") -> Database:
    """
    获取数据库单例
    
    为什么用单例：
        SQLite 默认只允许一个写连接，多连接会导致 "database is locked" 错误
        单例确保整个进程只有一个连接
    
    参数：
        db_path: 数据库文件路径
    
    返回：
        已连接的 Database 实例
    
    使用示例：
        db = await get_database()
        contents = await db.get_contents_by_status("collected")
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
        await _db_instance.connect()
    return _db_instance
