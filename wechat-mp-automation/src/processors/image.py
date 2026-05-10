"""
图像处理器
"""

import asyncio
import base64
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
from loguru import logger


class ImageProvider(Enum):
    """图像提供商"""
    DALLE = "dalle"
    MIDJOURNEY = "midjourney"
    STABLE_DIFFUSION = "stable_diffusion"
    FLUX = "flux"
    UNSPLASH = "unsplash"
    PEXELS = "pexels"
    SCREENSHOT = "screenshot"


@dataclass
class ImageConfig:
    """图像配置"""
    provider: ImageProvider = ImageProvider.DALLE
    count: int = 3
    strategy: str = "auto"  # auto | fixed | dynamic
    style: str = "modern minimalist"
    size: str = "1024x1024"
    quality: str = "standard"


@dataclass
class GeneratedImage:
    """生成的图像"""
    id: str
    url: str | None = None
    local_path: str | None = None
    prompt: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ImageResult:
    """图像生成结果"""
    success: bool
    images: list[GeneratedImage] = field(default_factory=list)
    error: str | None = None
    metadata: dict = field(default_factory=dict)


class ImageProcessor:
    """图像处理器"""
    
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.image_config = config.get("image_gen", {})
        self.client = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.client = httpx.AsyncClient(timeout=60.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.client:
            await self.client.aclose()
    
    async def generate(
        self,
        title: str,
        content: str = "",
        config: ImageConfig | None = None
    ) -> ImageResult:
        """生成图像"""
        if config is None:
            config = ImageConfig()
        
        try:
            provider = ImageProvider(config.provider.value if isinstance(config.provider, ImageProvider) else config.provider)
            
            if provider == ImageProvider.DALLE:
                return await self._generate_dalle(title, content, config)
            elif provider == ImageProvider.UNSPLASH:
                return await self._generate_unsplash(title, config)
            elif provider == ImageProvider.PEXELS:
                return await self._generate_pexels(title, config)
            elif provider == ImageProvider.SCREENSHOT:
                url = config.metadata.get("url", "")
                if url:
                    return await self._take_screenshot(url, config)
                else:
                    return ImageResult(success=False, error="URL required for screenshot")
            else:
                return ImageResult(success=False, error=f"Unsupported provider: {provider}")
                
        except Exception as e:
            logger.error(f"Image generation error: {e}")
            return ImageResult(success=False, error=str(e))
    
    async def _generate_dalle(
        self,
        title: str,
        content: str,
        config: ImageConfig
    ) -> ImageResult:
        """使用 DALL-E 生成图像"""
        dalle_config = self.image_config.get("providers", {}).get("dalle", {})
        api_key = dalle_config.get("api_key") or self.image_config.get("dalle_api_key")
        
        if not api_key:
            return ImageResult(success=False, error="DALL-E API key not configured")
        
        # 构建提示词
        prompt = self._build_image_prompt(title, content, config)
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": min(config.count, 10),
            "size": config.size,
            "quality": config.quality,
            "style": "natural" if "realistic" in config.style else "vivid"
        }
        
        try:
            response = await self.client.post(
                "https://api.openai.com/v1/images/generations",
                json=data,
                headers=headers
            )
            
            if response.status_code != 200:
                return ImageResult(success=False, error=f"API error: {response.status_code}")
            
            result = response.json()
            
            images = []
            for item in result.get("data", []):
                img = GeneratedImage(
                    id=str(uuid.uuid4()),
                    url=item.get("url"),
                    prompt=prompt,
                    metadata=item
                )
                images.append(img)
            
            return ImageResult(
                success=True,
                images=images,
                metadata={"prompt": prompt}
            )
            
        except Exception as e:
            logger.error(f"DALL-E generation error: {e}")
            return ImageResult(success=False, error=str(e))
    
    async def _generate_unsplash(
        self,
        title: str,
        config: ImageConfig
    ) -> ImageResult:
        """从 Unsplash 获取图像"""
        unsplash_config = self.image_config.get("providers", {}).get("unsplash", {})
        api_key = unsplash_config.get("api_key") or self.image_config.get("unsplash_api_key")
        
        if not api_key:
            return ImageResult(success=False, error="Unsplash API key not configured")
        
        try:
            params = {
                "query": title,
                "per_page": config.count,
                "orientation": self._get_unsplash_orientation(config.size)
            }
            
            headers = {"Authorization": f"Client-ID {api_key}"}
            
            response = await self.client.get(
                "https://api.unsplash.com/search/photos",
                params=params,
                headers=headers
            )
            
            if response.status_code != 200:
                return ImageResult(success=False, error=f"API error: {response.status_code}")
            
            result = response.json()
            
            images = []
            for item in result.get("results", []):
                img = GeneratedImage(
                    id=item.get("id", str(uuid.uuid4())),
                    url=item.get("urls", {}).get("regular"),
                    prompt=title,
                    metadata={
                        "author": item.get("user", {}).get("name"),
                        "source": "unsplash",
                        "download_url": item.get("links", {}).get("download")
                    }
                )
                images.append(img)
            
            return ImageResult(
                success=True,
                images=images,
                metadata={"query": title}
            )
            
        except Exception as e:
            logger.error(f"Unsplash error: {e}")
            return ImageResult(success=False, error=str(e))
    
    async def _generate_pexels(
        self,
        title: str,
        config: ImageConfig
    ) -> ImageResult:
        """从 Pexels 获取图像"""
        pexels_config = self.image_config.get("providers", {}).get("pexels", {})
        api_key = pexels_config.get("api_key") or self.image_config.get("pexels_api_key")
        
        if not api_key:
            return ImageResult(success=False, error="Pexels API key not configured")
        
        try:
            params = {
                "query": title,
                "per_page": config.count,
                "orientation": self._get_pexels_orientation(config.size)
            }
            
            headers = {"Authorization": api_key}
            
            response = await self.client.get(
                "https://api.pexels.com/v1/search",
                params=params,
                headers=headers
            )
            
            if response.status_code != 200:
                return ImageResult(success=False, error=f"API error: {response.status_code}")
            
            result = response.json()
            
            images = []
            for item in result.get("photos", []):
                img = GeneratedImage(
                    id=str(item.get("id")),
                    url=item.get("src", {}).get("original"),
                    prompt=title,
                    metadata={
                        "author": item.get("photographer"),
                        "source": "pexels",
                        "alt": item.get("alt")
                    }
                )
                images.append(img)
            
            return ImageResult(
                success=True,
                images=images,
                metadata={"query": title}
            )
            
        except Exception as e:
            logger.error(f"Pexels error: {e}")
            return ImageResult(success=False, error=str(e))
    
    async def _take_screenshot(
        self,
        url: str,
        config: ImageConfig
    ) -> ImageResult:
        """截取网页截图"""
        try:
            # 使用 Playwright 或其他截图工具
            # 这里先返回错误，需要安装 Playwright
            return ImageResult(
                success=False,
                error="Screenshot requires Playwright installation. Use image library instead."
            )
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return ImageResult(success=False, error=str(e))
    
    def _build_image_prompt(
        self,
        title: str,
        content: str,
        config: ImageConfig
    ) -> str:
        """构建图像生成提示词"""
        style_map = {
            "modern minimalist": "modern minimalist style, clean design, simple",
            "realistic": "photorealistic, high quality, detailed",
            "abstract": "abstract art, colorful, creative",
            "professional": "professional, business, clean",
        }
        
        style_desc = style_map.get(config.style, config.style)
        
        # 从内容中提取关键词
        keywords = self._extract_keywords(content)
        
        prompt = f"{title}, {style_desc}"
        if keywords:
            prompt += f", {', '.join(keywords[:5])}"
        
        prompt += ", no text, no watermark, high quality"
        
        return prompt
    
    def _extract_keywords(self, content: str) -> list[str]:
        """提取关键词"""
        # 简单的关键词提取
        import re
        
        # 移除标点符号
        text = re.sub(r"[^\w\s]", " ", content)
        
        # 移除常见停用词
        stopwords = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这"}
        
        # 提取2-4个字的词
        words = re.findall(r"[\u4e00-\u9fa5]{2,4}", text)
        word_freq = {}
        
        for word in words:
            if word not in stopwords:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # 按频率排序
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        
        return [word for word, freq in sorted_words[:10]]
    
    def _get_unsplash_orientation(self, size: str) -> str:
        """获取 Unsplash 方向参数"""
        if "x" in size:
            w, h = size.split("x")
            w, h = int(w), int(h)
            if h > w:
                return "portrait"
            elif w > h:
                return "landscape"
            else:
                return "squarish"
        return "squarish"
    
    def _get_pexels_orientation(self, size: str) -> str:
        """获取 Pexels 方向参数"""
        if "x" in size:
            w, h = size.split("x")
            w, h = int(w), int(h)
            if h > w:
                return "portrait"
            elif w > h:
                return "landscape"
            else:
                return "square"
        return "square"
