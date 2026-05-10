"""
RSS 数据源
"""

import asyncio
import feedparser
from datetime import datetime
from typing import Any
import uuid

from loguru import logger

from src.sources.base import BaseSource, SourceConfig, SourceResult, TestResult, Content


class RSSSource(BaseSource):
    """RSS 数据源"""
    
    async def connect(self) -> bool:
        """连接 RSS 源（RSS 不需要持久连接）"""
        return True
    
    async def collect(self, filters: dict[str, Any] | None = None) -> SourceResult:
        """采集 RSS 内容"""
        import time
        start_time = time.time()
        
        urls = self.config.config.get("urls", [])
        # 兼容单 url 配置
        single_url = self.config.config.get("url")
        if single_url and not urls:
            urls = [single_url]
        
        if not urls:
            return SourceResult(
                success=False,
                error="No URLs configured for RSS source"
            )
        
        all_contents = []
        errors = []
        
        for url in urls:
            try:
                contents = await self._fetch_feed(url)
                all_contents.extend(contents)
            except Exception as e:
                errors.append(f"Error fetching {url}: {str(e)}")
                logger.error(f"RSS fetch error: {e}")
        
        # 应用过滤
        filtered_contents = self._apply_filters(all_contents)
        
        duration = time.time() - start_time
        
        return SourceResult(
            success=len(all_contents) > 0,
            contents=filtered_contents,
            collected_count=len(all_contents),
            filtered_count=len(all_contents) - len(filtered_contents),
            duration=duration,
            error="; ".join(errors) if errors else None
        )
    
    async def _fetch_feed(self, url: str) -> list[Content]:
        """获取单个 RSS 源"""
        # 在线程池中运行同步的 feedparser
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, url)
        
        contents = []
        for entry in feed.entries:
            try:
                # 解析发布日期
                published_at = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6])
                
                # 获取内容
                content_text = ""
                if hasattr(entry, "content"):
                    content_text = entry.content[0].value
                elif hasattr(entry, "summary"):
                    content_text = entry.summary
                
                # 清理 HTML
                content_text = self._clean_html(content_text)
                
                content = Content(
                    id=str(uuid.uuid4()),
                    source_id=self.config.id,
                    source_type="rss",
                    url=entry.get("link", ""),
                    title=entry.get("title", ""),
                    content=content_text,
                    summary=self._truncate(content_text, 200),
                    author=entry.get("author", ""),
                    published_at=published_at,
                    metadata={
                        "feed_url": url,
                        "tags": [tag.term for tag in getattr(entry, "tags", [])],
                    },
                    raw_data=entry,
                )
                contents.append(content)
            except Exception as e:
                logger.warning(f"Error parsing RSS entry: {e}")
                continue
        
        return contents
    
    def _clean_html(self, html: str) -> str:
        """清理 HTML 标签"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n", strip=True)
    
    def _truncate(self, text: str, length: int) -> str:
        """截断文本"""
        if len(text) <= length:
            return text
        return text[:length] + "..."
    
    async def test(self) -> TestResult:
        """测试 RSS 源"""
        urls = self.config.config.get("urls", [])
        single_url = self.config.config.get("url")
        if single_url and not urls:
            urls = [single_url]
        
        if not urls:
            return TestResult(
                success=False,
                message="No URLs configured"
            )
        
        try:
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, urls[0])
            
            if feed.bozo:
                return TestResult(
                    success=False,
                    message=f"Feed has issues: {feed.bozo_exception}",
                    details={"bozo": True}
                )
            
            return TestResult(
                success=True,
                message=f"Feed loaded successfully, {len(feed.entries)} entries",
                details={
                    "feed_title": feed.feed.get("title", ""),
                    "entries_count": len(feed.entries),
                }
            )
        except Exception as e:
            return TestResult(
                success=False,
                message=f"Failed to fetch feed: {str(e)}"
            )
