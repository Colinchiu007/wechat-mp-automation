"""
知乎数据源
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


class ZhihuSource(BaseSource):
    """知乎数据源"""
    
    def __init__(self, config: SourceConfig):
        super().__init__(config)
        self.client = None
    
    async def connect(self) -> bool:
        """连接知乎"""
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.zhihu.com/",
            }
        )
        return True
    
    async def collect(self, filters: dict[str, Any] | None = None) -> SourceResult:
        """采集知乎内容"""
        start_time = time.time()
        
        source_type = self.config.config.get("type", "search")
        all_contents = []
        errors = []
        
        try:
            if source_type == "search":
                keywords = self.config.config.get("keywords", [])
                for keyword in keywords:
                    try:
                        contents = await self._search(keyword)
                        all_contents.extend(contents)
                    except Exception as e:
                        errors.append(f"Error searching {keyword}: {str(e)}")
                        
            elif source_type == "hot":
                try:
                    contents = await self._get_hot()
                    all_contents.extend(contents)
                except Exception as e:
                    errors.append(f"Error getting hot: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Zhihu collection error: {e}")
        
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
    
    async def _search(self, keyword: str) -> list[Content]:
        """搜索知乎"""
        contents = []
        
        try:
            url = "https://www.zhihu.com/api/v4/search_v3"
            params = {
                "t": "general",
                "q": keyword,
                "correction": "1",
                "offset": 0,
                "limit": 20,
                "filter_fields": "",
                "lc_idx": 0,
                "show_all_topics": "0",
            }
            
            response = await self.client.get(url, params=params)
            data = response.json()
            
            for item in data.get("data", []):
                try:
                    obj = item.get("object", {})
                    content_type = obj.get("type", "")
                    
                    if content_type == "answer":
                        content = Content(
                            id=str(uuid.uuid4()),
                            source_id=self.config.id,
                            source_type="zhihu_search",
                            url=obj.get("url", ""),
                            title=obj.get("question", {}).get("title", ""),
                            content=obj.get("excerpt", ""),
                            summary=self._truncate(obj.get("excerpt", ""), 200),
                            author=obj.get("author", {}).get("name", ""),
                            metadata={
                                "keyword": keyword,
                                "type": content_type,
                                "voteup_count": obj.get("voteup_count", 0),
                                "comment_count": obj.get("comment_count", 0),
                            }
                        )
                        contents.append(content)
                        
                    elif content_type == "article":
                        content = Content(
                            id=str(uuid.uuid4()),
                            source_id=self.config.id,
                            source_type="zhihu_search",
                            url=obj.get("url", ""),
                            title=obj.get("title", ""),
                            content=obj.get("excerpt", ""),
                            summary=self._truncate(obj.get("excerpt", ""), 200),
                            author=obj.get("author", {}).get("name", ""),
                            metadata={
                                "keyword": keyword,
                                "type": content_type,
                                "voteup_count": obj.get("voteup_count", 0),
                            }
                        )
                        contents.append(content)
                        
                except Exception as e:
                    logger.warning(f"Error parsing Zhihu item: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Zhihu search error: {e}")
        
        return contents
    
    async def _get_hot(self) -> list[Content]:
        """获取知乎热榜"""
        contents = []
        
        try:
            url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"
            response = await self.client.get(url)
            data = response.json()
            
            for item in data.get("data", []):
                try:
                    content = Content(
                        id=str(uuid.uuid4()),
                        source_id=self.config.id,
                        source_type="zhihu_hot",
                        url=f"https://www.zhihu.com/question/{item.get('target', {}).get('id', '')}",
                        title=item.get("target", {}).get("title", ""),
                        content=item.get("target", {}).get("excerpt", ""),
                        summary=item.get("brief", ""),
                        metadata={
                            "type": "hot",
                            "visit_count": item.get("target", {}).get("visit_count", {}).get("count", 0),
                            "follower_count": item.get("target", {}).get("follower_count", 0),
                        }
                    )
                    contents.append(content)
                except Exception as e:
                    logger.warning(f"Error parsing hot item: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Zhihu hot error: {e}")
        
        return contents
    
    def _truncate(self, text: str, length: int) -> str:
        """截断文本"""
        if len(text) <= length:
            return text
        return text[:length] + "..."
    
    async def test(self) -> TestResult:
        """测试知乎连接"""
        try:
            url = "https://www.zhihu.com"
            response = await self.client.get(url)
            return TestResult(
                success=response.status_code == 200,
                message=f"Zhihu accessible, status: {response.status_code}",
                details={"status_code": response.status_code}
            )
        except Exception as e:
            return TestResult(
                success=False,
                message=f"Failed to connect: {str(e)}"
            )
    
    async def close(self):
        """关闭连接"""
        if self.client:
            await self.client.aclose()
