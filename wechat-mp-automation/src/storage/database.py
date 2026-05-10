"""
SQLite 数据库管理
- 自动建表
- 异步操作
- 单例模式
"""

import aiosqlite
from loguru import logger
from pathlib import Path
from typing import Any


# 建表 SQL（与 SPEC.md 对齐）
SCHEMA_SQL = """
-- 原始内容
CREATE TABLE IF NOT EXISTS contents (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    url TEXT UNIQUE,
    title TEXT NOT NULL,
    content TEXT,
    summary TEXT,
    author TEXT,
    published_at DATETIME,
    metadata JSON,
    status TEXT DEFAULT 'collected',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 改写结果
CREATE TABLE IF NOT EXISTS rewrites (
    id TEXT PRIMARY KEY,
    content_id TEXT REFERENCES contents(id),
    strategy TEXT NOT NULL,
    style TEXT,
    title TEXT,
    content TEXT NOT NULL,
    word_count INTEGER,
    quality_score JSON,
    model TEXT,
    tokens_used INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 格式化结果
CREATE TABLE IF NOT EXISTS formatted (
    id TEXT PRIMARY KEY,
    rewrite_id TEXT REFERENCES rewrites(id),
    format TEXT NOT NULL,
    html TEXT,
    cover_image TEXT,
    images JSON,
    exports JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 发布记录
CREATE TABLE IF NOT EXISTS published (
    id TEXT PRIMARY KEY,
    formatted_id TEXT REFERENCES formatted(id),
    account_id TEXT NOT NULL,
    media_id TEXT,
    status TEXT DEFAULT 'draft',
    publish_time DATETIME,
    article_url TEXT,
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 执行日志
CREATE TABLE IF NOT EXISTS execution_log (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    input_count INTEGER,
    output_count INTEGER,
    error TEXT,
    duration_seconds REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_contents_status ON contents(status);
CREATE INDEX IF NOT EXISTS idx_contents_source_id ON contents(source_id);
CREATE INDEX IF NOT EXISTS idx_rewrites_content_id ON rewrites(content_id);
CREATE INDEX IF NOT EXISTS idx_formatted_rewrite_id ON formatted(rewrite_id);
CREATE INDEX IF NOT EXISTS idx_published_formatted_id ON published(formatted_id);
CREATE INDEX IF NOT EXISTS idx_execution_log_batch_id ON execution_log(batch_id);
"""


class Database:
    """SQLite 异步数据库"""

    def __init__(self, db_path: str = "./data/content.db"):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        """连接数据库并初始化表结构"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()
        logger.info(f"Database connected: {self.db_path}")

    async def close(self):
        """关闭连接"""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("Database closed")

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """执行SQL"""
        if not self._conn:
            raise RuntimeError("Database not connected")
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor

    async def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """批量执行SQL"""
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.executemany(sql, params_list)
        await self._conn.commit()

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """查询单条"""
        if not self._conn:
            raise RuntimeError("Database not connected")
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """查询多条"""
        if not self._conn:
            raise RuntimeError("Database not connected")
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ==================== 业务方法 ====================

    async def insert_content(self, data: dict) -> str:
        """插入原始内容，返回id。重复URL则跳过。"""
        content_id = data["id"]
        # 检查URL是否已存在
        if data.get("url"):
            existing = await self.fetch_one(
                "SELECT id FROM contents WHERE url = ?", (data["url"],)
            )
            if existing:
                logger.debug(f"Content already exists (URL dedup): {data['url']}")
                return existing["id"]

        import json
        await self.execute(
            """INSERT OR IGNORE INTO contents 
            (id, source_id, source_type, url, title, content, summary, author, published_at, metadata, status)
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
        """按状态查询内容"""
        return await self.fetch_all(
            "SELECT * FROM contents WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        )

    async def update_content_status(self, content_id: str, status: str):
        """更新内容状态"""
        await self.execute(
            "UPDATE contents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, content_id),
        )

    async def insert_rewrite(self, data: dict) -> str:
        """插入改写结果"""
        import json
        rewrite_id = data["id"]
        await self.execute(
            """INSERT INTO rewrites 
            (id, content_id, strategy, style, title, content, word_count, quality_score, model, tokens_used)
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

    async def insert_formatted(self, data: dict) -> str:
        """插入格式化结果"""
        import json
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

    async def insert_published(self, data: dict) -> str:
        """插入发布记录"""
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
        """更新发布记录"""
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

    async def insert_execution_log(self, data: dict):
        """插入执行日志"""
        import json
        await self.execute(
            """INSERT INTO execution_log 
            (id, batch_id, step, status, input_count, output_count, error, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["id"],
                data["batch_id"],
                data["step"],
                data["status"],
                data.get("input_count", 0),
                data.get("output_count", 0),
                data.get("error"),
                data.get("duration_seconds", 0.0),
            ),
        )

    async def get_rewrite_for_content(self, content_id: str) -> dict | None:
        """获取某内容的最新改写"""
        return await self.fetch_one(
            "SELECT * FROM rewrites WHERE content_id = ? ORDER BY created_at DESC LIMIT 1",
            (content_id,),
        )

    async def get_formatted_for_rewrite(self, rewrite_id: str) -> dict | None:
        """获取某改写的最新格式化"""
        return await self.fetch_one(
            "SELECT * FROM formatted WHERE rewrite_id = ? ORDER BY created_at DESC LIMIT 1",
            (rewrite_id,),
        )


# 单例
_db_instance: Database | None = None


async def get_database(db_path: str = "./data/content.db") -> Database:
    """获取数据库单例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
        await _db_instance.connect()
    return _db_instance
