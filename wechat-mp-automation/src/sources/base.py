"""
数据采集基类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SourceType(Enum):
    """数据源类型"""
    RSS = "rss"
    WECHAT = "wechat_search"
    ZHIHU = "zhihu"
    YOUTUBE = "youtube"
    XIAOHONGSHU = "xiaohongshu"
    DOUYIN = "douyin"
    WEIBO = "weibo"
    WEB_SCRAPER = "web_scraping"
    NOTION = "notion"
    AIRTABLE = "airtable"


class SourceStatus(Enum):
    """数据源状态"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class SourceConfig:
    """数据源配置"""
    id: str
    name: str
    type: SourceType
    enabled: bool = True
    priority: int = 0
    config: dict[str, Any] = field(default_factory=dict)
    schedule: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Content:
    """采集的内容"""
    id: str
    source_id: str
    source_type: str
    url: str
    title: str
    content: str = ""
    summary: str = ""
    author: str = ""
    published_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SourceResult:
    """数据源采集结果"""
    success: bool
    contents: list[Content] = field(default_factory=list)
    error: str | None = None
    collected_count: int = 0
    filtered_count: int = 0
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResult:
    """测试结果"""
    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class BaseSource(ABC):
    """数据源基类"""
    
    def __init__(self, config: SourceConfig):
        self.config = config
        self.logger = None  # 将在子类中初始化
    
    @abstractmethod
    async def connect(self) -> bool:
        """连接数据源"""
        pass
    
    @abstractmethod
    async def collect(self, filters: dict[str, Any] | None = None) -> SourceResult:
        """采集内容"""
        pass
    
    @abstractmethod
    async def test(self) -> TestResult:
        """测试数据源连接"""
        pass
    
    def _apply_filters(self, contents: list[Content]) -> list[Content]:
        """应用过滤规则"""
        filters = self.config.filters
        if not filters:
            return contents
        
        filtered = []
        for content in contents:
            # 关键词过滤
            include_keywords = filters.get("include_keywords", [])
            exclude_keywords = filters.get("exclude_keywords", [])
            
            if include_keywords:
                include_mode = filters.get("include_mode", "any")
                if include_mode == "all":
                    if not all(kw in content.title + content.content for kw in include_keywords):
                        continue
                else:  # any
                    if not any(kw in content.title + content.content for kw in include_keywords):
                        continue
            
            if exclude_keywords:
                exclude_mode = filters.get("exclude_mode", "any")
                if exclude_mode == "all":
                    if all(kw in content.title + content.content for kw in exclude_keywords):
                        continue
                else:  # any
                    if any(kw in content.title + content.content for kw in exclude_keywords):
                        continue
            
            # 时间过滤
            time_range = filters.get("time_range")
            if time_range and content.published_at:
                from datetime import timedelta
                cutoff = datetime.now() - timedelta(days=time_range)
                if content.published_at < cutoff:
                    continue
            
            # 热度过滤
            min_views = filters.get("min_views")
            if min_views:
                views = content.metadata.get("views", 0)
                if views < min_views:
                    continue
            
            filtered.append(content)
        
        return filtered
    
    @staticmethod
    def get_source_class(source_type: SourceType):
        """根据类型获取对应的源类"""
        from src.sources.rss import RSSSource
        from src.sources.wechat import WechatSource
        from src.sources.zhihu import ZhihuSource
        from src.sources.youtube import YoutubeSource
        from src.sources.web_scraper import WebScraperSource
        
        source_map = {
            SourceType.RSS: RSSSource,
            SourceType.WECHAT: WechatSource,
            SourceType.ZHIHU: ZhihuSource,
            SourceType.YOUTUBE: YoutubeSource,
            SourceType.WEB_SCRAPER: WebScraperSource,
        }
        
        return source_map.get(source_type)
