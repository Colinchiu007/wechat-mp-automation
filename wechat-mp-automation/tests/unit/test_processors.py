"""
测试内容处理器
"""

import pytest

from src.processors.filter import ContentFilter
from src.processors.formatter import ContentFormatter
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
        # 标题太短，reasons 中包含"标题太短"
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
        # 内容太短，reasons 中包含"内容太短"
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
        assert any("敏感词" in reason for reason in result.reasons)
        # 敏感词存在时 passed 必定为 False
        assert result.passed == False

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
                content="短",  # 标题<5字符，内容<100字符，扣分后 score=0.5，刚好通过（>=0.5）
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

        # 全部通过（filter 采用扣分制，只要 score>=0.5 就通过）
        # batch2 虽然短，但 score=0.5 没触发敏感词，仍通过
        assert len(passed) == 3
        assert len(failed) == 0
        assert all(c.id in ("batch1", "batch2", "batch3") for c in passed)

    def test_batch_filter_with_sensitive(self):
        """测试批量过滤 - 含敏感词的内容应被过滤"""
        filter = ContentFilter()

        contents = [
            Content(
                id="safe1",
                source_id="test",
                source_type="rss",
                url="https://example.com",
                title="正常标题",
                content="这是正常的文章内容，包含足够多的文字。" * 5,
            ),
            Content(
                id="unsafe1",
                source_id="test",
                source_type="rss",
                url="https://example.com",
                title="包含敏感词",
                content="这是一段包含敏感词示例1的文章内容。",
            ),
        ]

        passed, failed = filter.filter_batch(contents)

        # 敏感词内容必定被过滤
        assert len(passed) == 1
        assert len(failed) == 1
        assert passed[0].id == "safe1"
        assert failed[0][0].id == "unsafe1"


class TestContentFormatter:
    """测试内容格式化器"""

    def test_markdown_to_html(self):
        """测试 Markdown 转 HTML"""
        from src.processors.formatter import markdown_to_wechat_html

        md = "## 标题\n\n这是第一段。\n\n这是第二段。"
        html = markdown_to_wechat_html(md)

        assert "<h2" in html
        assert "这是第一段" in html
        assert "这是第二段" in html

    def test_markdown_to_html_with_code(self):
        """测试代码块转换"""
        from src.processors.formatter import markdown_to_wechat_html

        md = "这是普通文本。\n\n```python\nprint('hello')\n```\n\n更多内容。"
        html = markdown_to_wechat_html(md)

        assert "<pre" in html  # 带属性的标签
        assert "print('hello')" in html

    def test_markdown_to_html_with_image(self):
        """测试图片插入"""
        from src.processors.formatter import markdown_to_wechat_html

        md = "## 标题\n\n段落1\n\n段落2"
        images = [
            {"path": "./test.jpg", "position": 1, "alt": "配图"},
        ]
        html = markdown_to_wechat_html(md, images)

        assert "<img" in html
