"""
微信公众号自动化 - 主入口文件
"""

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

from src.config.loader import ConfigLoader
from src.workflows.engine import WorkflowEngine


def setup_logging(level: str = "INFO"):
    """设置日志"""
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )


async def run_workflow(workflow_name: str, source_ids: list[str] = None):
    """运行指定工作流"""
    config = ConfigLoader.load()
    engine = WorkflowEngine(config)
    
    logger.info(f"Starting workflow: {workflow_name}")
    result = await engine.run(workflow_name, source_ids)
    
    if result.success:
        logger.success(f"Workflow completed successfully")
    else:
        logger.error(f"Workflow failed: {result.error}")
    
    return result


async def run_scheduler():
    """启动调度器"""
    from src.scheduler.cron import Scheduler
    
    config = ConfigLoader.load()
    scheduler = Scheduler(config)
    
    logger.info("Starting scheduler...")
    await scheduler.start()


def run_api():
    """启动 API 服务"""
    import uvicorn
    from src.api.app import app
    
    logger.info("Starting API server...")
    uvicorn.run(app, host="0.0.0.0", port=8080)


def main():
    parser = argparse.ArgumentParser(description="微信公众号自动化")
    parser.add_argument("command", choices=["run", "scheduler", "api"], help="命令")
    parser.add_argument("--workflow", "-w", default="default", help="工作流名称")
    parser.add_argument("--source", "-s", nargs="+", help="数据源ID列表")
    parser.add_argument("--config", "-c", default="config/config.yaml", help="配置文件路径")
    parser.add_argument("--log-level", "-l", default="INFO", help="日志级别")
    
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    
    if args.command == "run":
        asyncio.run(run_workflow(args.workflow, args.source))
    elif args.command == "scheduler":
        asyncio.run(run_scheduler())
    elif args.command == "api":
        run_api()


if __name__ == "__main__":
    main()
