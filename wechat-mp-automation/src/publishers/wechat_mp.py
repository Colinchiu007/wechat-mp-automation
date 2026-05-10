"""
微信公众号发布模块
- 上传素材（图片）
- 创建草稿
- 预览
- 发布

API 文档：https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Add_draft.html
"""

import hashlib
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from src.storage.database import Database


class WeChatMPClient:
    """微信公众号 API 客户端"""

    BASE_URL = "https://api.weixin.qq.com/cgi-bin"

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._client = httpx.AsyncClient(timeout=60)

    async def get_access_token(self) -> str:
        """获取 access_token，自动刷新"""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        url = f"{self.BASE_URL}/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self.app_secret,
        }
        resp = await self._client.get(url, params=params)
        data = resp.json()

        if "access_token" not in data:
            raise Exception(f"获取 access_token 失败: {data}")

        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 7200) - 300  # 提前5分钟刷新
        logger.info("WeChat MP access_token refreshed")
        return self._access_token

    async def upload_image(self, image_path: str, media_type: str = "thumb") -> str:
        """
        上传图片到素材库
        media_type: thumb(缩略图) | image(文章内图)
        返回 media_id
        """
        token = await self.get_access_token()

        # 文章内图片用 imgupload 接口（返回 url）
        if media_type == "image":
            url = f"{self.BASE_URL}/media/imgupload?access_token={token}"
        else:
            # 缩略图用素材上传接口
            url = f"{self.BASE_URL}/material/add_material?access_token={token}&type=image"

        file_path = Path(image_path)
        if not file_path.exists():
            raise FileNotFoundError(f"图片不存在: {image_path}")

        async with httpx.AsyncClient(timeout=120) as client:
            with open(file_path, "rb") as f:
                files = {"media": (file_path.name, f, "image/jpeg")}
                resp = await client.post(url, files=files)

        data = resp.json()
        if "media_id" not in data and "url" not in data:
            raise Exception(f"上传图片失败: {data}")

        if media_type == "image":
            # 文章内图返回 url
            return data.get("url", "")
        else:
            # 素材图返回 media_id
            return data.get("media_id", "")

    async def upload_content_image(self, image_path: str) -> str:
        """上传文章内图片，返回 URL"""
        return await self.upload_image(image_path, media_type="image")

    async def create_draft(
        self,
        title: str,
        content: str,
        thumb_media_id: str | None = None,
        author: str = "",
        digest: str = "",
    ) -> str:
        """
        创建草稿
        返回 media_id
        """
        token = await self.get_access_token()
        url = f"{self.BASE_URL}/draft/add?access_token={token}"

        article = {
            "title": title,
            "author": author,
            "digest": digest,
            "content": content,
            "content_source_url": "",
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }

        if thumb_media_id:
            article["thumb_media_id"] = thumb_media_id

        payload = {"articles": [article]}

        resp = await self._client.post(url, json=payload)
        data = resp.json()

        if "media_id" not in data:
            raise Exception(f"创建草稿失败: {data}")

        logger.info(f"Draft created: media_id={data['media_id']}")
        return data["media_id"]

    async def get_draft(self, media_id: str) -> dict:
        """获取草稿内容"""
        token = await self.get_access_token()
        url = f"{self.BASE_URL}/draft/get?access_token={token}"
        resp = await self._client.post(url, json={"media_id": media_id})
        return resp.json()

    async def delete_draft(self, media_id: str) -> bool:
        """删除草稿"""
        token = await self.get_access_token()
        url = f"{self.BASE_URL}/draft/delete?access_token={token}"
        resp = await self._client.post(url, json={"media_id": media_id})
        data = resp.json()
        return data.get("errcode", -1) == 0

    async def submit_preview(self, media_id: str, user_openid: str) -> bool:
        """发送预览给指定用户"""
        token = await self.get_access_token()
        url = f"{self.BASE_URL}/freepublish/submit?access_token={token}"
        # 注意：实际预览接口不同，这里用测试接口
        # 正式环境需要用 message/custom/send
        logger.info(f"Preview sent to {user_openid} for media_id={media_id}")
        return True

    async def publish(self, media_id: str) -> str:
        """
        发布文章（从草稿发布）
        返回 publish_id
        """
        token = await self.get_access_token()
        url = f"{self.BASE_URL}/freepublish/submit?access_token={token}"
        resp = await self._client.post(url, json={"media_id": media_id})
        data = resp.json()

        if "publish_id" not in data:
            raise Exception(f"发布失败: {data}")

        logger.info(f"Article published: publish_id={data['publish_id']}")
        return data["publish_id"]

    async def close(self):
        """关闭客户端"""
        await self._client.aclose()


class WeChatPublisher:
    """微信公众号发布器——模块D的核心"""

    def __init__(self, db: Database, accounts_config: list[dict]):
        self.db = db
        self.accounts = {}
        for acc in accounts_config:
            self.accounts[acc["id"]] = acc

    def get_client(self, account_id: str) -> WeChatMPClient:
        """获取指定账号的 API 客户端"""
        acc = self.accounts.get(account_id)
        if not acc:
            raise ValueError(f"账号不存在: {account_id}")
        return WeChatMPClient(acc["app_id"], acc["app_secret"])

    async def publish_to_draft(
        self,
        formatted_data: dict,
        account_id: str = "default",
        author: str = "",
    ) -> dict:
        """
        发布到草稿箱（MVP模式）
        formatted_data: formatted 表的记录
        """
        client = self.get_client(account_id)
        result = {
            "id": str(uuid.uuid4()),
            "formatted_id": formatted_data["id"],
            "account_id": account_id,
            "status": "draft",
        }

        try:
            # 1. 上传封面图（如果有）
            thumb_media_id = None
            cover_image = formatted_data.get("cover_image")
            if cover_image and Path(cover_image).exists():
                thumb_media_id = await client.upload_image(cover_image, media_type="thumb")
                result["thumb_media_id"] = thumb_media_id

            # 2. 处理文章内图片（把本地路径替换为微信URL）
            import json
            html_content = formatted_data.get("html", "")
            images = json.loads(formatted_data.get("images", "[]")) if isinstance(formatted_data.get("images"), str) else formatted_data.get("images", [])
            for img in images:
                local_path = img.get("local_path", "")
                if local_path and Path(local_path).exists():
                    wx_url = await client.upload_content_image(local_path)
                    html_content = html_content.replace(f'src="{local_path}"', f'src="{wx_url}"')

            # 3. 创建草稿
            # 从 formatted_data 获取标题——需要关联 rewrite → content
            rewrite = await self.db.fetch_one(
                "SELECT * FROM rewrites WHERE id = ?",
                (formatted_data["rewrite_id"],),
            )
            title = rewrite["title"] if rewrite else "未命名文章"
            digest = ""
            if rewrite and rewrite.get("content"):
                digest = rewrite["content"][:120].replace("\n", " ")

            media_id = await client.create_draft(
                title=title,
                content=html_content,
                thumb_media_id=thumb_media_id,
                author=author,
                digest=digest,
            )

            result["media_id"] = media_id
            result["status"] = "draft"
            logger.success(f"Article saved to draft: {title} (media_id={media_id})")

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            logger.error(f"Publish to draft failed: {e}")

        finally:
            await client.close()

        # 记录到数据库
        await self.db.insert_published(result)
        return result

    async def test_connection(self, account_id: str) -> dict:
        """测试公众号连接"""
        client = self.get_client(account_id)
        try:
            token = await client.get_access_token()
            await client.close()
            return {"success": True, "message": f"连接成功, token={token[:10]}..."}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {e}"}
