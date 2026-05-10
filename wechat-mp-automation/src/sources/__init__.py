"""
数据采集模块
"""

from src.sources.base import BaseSource, SourceResult, SourceConfig
from src.sources.rss import RSSSource
from src.sources.wechat import WechatSource
from src.sources.zhihu import ZhihuSource
from src.sources.youtube import YoutubeSource
from src.sources.web_scraper import WebScraperSource

__all__ = [
    "BaseSource",
    "SourceResult",
    "SourceConfig",
    "RSSSource",
    "WechatSource",
    "ZhihuSource",
    "YoutubeSource",
    "WebScraperSource",
]
