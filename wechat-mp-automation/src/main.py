"""
微信公众号自动化 - 主入口
Phase 1 MVP: 串行执行 collect → rewrite → format → publish

用法:
  python -m src.main run --all                          # 运行完整链路
  python -m src.main run --steps collect,rewrite         # 只运行采集+改写
  python -m src.main sources collect --source tech-rss   # 采集指定数据源
  python -m src.main sources test --source tech-rss      # 测试数据源
  python -m src.main status                               # 查看执行状态
"""

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

from src.config.loader import ConfigLoader
from src.workflows.engine import WorkflowEngine, StepName
from src.storage.database import Database, get_database
from src.sources.rss import RSSSource
from src.sources.base import SourceConfig, SourceType


def setup_logging(level: str = "INFO", log_file: str | None = None):
    """设置日志"""
    logger.remove()
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
        "<level>{message}</level>"
    )
    logger.add(sys.stderr, level=level, format=fmt)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        logger.add(log_file, level=level, format=fmt, rotation="10 MB", encoding="utf-8")


async def run_workflow(args):
    """运行工作流"""
    config = ConfigLoader.load(args.config)
    config_dict = config.model_dump()

    # 合并命令行参数
    steps = None
    if args.steps:
        steps = [s.strip() for s in args.steps.split(",")]

    engine = WorkflowEngine(config_dict)
    result = await engine.run(
        steps=steps,
        source_ids=args.source,
        account_id=args.account,
        style=args.style,
    )

    if result["success"]:
        logger.success("🎉 工作流执行完成！")
    else:
        logger.error(f"❌ 工作流执行失败: {result.get('error', 'unknown')}")

    return result


async def sources_collect(args):
    """采集数据"""
    config = ConfigLoader.load(args.config)
    db_path = config.database.path
    db = await get_database(db_path)

    import yaml
    sources_config_dir = Path("config/sources")
    all_sources = []

    if sources_config_dir.exists():
        for yf in sources_config_dir.glob("*.yaml"):
            with open(yf, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "sources" in data:
                    all_sources.extend(data["sources"])

    if args.source:
        all_sources = [s for s in all_sources if s.get("id") in args.source]

    rss_sources = [s for s in all_sources if s.get("type") == "rss" and s.get("enabled", True)]

    if not rss_sources:
        logger.warning("没有找到可用的RSS数据源")
        return

    total = 0
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

            for content in result.contents:
                data = content.to_dict()
                await db.insert_content(data)

            total += len(result.contents)
            logger.info(f"✅ {src_conf['id']}: 采集 {len(result.contents)} 篇")

        except Exception as e:
            logger.error(f"❌ {src_conf.get('id', '?')}: 采集失败 - {e}")

    logger.info(f"📊 总计采集 {total} 篇文章")


async def sources_test(args):
    """测试数据源"""
    config = ConfigLoader.load(args.config)

    import yaml
    sources_config_dir = Path("config/sources")
    all_sources = []

    if sources_config_dir.exists():
        for yf in sources_config_dir.glob("*.yaml"):
            with open(yf, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "sources" in data:
                    all_sources.extend(data["sources"])

    if args.source:
        all_sources = [s for s in all_sources if s.get("id") in args.source]

    for src_conf in all_sources:
        if src_conf.get("type") != "rss":
            continue
        try:
            source_config = SourceConfig(
                id=src_conf["id"],
                name=src_conf.get("name", src_conf["id"]),
                type=SourceType.RSS,
                enabled=True,
                config={"url": src_conf["url"]},
            )
            source = RSSSource(source_config)
            result = await source.test()
            status = "✅ 连通" if result.success else "❌ 失败"
            logger.info(f"{status} {src_conf['id']}: {result.message}")

        except Exception as e:
            logger.error(f"❌ {src_conf.get('id', '?')}: 测试失败 - {e}")


async def show_status(args):
    """查看状态"""
    config = ConfigLoader.load(args.config)
    db_path = config.database.path
    db = await get_database(db_path)

    # 各状态文章数
    for status in ["collected", "processing", "processed", "published", "error"]:
        rows = await db.fetch_all(
            "SELECT COUNT(*) as cnt FROM contents WHERE status = ?", (status,)
        )
        count = rows[0]["cnt"] if rows else 0
        if count > 0:
            logger.info(f"  {status}: {count} 篇")

    # 最近执行日志
    logs = await db.fetch_all(
        "SELECT * FROM execution_log ORDER BY created_at DESC LIMIT 5"
    )
    if logs:
        logger.info("\n最近执行日志:")
        for log in logs:
            status_icon = "✅" if log["status"] == "success" else "❌"
            logger.info(
                f"  {status_icon} [{log['batch_id']}] {log['step']} - "
                f"{log['status']} ({log.get('duration_seconds', 0):.1f}s)"
            )


def main():
    parser = argparse.ArgumentParser(description="微信公众号自动化系统")
    parser.add_argument("--config", "-c", default="config/config.yaml", help="配置文件路径")
    parser.add_argument("--log-level", "-l", default="INFO", help="日志级别")

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # run 命令
    run_parser = subparsers.add_parser("run", help="运行工作流")
    run_parser.add_argument("--all", action="store_true", help="运行全部步骤")
    run_parser.add_argument("--steps", "-s", help="指定步骤: collect,rewrite,format,publish")
    run_parser.add_argument("--source", nargs="+", help="指定数据源ID")
    run_parser.add_argument("--account", default="default", help="发布目标公众号")
    run_parser.add_argument("--style", help="改写风格ID")

    # sources 命令
    sources_parser = subparsers.add_parser("sources", help="数据源管理")
    sources_sub = sources_parser.add_subparsers(dest="sources_command")
    sources_collect_parser = sources_sub.add_parser("collect", help="采集数据")
    sources_collect_parser.add_argument("--source", nargs="+", help="指定数据源ID")
    sources_test_parser = sources_sub.add_parser("test", help="测试数据源")
    sources_test_parser.add_argument("--source", nargs="+", help="指定数据源ID")

    # status 命令
    subparsers.add_parser("status", help="查看执行状态")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    setup_logging(args.log_level)

    if args.command == "run":
        asyncio.run(run_workflow(args))
    elif args.command == "sources":
        if args.sources_command == "collect":
            asyncio.run(sources_collect(args))
        elif args.sources_command == "test":
            asyncio.run(sources_test(args))
        else:
            sources_parser.print_help()
    elif args.command == "status":
        asyncio.run(show_status(args))


if __name__ == "__main__":
    main()
