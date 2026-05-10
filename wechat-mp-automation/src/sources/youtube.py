"""
YouTube 数据源
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
from loguru import logger

from src.sources.base import BaseSource, SourceConfig, SourceResult, TestResult, Content


class YoutubeSource(BaseSource):
    """YouTube 数据源"""
    
    def __init__(self, config: SourceConfig):
        super().__init__(config)
        self.client = None
        self.api_key = config.config.get("api_key", "")
    
    async def connect(self) -> bool:
        """连接 YouTube API"""
        self.client = httpx.AsyncClient(timeout=30.0)
        return True
    
    async def collect(self, filters: dict[str, Any] | None = None) -> SourceResult:
        """采集 YouTube 内容"""
        start_time = time.time()
        
        source_type = self.config.config.get("type", "search")
        all_contents = []
        errors = []
        
        try:
            if source_type == "search":
                query = self.config.config.get("search_query", "")
                if query:
                    contents = await self._search_videos(query)
                    all_contents.extend(contents)
                    
            elif source_type == "trending":
                region = self.config.config.get("region", "US")
                category = self.config.config.get("category", "")
                contents = await self._get_trending(region, category)
                all_contents.extend(contents)
                
            elif source_type == "channel":
                channel_id = self.config.config.get("channel_id", "")
                if channel_id:
                    contents = await self._get_channel_videos(channel_id)
                    all_contents.extend(contents)
                    
        except Exception as e:
            logger.error(f"YouTube collection error: {e}")
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
    
    async def _search_videos(self, query: str) -> list[Content]:
        """搜索视频"""
        contents = []
        
        if not self.api_key:
            logger.warning("YouTube API key not configured, using web scraping fallback")
            return await self._search_videos_web(query)
        
        try:
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": self.config.config.get("max_results", 20),
                "order": self.config.config.get("order", "viewCount"),
                "key": self.api_key,
            }
            
            if self.config.config.get("region"):
                params["regionCode"] = self.config.config.get("region")
            
            response = await self.client.get(url, params=params)
            data = response.json()
            
            for item in data.get("items", []):
                try:
                    snippet = item.get("snippet", {})
                    video_id = item.get("id", {}).get("videoId", "")
                    
                    content = Content(
                        id=str(uuid.uuid4()),
                        source_id=self.config.id,
                        source_type="youtube_search",
                        url=f"https://www.youtube.com/watch?v={video_id}",
                        title=snippet.get("title", ""),
                        content=snippet.get("description", ""),
                        summary=self._truncate(snippet.get("description", ""), 200),
                        author=snippet.get("channelTitle", ""),
                        published_at=datetime.fromisoformat(
                            snippet.get("publishedAt", "").replace("Z", "+00:00")
                        ) if snippet.get("publishedAt") else None,
                        metadata={
                            "query": query,
                            "video_id": video_id,
                            "channel_id": snippet.get("channelId", ""),
                            "thumbnails": snippet.get("thumbnails", {}),
                        }
                    )
                    contents.append(content)
                except Exception as e:
                    logger.warning(f"Error parsing video: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"YouTube search API error: {e}")
        
        return contents
    
    async def _search_videos_web(self, query: str) -> list[Content]:
        """使用网页抓取搜索视频（无 API Key 时的后备方案）"""
        contents = []
        
        try:
            # YouTube 搜索页面
            url = f"https://www.youtube.com/results"
            params = {"search_query": query}
            
            from bs4 import BeautifulSoup
            response = await self.client.get(url, params=params)
            soup = BeautifulSoup(response.text, "html.parser")
            
            # 解析视频结果
            videos = soup.select("ytd-video-renderer, ytd-rich-item-renderer")
            
            for video in videos[:20]:
                try:
                    title_elem = video.select_one("a#video-title, h3 a")
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    video_url = "https://www.youtube.com" + title_elem.get("href", "")
                    
                    # 提取 video ID
                    import re
                    video_id_match = re.search(r"v=([a-zA-Z0-9_-]+)", video_url)
                    if not video_id_match:
                        continue
                    video_id = video_id_match.group(1)
                    
                    # 获取描述
                    desc_elem = video.select_one("span#description-text")
                    description = desc_elem.get_text(strip=True) if desc_elem else ""
                    
                    content = Content(
                        id=str(uuid.uuid4()),
                        source_id=self.config.id,
                        source_type="youtube_search",
                        url=video_url,
                        title=title,
                        content=description,
                        summary=self._truncate(description, 200),
                        metadata={
                            "query": query,
                            "video_id": video_id,
                        }
                    )
                    contents.append(content)
                except Exception as e:
                    logger.warning(f"Error parsing video element: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"YouTube web search error: {e}")
        
        return contents
    
    async def _get_trending(self, region: str = "US", category: str = "") -> list[Content]:
        """获取热门视频"""
        contents = []
        
        if not self.api_key:
            logger.warning("YouTube API key required for trending")
            return contents
        
        try:
            url = "https://www.googleapis.com/youtube/v3/videos"
            params = {
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": region,
                "maxResults": 20,
                "key": self.api_key,
            }
            
            if category:
                params["videoCategoryId"] = category
            
            response = await self.client.get(url, params=params)
            data = response.json()
            
            for item in data.get("items", []):
                try:
                    snippet = item.get("snippet", {})
                    stats = item.get("statistics", {})
                    video_id = item.get("id", "")
                    
                    content = Content(
                        id=str(uuid.uuid4()),
                        source_id=self.config.id,
                        source_type="youtube_trending",
                        url=f"https://www.youtube.com/watch?v={video_id}",
                        title=snippet.get("title", ""),
                        content=snippet.get("description", ""),
                        summary=self._truncate(snippet.get("description", ""), 200),
                        author=snippet.get("channelTitle", ""),
                        published_at=datetime.fromisoformat(
                            snippet.get("publishedAt", "").replace("Z", "+00:00")
                        ) if snippet.get("publishedAt") else None,
                        metadata={
                            "region": region,
                            "category": snippet.get("categoryId", ""),
                            "video_id": video_id,
                            "view_count": stats.get("viewCount", "0"),
                            "like_count": stats.get("likeCount", "0"),
                        }
                    )
                    contents.append(content)
                except Exception as e:
                    logger.warning(f"Error parsing trending video: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"YouTube trending error: {e}")
        
        return contents
    
    async def _get_channel_videos(self, channel_id: str) -> list[Content]:
        """获取频道视频"""
        contents = []
        
        if not self.api_key:
            logger.warning("YouTube API key required for channel videos")
            return contents
        
        try:
            # 获取频道上传视频的播放列表
            channel_url = "https://www.googleapis.com/youtube/v3/channels"
            channel_params = {
                "part": "contentDetails",
                "id": channel_id,
                "key": self.api_key,
            }
            
            channel_response = await self.client.get(channel_url, params=channel_params)
            channel_data = channel_response.json()
            
            uploads_id = channel_data.get("items", [{}])[0].get(
                "contentDetails", {}
            ).get("relatedPlaylists", {}).get("uploads", "")
            
            if not uploads_id:
                return contents
            
            # 获取播放列表中的视频
            playlist_url = "https://www.googleapis.com/youtube/v3/playlistItems"
            playlist_params = {
                "part": "snippet",
                "playlistId": uploads_id,
                "maxResults": 20,
                "key": self.api_key,
            }
            
            playlist_response = await self.client.get(playlist_url, params=playlist_params)
            playlist_data = playlist_response.json()
            
            for item in playlist_data.get("items", []):
                try:
                    snippet = item.get("snippet", {})
                    video_id = snippet.get("resourceId", {}).get("videoId", "")
                    
                    content = Content(
                        id=str(uuid.uuid4()),
                        source_id=self.config.id,
                        source_type="youtube_channel",
                        url=f"https://www.youtube.com/watch?v={video_id}",
                        title=snippet.get("title", ""),
                        content=snippet.get("description", ""),
                        summary=self._truncate(snippet.get("description", ""), 200),
                        author=snippet.get("channelTitle", ""),
                        published_at=datetime.fromisoformat(
                            snippet.get("publishedAt", "").replace("Z", "+00:00")
                        ) if snippet.get("publishedAt") else None,
                        metadata={
                            "channel_id": channel_id,
                            "video_id": video_id,
                        }
                    )
                    contents.append(content)
                except Exception as e:
                    logger.warning(f"Error parsing channel video: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"YouTube channel error: {e}")
        
        return contents
    
    def _truncate(self, text: str, length: int) -> str:
        """截断文本"""
        if len(text) <= length:
            return text
        return text[:length] + "..."
    
    async def test(self) -> TestResult:
        """测试 YouTube 连接"""
        try:
            if self.api_key:
                url = "https://www.googleapis.com/youtube/v3/channels"
                params = {"part": "snippet", "id": "UC_x5XG1OV2P6uZZ5FSM9Ttw", "key": self.api_key}
                response = await self.client.get(url, params=params)
                data = response.json()
                
                if "items" in data:
                    return TestResult(
                        success=True,
                        message="YouTube API connection successful",
                        details={"api_key_valid": True}
                    )
                else:
                    return TestResult(
                        success=False,
                        message="YouTube API key invalid",
                        details=data
                    )
            else:
                return TestResult(
                    success=True,
                    message="YouTube API key not configured, using web scraping",
                    details={"api_key_configured": False}
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
