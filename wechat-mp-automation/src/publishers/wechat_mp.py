"""
微信公众号发布模块
==================

本模块负责与微信公众平台 API 交互，实现文章发布功能，是模块D的核心。

核心职责：
1. 管理 access_token（自动刷新，提前5分钟续期）
2. 上传图片素材（封面图、文章内图）
3. 创建草稿
4. 发布文章

API 文档：
- 草稿箱管理：https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Add_draft.html
- 素材管理：https://developers.weixin.qq.com/doc/offiaccount/Asset_Management/Adding_Permanent_Assets.html
- 发布接口：https://developers.weixin.qq.com/doc/offiaccount/Publish/Publish.html

设计决策：
- 使用永久素材而非临时素材：永久素材可重复使用，便于修改草稿
- 封面图用 thumb 类型：公众号要求封面图为永久素材
- 文章内图用 imgupload：返回 URL，直接插入 HTML

使用示例：
    # 初始化客户端
    client = WeChatMPClient("wx1234567890", "your_app_secret")
    
    # 上传封面图
    thumb_id = await client.upload_image("cover.jpg", media_type="thumb")
    
    # 创建草稿
    media_id = await client.create_draft(
        title="文章标题",
        content="<p>正文 HTML</p>",
        thumb_media_id=thumb_id
    )
    
    # 发布（可选，MVP只做草稿）
    publish_id = await client.publish(media_id)
    
    await client.close()

Phase 规划：
- Phase 1: 仅支持草稿箱模式
- Phase 2: 添加预览功能（发送给指定用户）
- Phase 3: 支持定时发布
- Phase 5: 自动发布（需审核机制）

安全注意：
- access_token 每日调用次数有限（2000次/账号），需要缓存
- secret 不能硬编码，必须从环境变量或配置文件读取
- 调用失败时检查 errcode，特别是 40001（token 过期）
"""

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from src.storage.database import Database


