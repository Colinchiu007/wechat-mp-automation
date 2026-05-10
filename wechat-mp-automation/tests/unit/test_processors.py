"""
测试内容处理器
"""

import pytest

from src.processors.filter import ContentFilter
from src.processors.formatter import ContentFormatter, FormatConfig, OutputFormat
from src.sources.base import Content


class TestContentFilter:
    """测试内容过滤器"""
    
    def test_filter_normal_content(self):
        """测试正常内容"""
        filter = ContentFilter()
        
        content = Content(
            id="test1",
            source_id="test",
            source_type="rss",
            url="https://example.com",
            title="这是一个正常的标题",
            content="这是一段正常的文章内容，包含足够多的文字来通过质量检测。文章讲述了科技发展的重要性，以及AI技术的应用前景。这是一个很好的示例内容。",
        )
        
        result = filter.filter(content)
        assert result.passed == True
    
    def test_filter_short_title(self):
        """测试标题太短"""
        filter = ContentFilter()
        
        content = Content(
            id="test2",
            source_id="test",
            source_type="rss",
            url="https://example.com",
            title="短",
            content="这是一段正常的文章内容。",
        )
        
        result = filter.filter(content)
        assert result.passed == False
        assert "标题太短" in result.reasons
    
    def test_filter_short_content(self):
        """测试内容太短"""
        filter = ContentFilter()
        
        content = Content(
            id="test3",
            source_id="test",
            source_type="rss",
            url="https://example.com",
            title="这是一个正常的标题",
            content="内容太短",
        )
        
        result = filter.filter(content)
        assert result.passed == False
        assert "内容太短" in result.reasons
    
    def test_filter_sensitive_words(self):
        """测试敏感词"""
        filter = ContentFilter()
        
        content = Content(
            id="test4",
            source_id="test",
            source_type="rss",
            url="https://example.com",
            title="这是一个正常的标题",
            content="这是一段包含敏感词示例1的文章内容。",
        )
        
        result = filter.filter(content)
        assert result.passed == False
        assert any("敏感词" in reason for reason in result.reasons)
    
    def test_batch_filter(self):
        """测试批量过滤"""
        filter = ContentFilter()
        
        contents = [
            Content(
                id="batch1",
                source_id="test",
                source_type="rss",
                url="https://example1.com",
                title="正常标题1",
                content="这是正常的文章内容，包含足够多的文字来通过质量检测。" * 5,
            ),
            Content(
                id="batch2",
                source_id="test",
                source_type="rss",
                url="https://example2.com",
                title="短",
                content="内容太短",
            ),
            Content(
                id="batch3",
                source_id="test",
                source_type="rss",
                url="https://example3.com",
                title="正常标题3",
                content="这也是正常的文章内容，包含足够多的文字来通过质量检测。" * 5,
            ),
        ]
        
        passed, failed = filter.filter_batch(contents)
        
        assert len(passed) == 2
        assert len(failed) == 1


class TestContentFormatter:
    """测试内容格式化器"""
    
    def test_format_markdown(self):
        """测试 Markdown 格式"""
        formatter = ContentFormatter()
        
        result = formatter.format(
            title="测试标题",
            content="这是第一段内容。\n\n这是第二段内容。",
            summary="这是摘要",
            images=["https://example.com/image.jpg"]
        )
        
        assert "# 测试标题" in result
        assert "> 这是摘要" in result
        assert "![封面](https://example.com/image.jpg)" in result
        assert "这是第一段内容。" in result
    
    def test_format_wechat(self):
        """测试微信公众号格式"""
        formatter = ContentFormatter()
        
        result = formatter.format(
            title="微信公众号标题",
            content="这是微信公众号的文章内容。\n\n包含多段落的内容。",
            config=FormatConfig(format=OutputFormat.WECHAT)
        )
        
        assert "**微信公众号标题**" in result
        assert "这是微信公众号的文章内容。" in result
    
    def test_format_xiaohongshu(self):
        """测试小红书格式"""
        formatter = ContentFormatter()
        
        result = formatter.format(
            title="小红书标题",
            content="这是小红书的内容。",
            images=["https://example.com/cover.jpg"],
            config=FormatConfig(format=OutputFormat.XIAOHONGSHU)
        )
        
        assert "## 小红书标题" in result
        assert "[图片]" in result
        assert "#标签" in result
    
    def test_format_youtube(self):
        """测试 YouTube 格式"""
        formatter = ContentFormatter()
        
        result = formatter.format(
            title="YouTube 标题",
            content="这是 YouTube 视频的描述内容。",
            summary="视频摘要",
            config=FormatConfig(format=OutputFormat.YOUTUBE)
        )
        
        assert "# YouTube 标题" in result
        assert "## 描述" in result
        assert "## 标签" in result
    
    def test_truncate_long_content(self):
        """测试截断长内容"""
        formatter = ContentFormatter()
        
        # 小红书限制1000字
        long_content = "测试内容。" * 300
        
        result = formatter.format(
            title="长内容标题",
            content=long_content,
            config=FormatConfig(format=OutputFormat.XIAOHONGSHU)
        )
        
        assert len(result) <= 1200  # 留有余地
