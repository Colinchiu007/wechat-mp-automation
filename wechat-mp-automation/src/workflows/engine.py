"""
工作流引擎——模块E的核心
========================

本模块是整个自动化系统的"大脑"，负责协调各模块按顺序执行。

核心设计：
- 串行执行：collect → rewrite → format → publish（MVP阶段）
- 幂等性：同一内容重复执行不会产生重复记录
- 错误恢复：失败的内容状态回退，下次执行时自动重试
- 可观测性：每步执行都写入 execution_log 表

工作流状态机：
```
新内容 → [collect] → collected
                         ↓
                     [rewrite] → processing → processed
                         ↓                           ↓
                     [format]                    （跳过）
                         ↓
                    formatted
                         ↓
                     [publish] → draft
```

使用示例：
    from src.workflows.engine import WorkflowEngine
    
    engine = WorkflowEngine(config)
    
    # 运行完整链路
    result = await engine.run()
    
    # 只运行采集+改写
    result = await engine.run(steps=["collect", "rewrite"])
    
    # 指定数据源和风格
    result = await engine.run(
        source_ids=["36kr", "huxiu"],
        style="professional"
    )

Phase 规划：
- Phase 1 (当前): 串行执行，手动触发
- Phase 3: 添加定时调度（Cron）
- Phase 5: 支持并行执行、分支条件、重试策略
"""

import time
import uuid
from enum import Enum
from typing import Any

from loguru import logger

from src.config.loader import ConfigLoader
from src.storage.database import Database, get_database
from src.sources.rss import RSSSource
from src.sources.base import SourceConfig, SourceType, Content
from src.processors.rewrite import RewriteProcessor, RewriteConfig, RewriteStrategy
from src.processors.formatter import ContentFormatter
from src.publishers.wechat_mp import WeChatPublisher


class StepName(str, Enum):
    """
    工作流步骤枚举
    
    定义了四个核心步骤，按顺序执行：
    1. COLLECT: 从数据源采集原始内容
    2. REWRITE: 调用 LLM 改写内容
    3. FORMAT: 将 Markdown 转换为公众号 HTML
    4. PUBLISH: 发布到公众号草稿箱
    """
    COLLECT = "collect"
    REWRITE = "rewrite"
    FORMAT = "format"
    PUBLISH = "publish"


