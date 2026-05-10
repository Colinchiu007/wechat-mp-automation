"""
简单调度器（Phase 1 MVP：仅手动触发，不做定时）
Phase 3 会加入 Cron 定时调度
"""

from loguru import logger


class SimpleScheduler:
    """MVP调度器——只支持手动触发"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    async def start(self):
        """启动调度器（MVP: 不做任何事，预留接口）"""
        logger.info("Scheduler started (manual mode - no cron)")

    async def stop(self):
        """停止调度器"""
        logger.info("Scheduler stopped")

    async def add_job(self, name: str, cron: str, workflow: str, **kwargs):
        """添加定时任务（Phase 3 实现）"""
        raise NotImplementedError("定时调度将在 Phase 3 实现，当前请使用手动触发模式")

    async def list_jobs(self) -> list[dict]:
        """列出所有定时任务"""
        return []

    async def remove_job(self, name: str):
        """删除定时任务"""
        pass
