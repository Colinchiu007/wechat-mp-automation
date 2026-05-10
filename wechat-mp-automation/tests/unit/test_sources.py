"""
测试数据源模块
"""

import pytest
from datetime import datetime

from src.sources.base import BaseSource, SourceConfig, SourceType, Content


class TestSourceBase:
    """测试数据源基类"""
    
    def test_source_config(self):
        """测试数据源配置"""
        config = SourceConfig(
            id="test_source",
            name="测试数据源",
            type=SourceType.RSS,
            enabled=True,
            priority=1,
            config={"urls": ["https://example.com/feed"]},
            filters={
                "time_range": 7,
                "include_keywords": ["AI", "科技"],
            }
        )
        
        assert config.id == "test_source"
        assert config.name == "测试数据源"
        assert config.type == SourceType.RSS
        assert config.enabled == True
        assert config.priority == 1
    
    def test_content_creation(self):
        """测试内容创建"""
        content = Content(
            id="test_content",
            source_id="test_source",
            source_type="rss",
            url="https://example.com/article",
            title="测试文章标题",
            content="这是文章的内容。",
            summary="这是摘要",
            author="测试作者",
            published_at=datetime.now(),
            metadata={"views": 1000}
        )
        
        assert content.id == "test_content"
        assert content.title == "测试文章标题"
        assert content.author == "测试作者"
        assert content.metadata["views"] == 1000
    
    def test_content_to_dict(self):
        """测试内容转字典"""
        content = Content(
            id="test_content",
            source_id="test_source",
            source_type="rss",
            url="https://example.com/article",
            title="测试标题",
            content="测试内容",
        )
        
        data = content.to_dict()
        
        assert isinstance(data, dict)
        assert data["id"] == "test_content"
        assert data["title"] == "测试标题"
        assert "created_at" in data


class TestSourceFilters:
    """测试数据源过滤"""
    
    def test_include_keywords_filter(self):
        """测试包含关键词过滤"""
        from src.sources.base import BaseSource, SourceConfig, SourceType
        
        class MockSource(BaseSource):
            async def connect(self):
                return True
            
            async def collect(self, filters=None):
                return None
            
            async def test(self):
                return None
        
        config = SourceConfig(
            id="test",
            name="test",
            type=SourceType.RSS,
            filters={
                "include_keywords": ["AI", "ChatGPT"],
                "include_mode": "any"
            }
        )
        
        source = MockSource(config)
        
        # 测试内容
        matching_content = Content(
            id="1",
            source_id="test",
            source_type="rss",
            url="https://example.com",
            title="AI 最新消息",
            content="ChatGPT 发布新版本"
        )
        
        non_matching_content = Content(
            id="2",
            source_id="test",
            source_type="rss",
            url="https://example.com",
            title="天气",
            content="今天天气很好"
        )
        
        # 过滤
        filtered = source._apply_filters([matching_content, non_matching_content])
        
        assert len(filtered) == 1
        assert filtered[0].id == "1"
    
    def test_exclude_keywords_filter(self):
        """测试排除关键词过滤"""
        from src.sources.base import BaseSource, SourceConfig, SourceType
        
        class MockSource(BaseSource):
            async def connect(self):
                return True
            
            async def collect(self, filters=None):
                return None
            
            async def test(self):
                return None
        
        config = SourceConfig(
            id="test",
            name="test",
            type=SourceType.RSS,
            filters={
                "exclude_keywords": ["广告", "推广"]
            }
        )
        
        source = MockSource(config)
        
        # 测试内容
        content1 = Content(
            id="1",
            source_id="test",
            source_type="rss",
            url="https://example.com",
            title="正常文章",
            content="这是正常的文章内容"
        )
        
        content2 = Content(
            id="2",
            source_id="test",
            source_type="rss",
            url="https://example.com",
            title="广告文章",
            content="这是广告内容"
        )
        
        filtered = source._apply_filters([content1, content2])
        
        assert len(filtered) == 1
        assert filtered[0].id == "1"
    
    def test_time_range_filter(self):
        """测试时间范围过滤"""
        from src.sources.base import BaseSource, SourceConfig, SourceType
        from datetime import timedelta
        
        class MockSource(BaseSource):
            async def connect(self):
                return True
            
            async def collect(self, filters=None):
                return None
            
            async def test(self):
                return None
        
        config = SourceConfig(
            id="test",
            name="test",
            type=SourceType.RSS,
            filters={
                "time_range": 7  # 7天内
            }
        )
        
        source = MockSource(config)
        
        # 新内容（3天前）
        recent_content = Content(
            id="1",
            source_id="test",
            source_type="rss",
            url="https://example.com",
            title="新文章",
            content="内容",
            published_at=datetime.now() - timedelta(days=3)
        )
        
        # 旧内容（10天前）
        old_content = Content(
            id="2",
            source_id="test",
            source_type="rss",
            url="https://example.com",
            title="旧文章",
            content="内容",
            published_at=datetime.now() - timedelta(days=10)
        )
        
        filtered = source._apply_filters([recent_content, old_content])
        
        assert len(filtered) == 1
        assert filtered[0].id == "1"