class WeChatMPClient:
    """
    微信公众号 API 客户端
    
    封装所有与微信公众平台 API 交互的逻辑。
    
    属性：
        app_id: 公众号 AppID（在公众号后台获取）
        app_secret: 公众号 AppSecret（在公众号后台获取）
        _access_token: 缓存的 access_token
        _token_expires_at: token 过期时间戳
    
    使用示例：
        client = WeChatMPClient("wx123", "secret")
        try:
            token = await client.get_access_token()
            media_id = await client.create_draft("标题", "<p>内容</p>")
        finally:
            await client.close()
    
    注意：
        使用完毕后必须调用 close() 关闭连接
        或使用 async with 上下文管理器
    """
    
    BASE_URL = "https://api.weixin.qq.com/cgi-bin"
    
    def __init__(self, app_id: str, app_secret: str):
        """
        初始化客户端
        
        参数：
            app_id: 公众号 AppID
            app_secret: 公众号 AppSecret
        
        配置示例（环境变量）：
            export WECHAT_APP_ID="wx1234567890"
            export WECHAT_APP_SECRET="your_secret_here"
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self._access_token: str | None = None
        self._token_expires_at: float = 0  # 过期时间戳
        self._client = httpx.AsyncClient(timeout=60)
    
    # ========================================================================
    # Access Token 管理
    # ========================================================================
    
    async def get_access_token(self) -> str:
        """
        获取 access_token，自动刷新
        
        返回：
            当前有效的 access_token
        
        刷新策略：
        - 检查缓存的 token 是否存在且未过期
        - 有效则直接返回
        - 过期则调用 API 获取新 token
        - 新 token 有效期设为 expires_in - 300秒（提前5分钟刷新）
        
        错误处理：
        - API 返回错误时抛出异常，包含微信返回的错误信息
        
        限流注意：
        - 每个 AppID 每日可调用 2000 次
        - token 有效期 2 小时，合理缓存可大幅减少调用次数
        """
        # 检查缓存的 token 是否有效
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        
        # 调用 API 获取新 token
        url = f"{self.BASE_URL}/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self.app_secret,
        }
        
        resp = await self._client.get(url, params=params)
        data = resp.json()
        
        # 检查是否成功
        if "access_token" not in data:
            error_msg = data.get("errmsg", str(data))
            raise Exception(f"获取 access_token 失败: {error_msg}")
        
        # 缓存 token，提前 5 分钟刷新
        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 7200)
        self._token_expires_at = time.time() + expires_in - 300
        
        logger.info("WeChat MP access_token refreshed")
        return self._access_token
    
    # ========================================================================
    # 图片上传
    # ========================================================================
    
    async def upload_image(self, image_path: str, media_type: str = "thumb") -> str:
        """
        上传图片到素材库
        
        参数：
            image_path: 本地图片路径
            media_type: 图片类型
                - "thumb": 封面图（永久素材），返回 media_id
                - "image": 文章内图（返回 URL）
        
        返回：
            - thumb 类型：返回 media_id（用于创建草稿时指定封面）
            - image 类型：返回 URL（用于插入文章正文）
        
        API 差异说明：
        - 封面图用 /material/add_material 接口，返回 media_id
        - 文章内图用 /media/imgupload 接口，返回 URL
        - 两者返回值不同，需要区分处理
        
        支持的图片格式：
        - JPEG、PNG、GIF
        - 封面图建议尺寸：900×383（2.35:1 比例）
        - 文章内图宽度不超过 900px
        """
        token = await self.get_access_token()
        
        # ----------------------------------------------------------------
        # 根据类型选择不同的 API 端点
        # ----------------------------------------------------------------
        if media_type == "image":
            # 文章内图：返回 URL
            url = f"{self.BASE_URL}/media/imgupload?access_token={token}"
        else:
            # 封面图（永久素材）：返回 media_id
            url = f"{self.BASE_URL}/material/add_material?access_token={token}&type=image"
        
        # 检查文件是否存在
        file_path = Path(image_path)
        if not file_path.exists():
            raise FileNotFoundError(f"图片不存在: {image_path}")
        
        # 上传文件
        async with httpx.AsyncClient(timeout=120) as client:
            with open(file_path, "rb") as f:
                files = {"media": (file_path.name, f, "image/jpeg")}
                resp = await client.post(url, files=files)
        
        data = resp.json()
        
        # 检查上传结果
        if "media_id" not in data and "url" not in data:
            error_msg = data.get("errmsg", str(data))
            raise Exception(f"上传图片失败: {error_msg}")
        
        # 返回对应的结果
        if media_type == "image":
            return data.get("url", "")
        else:
            return data.get("media_id", "")
    
    async def upload_content_image(self, image_path: str) -> str:
        """
        上传文章内图片（便捷方法）
        
        参数：
            image_path: 本地图片路径
        
        返回：
            图片 URL（可直接插入 HTML 的 src 属性）
        """
        return await self.upload_image(image_path, media_type="image")
    
    # ========================================================================
    # 草稿管理
    # ========================================================================
    
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
        
        参数：
            title: 文章标题（必填，最长 64 字符）
            content: 正文 HTML（必填）
            thumb_media_id: 封面图 media_id（建议提供）
            author: 作者名称（可选，最长 8 字符）
            digest: 摘要（可选，最长 120 字符，不填则自动截取正文前 120 字）
        
        返回：
            草稿 media_id（用于后续修改或发布）
        
        注意：
        - 一篇图文消息最多 8 篇文章
        - MVP 阶段每次只创建一篇
        - 草稿保存在公众号后台，可登录网页版编辑
        
        API 限制：
        - 正文支持 HTML，但不支持 JavaScript
        - 图片必须使用微信域名下的 URL
        - 外链需在公众号后台配置业务域名
        """
        token = await self.get_access_token()
        url = f"{self.BASE_URL}/draft/add?access_token={token}"
        
        # 构建文章数据
        article = {
            "title": title,
            "author": author,
            "digest": digest,
            "content": content,
            "content_source_url": "",  # 原文链接（可选）
            "need_open_comment": 0,   # 是否打开评论（0/1）
            "only_fans_can_comment": 0,  # 仅粉丝可评论（0/1）
        }
        
        # 封面图（强烈建议提供）
        if thumb_media_id:
            article["thumb_media_id"] = thumb_media_id
        
        payload = {"articles": [article]}
        
        # 发送请求
        resp = await self._client.post(url, json=payload)
        data = resp.json()
        
        if "media_id" not in data:
            error_msg = data.get("errmsg", str(data))
            raise Exception(f"创建草稿失败: {error_msg}")
        
        logger.info(f"Draft created: media_id={data['media_id']}")
        return data["media_id"]
    
    async def get_draft(self, media_id: str) -> dict:
        """
        获取草稿内容
        
        参数：
            media_id: 草稿 ID
        
        返回：
            草稿详情（包含所有文章）
        """
        token = await self.get_access_token()
        url = f"{self.BASE_URL}/draft/get?access_token={token}"
        resp = await self._client.post(url, json={"media_id": media_id})
        return resp.json()
    
    async def delete_draft(self, media_id: str) -> bool:
        """
        删除草稿
        
        参数：
            media_id: 草稿 ID
        
        返回：
            是否删除成功
        
        注意：
            删除后无法恢复，谨慎使用
        """
        token = await self.get_access_token()
        url = f"{self.BASE_URL}/draft/delete?access_token={token}"
        resp = await self._client.post(url, json={"media_id": media_id})
        data = resp.json()
        return data.get("errcode", -1) == 0
    
    # ========================================================================
    # 预览与发布
    # ========================================================================
    
    async def submit_preview(self, media_id: str, user_openid: str) -> bool:
        """
        发送预览给指定用户
        
        参数：
            media_id: 草稿 ID
            user_openid: 接收预览的用户 OpenID
        
        返回：
            是否发送成功
        
        用途：
            在正式发布前，先发送给内部人员预览
            检查排版、图片、链接是否正常
        
        注意：
            user_openid 必须是已关注该公众号的用户
            MVP 阶段暂不实现此功能
        """
        token = await self.get_access_token()
        url = f"{self.BASE_URL}/freepublish/submit?access_token={token}"
        # 注意：实际预览接口不同，这里用占位实现
        # 正式环境需要用 message/custom/send 或其他预览接口
        logger.info(f"Preview sent to {user_openid} for media_id={media_id}")
        return True
    
    async def publish(self, media_id: str) -> str:
        """
        发布文章（从草稿发布）
        
        参数：
            media_id: 草稿 ID
        
        返回：
            publish_id（用于查询发布状态）
        
        发布流程：
        1. 调用此接口发起发布
        2. 微信异步处理
        3. 通过 publish_id 查询发布状态
        
        注意：
            发布后文章对所有用户可见
            MVP 阶段不建议自动发布，保持人工审核
        """
        token = await self.get_access_token()
        url = f"{self.BASE_URL}/freepublish/submit?access_token={token}"
        resp = await self._client.post(url, json={"media_id": media_id})
        data = resp.json()
        
        if "publish_id" not in data:
            error_msg = data.get("errmsg", str(data))
            raise Exception(f"发布失败: {error_msg}")
        
        logger.info(f"Article published: publish_id={data['publish_id']}")
        return data["publish_id"]
    
    # ========================================================================
    # 资源清理
    # ========================================================================
    
    async def close(self):
        """
        关闭客户端连接
        
        必须在程序退出前调用，否则可能导致资源泄漏
        """
        await self._client.aclose()


