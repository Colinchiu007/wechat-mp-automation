"""
工作流引擎——模块E的核心
- 串行执行: collect → rewrite → format → publish
- 状态追踪
- 错误恢复
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
    """工作流步骤"""
    COLLECT = "collect"
    REWRITE = "rewrite"
    FORMAT = "format"
    PUBLISH = "publish"


class WorkflowEngine:
    """工作流引擎"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.db: Database | None = None
        self.batch_id: str = ""

    async def _ensure_db(self) -> Database:
        """确保数据库连接"""
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
        steps: 指定要运行的步骤，None则运行全部
        source_ids: 指定数据源，None则运行全部已启用的
        account_id: 发布目标公众号
        style: 改写风格
        """
        self.batch_id = time.strftime("%Y%m%d_%H%M%S")
        db = await self._ensure_db()

        if steps is None:
            steps = [s.value for s in StepName]

        logger.info(f"🚀 Workflow started: batch={self.batch_id}, steps={steps}")

        results = {}
        collected_contents = []
        rewritten_contents = []
        formatted_contents = []

        # ========== Step 1: 采集 ==========
        if StepName.COLLECT in steps:
            step_result = await self._step_collect(db, source_ids)
            results["collect"] = step_result
            collected_contents = step_result.get("items", [])
            if not collected_contents:
                logger.warning("No content collected, workflow stopped")
                return {"success": False, "batch_id": self.batch_id, "results": results, "error": "no_content"}

        # ========== Step 2: 改写 ==========
        if StepName.REWRITE in steps:
            step_result = await self._step_rewrite(db, collected_contents, style)
            results["rewrite"] = step_result
            rewritten_contents = step_result.get("items", [])
            if not rewritten_contents:
                logger.warning("No content rewritten, workflow stopped")
                return {"success": False, "batch_id": self.batch_id, "results": results, "error": "rewrite_failed"}

        # ========== Step 3: 格式化 ==========
        if StepName.FORMAT in steps:
            step_result = await self._step_format(db, rewritten_contents)
            results["format"] = step_result
            formatted_contents = step_result.get("items", [])
            if not formatted_contents:
                logger.warning("No content formatted, workflow stopped")
                return {"success": False, "batch_id": self.batch_id, "results": results, "error": "format_failed"}

        # ========== Step 4: 发布 ==========
        if StepName.PUBLISH in steps:
            step_result = await self._step_publish(db, formatted_contents, account_id)
            results["publish"] = step_result

        # 汇总
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

    async def _step_collect(self, db: Database, source_ids: list[str] | None) -> dict:
        """采集步骤"""
        start = time.time()
        log_id = str(uuid.uuid4())

        logger.info("📥 Step: Collecting content...")
        await db.insert_execution_log({
            "id": log_id, "batch_id": self.batch_id, "step": "collect",
            "status": "started", "input_count": 0, "output_count": 0,
        })

        try:
            # 加载数据源配置
            import yaml
            from pathlib import Path

            sources_config_dir = Path("config/sources")
            all_sources = []

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

            # 只处理启用的 RSS 源（MVP只支持RSS）
            rss_sources = [s for s in all_sources if s.get("type") == "rss" and s.get("enabled", True)]

            all_items = []
            for src_conf in rss_sources:
                try:
                    source_config = SourceConfig(
                        id=src_conf["id"],
                        name=src_conf.get("name", src_conf["id"]),
                        type=SourceType.RSS,
                        enabled=True,
                        config={"url": src_conf["url"]},
                        filters=src_conf.get("filters", {}),
                    )
                    source = RSSSource(source_config)
                    result = await source.collect()

                    # 存入数据库
                    for content in result.contents:
                        data = content.to_dict()
                        await db.insert_content(data)
                        all_items.append(data)

                    logger.info(f"  Source {src_conf['id']}: collected {len(result.contents)} items")

                except Exception as e:
                    logger.error(f"  Source {src_conf.get('id', '?')} failed: {e}")

            # 获取所有 collected 状态的内容
            if not all_items:
                # 即使本次没采到新内容，也可能数据库里有之前采集的
                all_items = await db.get_contents_by_status("collected")

            duration = time.time() - start
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

    async def _step_rewrite(self, db: Database, contents: list[dict], style: str | None = None) -> dict:
        """改写步骤"""
        start = time.time()
        log_id = str(uuid.uuid4())

        logger.info(f"✍️ Step: Rewriting {len(contents)} articles...")
        await db.insert_execution_log({
            "id": log_id, "batch_id": self.batch_id, "step": "rewrite",
            "status": "started", "input_count": len(contents), "output_count": 0,
        })

        try:
            llm_config = self.config.get("llm", {})
            rewrite_config = RewriteConfig(
                strategy=RewriteStrategy.REWRITE,
                style_id=style,
                target_word_count=self.config.get("rewrite", {}).get("target_word_count", 3000),
            )

            rewritten = []
            async with RewriteProcessor({"llm": llm_config}) as processor:
                for item in contents:
                    try:
                        # 检查是否已改写
                        existing = await db.get_rewrite_for_content(item["id"])
                        if existing:
                            rewritten.append(existing)
                            continue

                        # 标记为处理中
                        await db.update_content_status(item["id"], "processing")

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

                        result = await processor.rewrite(content, rewrite_config)
                        if result.success:
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
                            await db.update_content_status(item["id"], "collected")
                            logger.warning(f"  Rewrite failed: {result.error}")

                    except Exception as e:
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

    async def _step_format(self, db: Database, rewrites: list[dict]) -> dict:
        """格式化步骤"""
        start = time.time()
        log_id = str(uuid.uuid4())

        logger.info(f"🎨 Step: Formatting {len(rewrites)} articles...")
        await db.insert_execution_log({
            "id": log_id, "batch_id": self.batch_id, "step": "format",
            "status": "started", "input_count": len(rewrites), "output_count": 0,
        })

        try:
            formatter = ContentFormatter(db, self.config.get("format", {}))
            formatted = []

            for rewrite in rewrites:
                try:
                    # 检查是否已格式化
                    existing = await db.get_formatted_for_rewrite(rewrite["id"])
                    if existing:
                        formatted.append(existing)
                        continue

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

    async def _step_publish(self, db: Database, formatted_items: list[dict], account_id: str = "default") -> dict:
        """发布步骤"""
        start = time.time()
        log_id = str(uuid.uuid4())

        logger.info(f"📤 Step: Publishing {len(formatted_items)} articles...")
        await db.insert_execution_log({
            "id": log_id, "batch_id": self.batch_id, "step": "publish",
            "status": "started", "input_count": len(formatted_items), "output_count": 0,
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
