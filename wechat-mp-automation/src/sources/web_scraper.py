"""
网页爬虫数据源
"""

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from src.sources.base import BaseSource, SourceConfig, SourceResult, TestResult, Content


class WebScraperSource(BaseSource):
    """网页爬虫数据源"""
    
    def __init__(self, config: SourceConfig):
        super().__init__(config)
        self.client = None
    
    async def connect(self) -> bool:
        """连接网页"""
        self.client = httpx.AsyncClient(
            timeout=self.config.config.get("timeout", 30.0),
            headers=self.config.config.get("headers", {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
        )
        return True
    
    async def collect(self, filters: dict[str, Any] | None = None) -> SourceResult:
        """采集网页内容"""
        start_time = time.time()
        
        base_url = self.config.config.get("url")
        if not base_url:
            return SourceResult(
                success=False,
                error="No URL configured for web scraper source"
            )
        
        all_contents = []
        errors = []
        
        try:
            contents = await self._scrape_page(base_url)
            all_contents.extend(contents)
            
            # 处理分页
            pagination = self.config.config.get("pagination", {})
            if pagination.get("enabled", False):
                next_button = pagination.get("next_button")
                max_pages = pagination.get("max_pages", 5)
                
                for page in range(1, max_pages + 1):
                    try:
                        # 获取下一页按钮
                        next_url = await self._find_next_page(base_url, next_button)
                        if not next_url:
                            break
                        
                        page_contents = await self._scrape_page(next_url)
                        all_contents.extend(page_contents)
                        
                    except Exception as e:
                        logger.warning(f"Error scraping page {page}: {e}")
                        errors.append(f"Page {page}: {str(e)}")
                        
        except Exception as e:
            logger.error(f"Web scraper error: {e}")
            errors.append(str(e))
        
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
    
    async def _scrape_page(self, url: str) -> list[Content]:
        """爬取单个页面"""
        contents = []
        
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # 选择器配置
            selectors = self.config.config.get("select", {})
            
            # 查找文章列表
            article_selector = selectors.get("article", "article, .post, .entry, .item")
            articles = soup.select(article_selector)
            
            if not articles:
                # 如果没有找到文章列表，尝试将整个页面作为一篇文章
                articles = [soup]
            
            for article in articles:
                try:
                    # 提取标题
                    title_selector = selectors.get("title", "h1, h2, .title")
                    title_elem = article.select_one(title_selector)
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    
                    if not title:
                        continue
                    
                    # 提取内容
                    content_selector = selectors.get("content", ".content, .entry-content, .post-content, p")
                    content_elem = article.select_one(content_selector)
                    if not content_elem:
                        content_elem = article
                    content_text = content_elem.get_text(separator="\n", strip=True)
                    
                    # 提取日期
                    date_selector = selectors.get("date", "time, .date, .published")
                    date_elem = article.select_one(date_selector)
                    published_at = None
                    if date_elem:
                        date_str = date_elem.get("datetime") or date_elem.get_text(strip=True)
                        try:
                            from dateutil import parser
                            published_at = parser.parse(date_str)
                        except:
                            pass
                    
                    # 提取作者
                    author_selector = selectors.get("author", ".author, .byline")
                    author_elem = article.select_one(author_selector)
                    author = author_elem.get_text(strip=True) if author_elem else ""
                    
                    # 提取链接
                    link_elem = article.select_one("a")
                    article_url = link_elem.get("href", "") if link_elem else url
                    if not article_url.startswith("http"):
                        from urllib.parse import urljoin
                        article_url = urljoin(url, article_url)
                    
                    content = Content(
                        id=str(uuid.uuid4()),
                        source_id=self.config.id,
                        source_type="web_scraping",
                        url=article_url,
                        title=title,
                        content=content_text,
                        summary=self._truncate(content_text, 200),
                        author=author,
                        published_at=published_at,
                        metadata={
                            "scraped_url": url,
                        },
                        raw_data={
                            "html": str(article)[:1000],  # 保存部分 HTML
                        }
                    )
                    contents.append(content)
                    
                except Exception as e:
                    logger.warning(f"Error parsing article: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
        
        return contents
    
    async def _find_next_page(self, current_url: str, next_button: str) -> str | None:
        """查找下一页 URL"""
        try:
            response = await self.client.get(current_url)
            soup = BeautifulSoup(response.text, "html.parser")
            
            next_elem = soup.select_one(next_button)
            if next_elem:
                href = next_elem.get("href")
                if href:
                    from urllib.parse import urljoin
                    return urljoin(current_url, href)
                    
        except Exception as e:
            logger.warning(f"Error finding next page: {e}")
        
        return None
    
    def _truncate(self, text: str, length: int) -> str:
        """截断文本"""
        if len(text) <= length:
            return text
        return text[:length] + "..."
    
    async def test(self) -> TestResult:
        """测试网页爬虫"""
        base_url = self.config.config.get("url")
        
        try:
            response = await self.client.get(base_url)
            soup = BeautifulSoup(response.text, "html.parser")
            
            selectors = self.config.config.get("select", {})
            article_selector = selectors.get("article", "article, .post, .entry")
            articles = soup.select(article_selector)
            
            return TestResult(
                success=True,
                message=f"Page accessible, found {len(articles)} article elements",
                details={
                    "status_code": response.status_code,
                    "article_count": len(articles),
                }
            )
        except Exception as e:
            return TestResult(
                success=False,
                message=f"Failed to scrape page: {str(e)}"
            )
    
    async def close(self):
        """关闭连接"""
        if self.client:
            await self.client.aclose()
