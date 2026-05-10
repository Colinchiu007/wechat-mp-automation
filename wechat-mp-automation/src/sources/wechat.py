"""
微信公众号搜索数据源
"""

import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from src.sources.base import BaseSource, SourceConfig, SourceResult, TestResult, Content


class WechatSource(BaseSource):
    """微信公众号搜索数据源"""
    
    def __init__(self, config: SourceConfig):
        super().__init__(config)
        self.client = None
    
    async def connect(self) -> bool:
        """连接微信搜索服务"""
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
            }
        )
        return True
    
    async def collect(self, filters: dict[str, Any] | None = None) -> SourceResult:
        """采集微信公众号内容"""
        start_time = time.time()
        
        keywords = self.config.config.get("keywords", [])
        if not keywords:
            return SourceResult(
                success=False,
                error="No keywords configured for WeChat source"
            )
        
        all_contents = []
        errors = []
        
        for keyword in keywords:
            try:
                contents = await self._search_articles(keyword)
                all_contents.extend(contents)
            except Exception as e:
                errors.append(f"Error searching {keyword}: {str(e)}")
                logger.error(f"WeChat search error: {e}")
        
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
    
    async def _search_articles(self, keyword: str) -> list[Content]:
        """搜索微信文章"""
        contents = []
        
        try:
            # 使用微信搜狗搜索
            url = f"https://weixin.sogou.com/weixin"
            params = {
                "type": "2",  # 搜索文章
                "query": keyword,
                "ie": "utf8",
            }
            
            response = await self.client.get(url, params=params)
            soup = BeautifulSoup(response.text, "html.parser")
            
            # 解析搜索结果
            articles = soup.select("div.news-box li")
            if not articles:
                articles = soup.select("li.list_item")
            
            for article in articles[:20]:  # 限制数量
                try:
                    title_elem = article.select_one("div.info h3 a, h3 a")
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    url = title_elem.get("href", "")
                    
                    # 获取摘要
                    summary_elem = article.select_one("div.info p.txt-info, p.txt-info, div.desc")
                    summary = summary_elem.get_text(strip=True) if summary_elem else ""
                    
                    # 获取发布日期
                    date_elem = article.select_one("div.info .s2, span.s2, .account_box .s2")
                    published_at = None
                    if date_elem:
                        date_str = date_elem.get_text(strip=True)
                        published_at = self._parse_date(date_str)
                    
                    content = Content(
                        id=str(uuid.uuid4()),
                        source_id=self.config.id,
                        source_type="wechat_search",
                        url=url,
                        title=title,
                        content="",  # 需要进一步抓取
                        summary=summary,
                        published_at=published_at,
                        metadata={
                            "keyword": keyword,
                        }
                    )
                    contents.append(content)
                except Exception as e:
                    logger.warning(f"Error parsing article: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"WeChat search error: {e}")
        
        return contents
    
    def _parse_date(self, date_str: str) -> datetime | None:
        """解析日期"""
        from dateutil import parser
        
        try:
            # 尝试直接解析
            return parser.parse(date_str)
        except:
            # 处理相对时间格式
            now = datetime.now()
            if "分钟" in date_str:
                minutes = int(date_str.replace("分钟", "").replace("前", "").strip())
                return now - timedelta(minutes=minutes)
            elif "小时" in date_str:
                hours = int(date_str.replace("小时", "").replace("前", "").strip())
                return now - timedelta(hours=hours)
            elif "昨天" in date_str:
                return now - timedelta(days=1)
            elif "天" in date_str:
                days = int(date_str.replace("天", "").replace("前", "").strip())
                return now - timedelta(days=days)
        return None
    
    async def test(self) -> TestResult:
        """测试微信搜索"""
        keywords = self.config.config.get("keywords", ["测试"])
        
        try:
            results = await self._search_articles(keywords[0])
            return TestResult(
                success=True,
                message=f"Search successful, found {len(results)} articles",
                details={"count": len(results)}
            )
        except Exception as e:
            return TestResult(
                success=False,
                message=f"Search failed: {str(e)}"
            )
    
    async def close(self):
        """关闭连接"""
        if self.client:
            await self.client.aclose()