class WorkflowEngine:
    """
    工作流引擎
    
    负责：
    1. 解析配置，加载数据源
    2. 按顺序执行四个步骤
    3. 记录执行日志
    4. 处理错误，支持断点续传
    
    属性：
        config: 全局配置字典（从 config.yaml 加载）
        db: 数据库实例（延迟初始化）
        batch_id: 当前执行批次ID（格式：YYYYMMDD_HHMMSS）
    """
    
    def __init__(self, config: dict | None = None):
        """
        初始化工作流引擎
        
        参数：
            config: 配置字典，如果为 None 则从 ConfigLoader 加载
        
        注意：
            数据库连接是延迟初始化的，在 run() 调用时才建立
            这样设计是为了支持测试时注入 mock 数据库
        """
        self.config = config or {}
        self.db: Database | None = None
        self.batch_id: str = ""
    
    async def _ensure_db(self) -> Database:
        """
        确保数据库连接已建立
        
        内部方法，在需要数据库时调用
        
        返回：
            已连接的 Database 实例
        
        设计说明：
            使用单例模式（get_database），确保进程内只有一个连接
            避免 SQLite "database is locked" 错误
        """
        if self.db is None:
            db_path = self.config.get("database", {}).get("path", "./data/content.db")
            self.db = await get_database(db_path)
        return self.db
    
    async def run(
        self,
        steps: list[str] | None = None,
        source_ids: list[str] | None = None,
        account_id: str = "default",
        style: str | None = None,
    ) -> dict:
        """
        运行工作流
        
        参数：
            steps: 指定要运行的步骤，如 ["collect", "rewrite"]
                   None 表示运行全部步骤
            source_ids: 指定数据源ID列表，如 ["36kr", "huxiu"]
                        None 表示运行全部已启用的数据源
            account_id: 发布目标公众号账号ID（支持多账号）
            style: 改写风格，如 "professional"、"casual"
                   None 表示使用配置文件中的默认风格
        
        返回：
            {
                "success": bool,       # 是否全部步骤成功
                "batch_id": str,       # 批次ID
                "results": {           # 各步骤结果
                    "collect": {...},
                    "rewrite": {...},
                    "format": {...},
                    "publish": {...}
                }
            }
        
        使用示例：
            # 完整链路
            result = await engine.run()
            
            # 只采集
            result = await engine.run(steps=["collect"])
            
            # 采集指定源，改写指定风格
            result = await engine.run(
                steps=["collect", "rewrite"],
                source_ids=["36kr"],
                style="professional"
            )
        """
        # 生成批次ID（用于关联本次执行的所有日志）
        self.batch_id = time.strftime("%Y%m%d_%H%M%S")
        db = await self._ensure_db()
        
        # 如果未指定步骤，运行全部
        if steps is None:
            steps = [s.value for s in StepName]
        
        logger.info(f"🚀 Workflow started: batch={self.batch_id}, steps={steps}")
        
        # 结果收集
        results = {}
        
        # 步骤间传递的数据（串行依赖）
        collected_contents = []   # Step 1 输出 → Step 2 输入
        rewritten_contents = []   # Step 2 输出 → Step 3 输入
        formatted_contents = []   # Step 3 输出 → Step 4 输入
        
        # ================================================================
        # Step 1: 采集
        # ================================================================
        if StepName.COLLECT in steps:
            step_result = await self._step_collect(db, source_ids)
            results["collect"] = step_result
            collected_contents = step_result.get("items", [])
            
            # 没采到任何内容，停止工作流
            if not collected_contents:
                logger.warning("No content collected, workflow stopped")
                return {
                    "success": False,
                    "batch_id": self.batch_id,
                    "results": results,
                    "error": "no_content"
                }
        
        # ================================================================
        # Step 2: 改写
        # ================================================================
        if StepName.REWRITE in steps:
            step_result = await self._step_rewrite(db, collected_contents, style)
            results["rewrite"] = step_result
            rewritten_contents = step_result.get("items", [])
            
            if not rewritten_contents:
                logger.warning("No content rewritten, workflow stopped")
                return {
                    "success": False,
                    "batch_id": self.batch_id,
                    "results": results,
                    "error": "rewrite_failed"
                }
        
        # ================================================================
        # Step 3: 格式化
        # ================================================================
        if StepName.FORMAT in steps:
            step_result = await self._step_format(db, rewritten_contents)
            results["format"] = step_result
            formatted_contents = step_result.get("items", [])
            
            if not formatted_contents:
                logger.warning("No content formatted, workflow stopped")
                return {
                    "success": False,
                    "batch_id": self.batch_id,
                    "results": results,
                    "error": "format_failed"
                }
        
        # ================================================================
        # Step 4: 发布
        # ================================================================
        if StepName.PUBLISH in steps:
            step_result = await self._step_publish(db, formatted_contents, account_id)
            results["publish"] = step_result
        
        # 汇总结果
        total_success = sum(1 for r in results.values() if r.get("success"))
        total_steps = len(steps)
        
        logger.success(
            f"✅ Workflow completed: batch={self.batch_id}, "
            f"steps={total_success}/{total_steps}"
        )
        
        return {
            "success": total_success == total_steps,
            "batch_id": self.batch_id,
            "results": results,
        }
    
    # ========================================================================
    # Step 1: 采集
    # ========================================================================
    
    async def _step_collect(self, db: Database, source_ids: list[str] | None) -> dict:
        """
        采集步骤：从配置的数据源拉取内容
        
        执行流程：
        1. 加载 config/sources/*.yaml 中的数据源配置
        2. 筛选出 RSS 类型的已启用数据源（MVP 只支持 RSS）
        3. 对每个数据源调用 RSSSource.collect()
        4. 将采集结果存入 contents 表
        5. 更新执行日志
        
        幂等性保证：
        - URL 去重：insert_content 方法会检查 URL 是否已存在
        - 已存在则跳过，返回已有 ID
        
        参数：
            db: 数据库实例
            source_ids: 指定数据源ID列表，None 表示全部
        
        返回：
            {
                "success": bool,
                "items": list[dict],  # 采集到的内容
                "count": int          # 数量
            }
        """
        start = time.time()
        log_id = str(uuid.uuid4())
        
        logger.info("📥 Step: Collecting content...")
        
        # 记录开始状态
        await db.insert_execution_log({
            "id": log_id,
            "batch_id": self.batch_id,
            "step": "collect",
            "status": "started",
            "input_count": 0,
            "output_count": 0,
        })
        
        try:
            # ----------------------------------------------------------------
            # 加载数据源配置
            # ----------------------------------------------------------------
            import yaml
            from pathlib import Path
            
            sources_config_dir = Path("config/sources")
            all_sources = []
            
            # 遍历 config/sources/*.yaml，加载所有数据源
            if sources_config_dir.exists():
                for yf in sources_config_dir.glob("*.yaml"):
                    with open(yf, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if data and "sources" in data:
                            all_sources.extend(data["sources"])
            
            if not all_sources:
                logger.warning("No sources configured in config/sources/")
                await db.execute(
                    "UPDATE execution_log SET status='failed', error='no sources' WHERE id=?",
                    (log_id,),
                )
                return {"success": False, "items": [], "error": "no sources"}
            
            # 筛选指定的数据源
            if source_ids:
                all_sources = [s for s in all_sources if s.get("id") in source_ids]
            
            # ----------------------------------------------------------------
            # 执行采集（MVP只支持RSS）
            # ----------------------------------------------------------------
            # 只处理类型为 rss 且 enabled=true 的数据源
            rss_sources = [
                s for s in all_sources
                if s.get("type") == "rss" and s.get("enabled", True)
            ]
            
            all_items = []
            
            for src_conf in rss_sources:
                try:
                    # 构建 SourceConfig 对象
                    source_config = SourceConfig(
                        id=src_conf["id"],
                        name=src_conf.get("name", src_conf["id"]),
                        type=SourceType.RSS,
                        enabled=True,
                        config={"url": src_conf["url"]},  # RSSSource 支持 url 或 urls
                        filters=src_conf.get("filters", {}),
                    )
                    
                    # 创建 RSSSource 实例并采集
                    source = RSSSource(source_config)
                    result = await source.collect()
                    
                    # 存入数据库
                    for content in result.contents:
                        data = content.to_dict()
                        await db.insert_content(data)
                        all_items.append(data)
                    
                    logger.info(
                        f"  Source {src_conf['id']}: collected {len(result.contents)} items"
                    )
                
                except Exception as e:
                    logger.error(f"  Source {src_conf.get('id', '?')} failed: {e}")
            
            # ----------------------------------------------------------------
            # 如果本次没采到新内容，检查数据库是否有之前采集的
            # ----------------------------------------------------------------
            if not all_items:
                all_items = await db.get_contents_by_status("collected")
            
            duration = time.time() - start
            
            # 更新执行日志
            await db.execute(
                "UPDATE execution_log SET status='success', output_count=?, duration_seconds=? WHERE id=?",
                (len(all_items), duration, log_id),
            )
            
            logger.info(f"📥 Collect done: {len(all_items)} items in {duration:.1f}s")
            return {"success": True, "items": all_items, "count": len(all_items)}
        
        except Exception as e:
            duration = time.time() - start
            await db.execute(
                "UPDATE execution_log SET status='failed', error=?, duration_seconds=? WHERE id=?",
                (str(e), duration, log_id),
            )
            logger.error(f"📥 Collect failed: {e}")
            return {"success": False, "items": [], "error": str(e)}
    
    # ========================================================================
    # Step 2: 改写
    # ========================================================================
    
    async def _step_rewrite(
        self,
        db: Database,
        contents: list[dict],
        style: str | None = None
    ) -> dict:
        """
        改写步骤：调用 LLM 改写内容
        
        执行流程：
        1. 遍历采集到的内容
        2. 检查是否已改写（幂等性）
        3. 调用 RewriteProcessor 进行改写
        4. 存入 rewrites 表
        5. 更新原内容状态为 processed
        
        错误处理：
        - 改写失败的内容状态回退为 collected
        - 下次执行时会自动重试
        
        参数：
            db: 数据库实例
            contents: 待改写的内容列表
            style: 改写风格
        
        返回：
            {
                "success": bool,
                "items": list[dict],  # 改写结果
                "count": int
            }
        """
        start = time.time()
        log_id = str(uuid.uuid4())
        
        logger.info(f"✍️ Step: Rewriting {len(contents)} articles...")
        
        await db.insert_execution_log({
            "id": log_id,
            "batch_id": self.batch_id,
            "step": "rewrite",
            "status": "started",
            "input_count": len(contents),
            "output_count": 0,
        })
        
        try:
            # ----------------------------------------------------------------
            # 准备改写配置
            # ----------------------------------------------------------------
            llm_config = self.config.get("llm", {})
            
            rewrite_config = RewriteConfig(
                strategy=RewriteStrategy.REWRITE,  # MVP 使用深度改写
                style_id=style,
                target_word_count=self.config.get("rewrite", {}).get(
                    "target_word_count", 3000
                ),
            )
            
            rewritten = []
            
            # ----------------------------------------------------------------
            # 逐篇改写（使用异步上下文管理器）
            # ----------------------------------------------------------------
            async with RewriteProcessor({"llm": llm_config}) as processor:
                for item in contents:
                    try:
                        # 幂等性检查：是否已改写
                        existing = await db.get_rewrite_for_content(item["id"])
                        if existing:
                            rewritten.append(existing)
                            continue
                        
                        # 标记为处理中（防止并发重复处理）
                        await db.update_content_status(item["id"], "processing")
                        
                        # 构建 Content 对象
                        content = Content(
                            id=item["id"],
                            source_id=item.get("source_id", ""),
                            source_type=item.get("source_type", ""),
                            url=item.get("url", ""),
                            title=item.get("title", ""),
                            content=item.get("content", ""),
                            summary=item.get("summary", ""),
                            author=item.get("author", ""),
                        )
                        
                        # 调用改写器
                        result = await processor.rewrite(content, rewrite_config)
                        
                        if result.success:
                            # 存入数据库
                            rewrite_data = {
                                "id": str(uuid.uuid4()),
                                "content_id": item["id"],
                                "strategy": rewrite_config.strategy.value,
                                "style": style or "default",
                                "title": result.title or item.get("title", ""),
                                "content": result.rewritten_content,
                                "word_count": len(result.rewritten_content),
                                "model": llm_config.get("model", "unknown"),
                                "tokens_used": result.metadata.get("tokens_used", 0),
                            }
                            await db.insert_rewrite(rewrite_data)
                            rewritten.append(rewrite_data)
                            logger.info(f"  Rewritten: {item.get('title', '?')[:30]}")
                        else:
                            # 改写失败，状态回退
                            await db.update_content_status(item["id"], "collected")
                            logger.warning(f"  Rewrite failed: {result.error}")
                    
                    except Exception as e:
                        # 异常时状态回退
                        await db.update_content_status(item["id"], "collected")
                        logger.error(f"  Rewrite error: {e}")
            
            duration = time.time() - start
            
            await db.execute(
                "UPDATE execution_log SET status='success', output_count=?, duration_seconds=? WHERE id=?",
                (len(rewritten), duration, log_id),
            )
            
            logger.info(f"✍️ Rewrite done: {len(rewritten)}/{len(contents)} in {duration:.1f}s")
            return {"success": True, "items": rewritten, "count": len(rewritten)}
        
        except Exception as e:
            duration = time.time() - start
            await db.execute(
                "UPDATE execution_log SET status='failed', error=?, duration_seconds=? WHERE id=?",
                (str(e), duration, log_id),
            )
            logger.error(f"✍️ Rewrite failed: {e}")
            return {"success": False, "items": [], "error": str(e)}
    
    # ========================================================================
    # Step 3: 格式化
    # ========================================================================
    
    async def _step_format(self, db: Database, rewrites: list[dict]) -> dict:
        """
        格式化步骤：将改写后的 Markdown 转换为公众号 HTML
        
        执行流程：
        1. 遍历改写结果
        2. 检查是否已格式化（幂等性）
        3. 调用 ContentFormatter 进行格式化
        4. 存入 formatted 表
        
        参数：
            db: 数据库实例
            rewrites: 改写结果列表
        
        返回：
            {
                "success": bool,
                "items": list[dict],
                "count": int
            }
        """
        start = time.time()
        log_id = str(uuid.uuid4())
        
        logger.info(f"🎨 Step: Formatting {len(rewrites)} articles...")
        
        await db.insert_execution_log({
            "id": log_id,
            "batch_id": self.batch_id,
            "step": "format",
            "status": "started",
            "input_count": len(rewrites),
            "output_count": 0,
        })
        
        try:
            formatter = ContentFormatter(db, self.config.get("format", {}))
            formatted = []
            
            for rewrite in rewrites:
                try:
                    # 幂等性检查
                    existing = await db.get_formatted_for_rewrite(rewrite["id"])
                    if existing:
                        formatted.append(existing)
                        continue
                    
                    # 格式化
                    result = await formatter.format_article(rewrite)
                    formatted.append(result)
                    logger.info(f"  Formatted: {rewrite.get('title', '?')[:30]}")
                
                except Exception as e:
                    logger.error(f"  Format error: {e}")
            
            duration = time.time() - start
            
            await db.execute(
                "UPDATE execution_log SET status='success', output_count=?, duration_seconds=? WHERE id=?",
                (len(formatted), duration, log_id),
            )
            
            logger.info(f"🎨 Format done: {len(formatted)}/{len(rewrites)} in {duration:.1f}s")
            return {"success": True, "items": formatted, "count": len(formatted)}
        
        except Exception as e:
            duration = time.time() - start
            await db.execute(
                "UPDATE execution_log SET status='failed', error=?, duration_seconds=? WHERE id=?",
                (str(e), duration, log_id),
            )
            logger.error(f"🎨 Format failed: {e}")
            return {"success": False, "items": [], "error": str(e)}
    
    # ========================================================================
    # Step 4: 发布
    # ========================================================================
    
    async def _step_publish(
        self,
        db: Database,
        formatted_items: list[dict],
        account_id: str = "default"
    ) -> dict:
        """
        发布步骤：将格式化后的内容发布到公众号草稿箱
        
        执行流程：
        1. 加载公众号账号配置
        2. 对每篇文章调用 WeChatPublisher.publish_to_draft()
        3. 记录发布结果
        
        MVP 阶段只支持草稿箱模式，不自动发布
        
        参数：
            db: 数据库实例
            formatted_items: 格式化结果列表
            account_id: 公众号账号ID
        
        返回：
            {
                "success": bool,
                "items": list[dict],
                "count": int
            }
        """
        start = time.time()
        log_id = str(uuid.uuid4())
        
        logger.info(f"📤 Step: Publishing {len(formatted_items)} articles...")
        
        await db.insert_execution_log({
            "id": log_id,
            "batch_id": self.batch_id,
            "step": "publish",
            "status": "started",
            "input_count": len(formatted_items),
            "output_count": 0,
        })
        
        try:
            accounts = self.config.get("accounts", [])
            if not accounts:
                logger.warning("No WeChat accounts configured, skipping publish")
                return {"success": False, "items": [], "error": "no accounts"}
            
            publisher = WeChatPublisher(db, accounts)
            published = []
            
            for item in formatted_items:
                try:
                    result = await publisher.publish_to_draft(item, account_id)
                    published.append(result)
                    logger.info(f"  Published to draft: {result.get('media_id', '?')}")
                
                except Exception as e:
                    logger.error(f"  Publish error: {e}")
            
            duration = time.time() - start
            
            await db.execute(
                "UPDATE execution_log SET status='success', output_count=?, duration_seconds=? WHERE id=?",
                (len(published), duration, log_id),
            )
            
            logger.info(f"📤 Publish done: {len(published)}/{len(formatted_items)} in {duration:.1f}s")
            return {"success": True, "items": published, "count": len(published)}
        
        except Exception as e:
            duration = time.time() - start
            await db.execute(
                "UPDATE execution_log SET status='failed', error=?, duration_seconds=? WHERE id=?",
                (str(e), duration, log_id),
            )
            logger.error(f"📤 Publish failed: {e}")
            return {"success": False, "items": [], "error": str(e)}
