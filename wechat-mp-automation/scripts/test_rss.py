"""测试 RSS 采集"""
import asyncio
from src.sources.rss import RSSSource
from src.sources.base import SourceConfig, SourceType


async def test():
    config = SourceConfig(
        id="test-rss",
        name="Test RSS",
        type=SourceType.RSS,
        enabled=True,
        config={"url": "https://hnrss.org/frontpage"},
        filters={"time_range": 7},
    )
    source = RSSSource(config)
    result = await source.collect()
    print(f"Collected: {len(result.contents)} items")
    for c in result.contents[:3]:
        title = (c.title or "no title")[:50]
        print(f"  - {title}")


asyncio.run(test())
