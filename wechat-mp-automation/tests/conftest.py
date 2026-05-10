"""
pytest 配置
"""

import sys
from pathlib import Path

# 将 src 目录添加到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import pytest


@pytest.fixture
def sample_config():
    """示例配置"""
    return {
        "app": {
            "name": "wechat-mp-automation",
            "version": "1.0.0",
            "env": "test"
        },
        "llm": {
            "provider": "openai",
            "api_key": "test-key",
            "model": "gpt-4o",
            "base_url": "https://api.openai.com/v1",
            "timeout": 30,
            "retry": 1
        },
        "rewrite": {
            "default_strategy": "rewrite",
            "min_word_count": 100,
            "max_word_count": 5000,
            "target_word_count": 2000
        },
        "image": {
            "default_count": 1
        }
    }


@pytest.fixture
def sample_content():
    """示例内容"""
    from src.sources.base import Content
    from datetime import datetime
    
    return Content(
        id="test-123",
        source_id="test-source",
        source_type="rss",
        url="https://example.com/article",
        title="测试文章标题",
        content="这是测试文章的内容。文章讲述了AI技术的发展和应用。包括ChatGPT、大模型等前沿技术。这是一个很好的示例内容，用于测试内容处理流程。" * 5,
        summary="这是文章摘要",
        author="测试作者",
        published_at=datetime.now(),
        metadata={"views": 1000}
    )