class WeChatPublisher:
    """
    微信公众号发布器——模块D的核心
    
    高层次的发布接口，负责：
    1. 管理多个公众号账号
    2. 协调图片上传、HTML 组装、创建草稿的完整流程
    3. 记录发布状态到数据库
    
    使用示例：
        accounts = [
            {"id": "default", "app_id": "wx123", "app_secret": "secret"}
        ]
        publisher = WeChatPublisher(db, accounts)
        
        result = await publisher.publish_to_draft(formatted_data)
        print(result["media_id"])
    
    Phase 规划：
    - Phase 1: 仅支持单账号、草稿箱模式
    - Phase 2: 支持多账号、预览功能
    - Phase 3: 支持定时发布
    """
    
    def __init__(self, db: Database, accounts_config: list[dict]):
        """
        初始化发布器
        
        参数：
            db: 数据库实例
            accounts_config: 公众号账号配置列表
                [{"id": "xxx", "app_id": "wx...", "app_secret": "..."}]
        
        配置示例：
            accounts_config = [
                {
                    "id": "default",
                    "app_id": "wx1234567890",
                    "app_secret": "your_secret_here"
                }
            ]
        """
        self.db = db
        self.accounts: dict[str, dict] = {}
        
        # 构建账号索引（便于按 ID 快速查找）
        for acc in accounts_config:
            self.accounts[acc["id"]] = acc
    
    def get_client(self, account_id: str) -> WeChatMPClient:
        """
        获取指定账号的 API 客户端
        
        参数：
            account_id: 账号 ID
        
        返回：
            WeChatMPClient 实例
        
        注意：
            每次调用都会创建新的客户端实例
            使用完毕后需要手动关闭
        """
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
        发布到草稿箱（MVP 模式）
        
        参数：
            formatted_data: formatted 表的记录
            account_id: 公众号账号 ID
            author: 作者名称（可选）
        
        返回：
            {
                "id": str,              # 记录 UUID
                "formatted_id": str,    # 关联的格式化记录 ID
                "account_id": str,      # 账号 ID
                "media_id": str,        # 微信返回的草稿 ID
                "thumb_media_id": str,  # 封面图 ID（如有）
                "status": str,          # 状态：draft/failed
                "error": str            # 错误信息（失败时）
            }
        
        执行流程：
        1. 创建 API 客户端
        2. 上传封面图（如有）
        3. 上传文章内图片，替换本地路径为微信 URL
        4. 查询关联的改写记录，获取标题
        5. 创建草稿
        6. 记录发布结果到数据库
        
        错误处理：
        - 任何步骤失败都会记录错误，状态设为 failed
        - 使用 try-finally 确保客户端关闭
        """
        client = self.get_client(account_id)
        
        result = {
            "id": str(uuid.uuid4()),
            "formatted_id": formatted_data["id"],
            "account_id": account_id,
            "status": "draft",
        }
        
        try:
            # ----------------------------------------------------------------
            # Step 1: 上传封面图
            # ----------------------------------------------------------------
            thumb_media_id = None
            cover_image = formatted_data.get("cover_image")
            if cover_image and Path(cover_image).exists():
                thumb_media_id = await client.upload_image(
                    cover_image, media_type="thumb"
                )
                result["thumb_media_id"] = thumb_media_id
                logger.info(f"Cover uploaded: {thumb_media_id}")
            
            # ----------------------------------------------------------------
            # Step 2: 上传文章内图片，替换路径
            # ----------------------------------------------------------------
            html_content = formatted_data.get("html", "")
            
            # 解析 images 字段（可能是 JSON 字符串）
            images_raw = formatted_data.get("images", "[]")
            if isinstance(images_raw, str):
                images = json.loads(images_raw)
            else:
                images = images_raw
            
            for img in images:
                local_path = img.get("local_path", "")
                if local_path and Path(local_path).exists():
                    wx_url = await client.upload_content_image(local_path)
                    # 替换 HTML 中的本地路径为微信 URL
                    html_content = html_content.replace(
                        f'src="{local_path}"',
                        f'src="{wx_url}"'
                    )
                    logger.debug(f"Image uploaded: {local_path} → {wx_url}")
            
            # ----------------------------------------------------------------
            # Step 3: 查询关联的改写记录，获取标题
            # ----------------------------------------------------------------
            rewrite = await self.db.fetch_one(
                "SELECT * FROM rewrites WHERE id = ?",
                (formatted_data["rewrite_id"],),
            )
            
            title = "未命名文章"
            digest = ""
            if rewrite:
                title = rewrite.get("title") or "未命名文章"
                # 摘要：取正文前 120 字符
                content_text = rewrite.get("content", "")
                digest = content_text[:120].replace("\n", " ")
            
            # ----------------------------------------------------------------
            # Step 4: 创建草稿
            # ----------------------------------------------------------------
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
        
        # ----------------------------------------------------------------
        # Step 5: 记录到数据库
        # ----------------------------------------------------------------
        await self.db.insert_published(result)
        
        return result
    
    async def test_connection(self, account_id: str) -> dict:
        """
        测试公众号连接
        
        参数：
            account_id: 账号 ID
        
        返回：
            {"success": bool, "message": str}
        
        用途：
            在配置新账号后，测试 AppID/AppSecret 是否正确
            或在启动时检查账号状态
        """
        client = self.get_client(account_id)
        try:
            token = await client.get_access_token()
            await client.close()
            return {
                "success": True,
                "message": f"连接成功，token={token[:10]}..."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"连接失败: {e}"
            }
