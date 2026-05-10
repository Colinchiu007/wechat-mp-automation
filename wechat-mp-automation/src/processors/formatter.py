"""
内容格式化模块
- Markdown → 公众号 HTML
- 排版模板
- 多平台导出
"""

import json
import re
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from src.storage.database import Database


# 公众号 HTML 排版样式（极简模板）
WECHAT_TEMPLATE = """
<div style="max-width: 677px; margin: 0 auto; padding: 20px 16px; font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; font-size: 16px; line-height: 1.8; color: #333; word-wrap: break-word;">

{content}

</div>
"""

# 段落样式
PARAGRAPH_STYLE = 'style="margin-bottom: 1.2em; text-align: justify;"'
# 标题样式
H2_STYLE = 'style="font-size: 20px; font-weight: bold; color: #1a1a1a; margin: 1.5em 0 0.8em; padding-bottom: 0.3em; border-bottom: 2px solid #e8e8e8;"'
H3_STYLE = 'style="font-size: 18px; font-weight: bold; color: #333; margin: 1.2em 0 0.6em;"'
# 引用样式
BLOCKQUOTE_STYLE = 'style="margin: 1em 0; padding: 12px 16px; background: #f7f7f7; border-left: 4px solid #ddd; color: #666; font-size: 15px;"'
# 代码块样式
CODE_BLOCK_STYLE = 'style="margin: 1em 0; padding: 16px; background: #f5f5f5; border-radius: 4px; font-family: Menlo, Monaco, Consolas, monospace; font-size: 14px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word;"'
# 行内代码样式
INLINE_CODE_STYLE = 'style="background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: 14px; color: #c7254e;"'
# 粗体样式
BOLD_STYLE = 'style="font-weight: bold; color: #1a1a1a;"'
# 图片样式
IMAGE_STYLE = 'style="max-width: 100%; height: auto; display: block; margin: 1em auto; border-radius: 4px;"'
# 列表样式
UL_STYLE = 'style="margin: 1em 0; padding-left: 2em;"'
OL_STYLE = 'style="margin: 1em 0; padding-left: 2em;"'
LI_STYLE = 'style="margin-bottom: 0.5em; line-height: 1.8;"'


def markdown_to_wechat_html(md_text: str, images: list[dict] | None = None) -> str:
    """
    将 Markdown 转换为公众号 HTML
    images: [{path: "本地路径", position: 1(在第几段之后插入), url: "微信URL(可选)"}]
    """
    html = md_text

    # 1. 代码块（先处理，避免内部被其他规则干扰）
    html = re.sub(
        r'```(\w*)\n(.*?)```',
        lambda m: f'<pre {CODE_BLOCK_STYLE}><code>{_escape_html(m.group(2))}</code></pre>',
        html,
        flags=re.DOTALL,
    )

    # 2. 行内代码
    html = re.sub(
        r'`([^`]+)`',
        lambda m: f'<code {INLINE_CODE_STYLE}>{_escape_html(m.group(1))}</code>',
        html,
    )

    # 3. 引用块
    html = re.sub(
        r'^>\s*(.+)$',
        lambda m: f'<blockquote {BLOCKQUOTE_STYLE}>{m.group(1)}</blockquote>',
        html,
        flags=re.MULTILINE,
    )

    # 4. 标题
    html = re.sub(r'^###\s+(.+)$', lambda m: f'<h3 {H3_STYLE}>{m.group(1)}</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^##\s+(.+)$', lambda m: f'<h2 {H2_STYLE}>{m.group(1)}</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^#\s+(.+)$', lambda m: f'<h1 {H2_STYLE}>{m.group(1)}</h1>', html, flags=re.MULTILINE)

    # 5. 粗体和斜体
    html = re.sub(r'\*\*(.+?)\*\*', lambda m: f'<strong {BOLD_STYLE}>{m.group(1)}</strong>', html)
    html = re.sub(r'\*(.+?)\*', lambda m: f'<em>{m.group(1)}</em>', html)

    # 6. 链接
    html = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        lambda m: f'<a href="{m.group(2)}" style="color: #576b95; text-decoration: none;">{m.group(1)}</a>',
        html,
    )

    # 7. 无序列表
    html = re.sub(r'^[-*]\s+(.+)$', lambda m: f'<li {LI_STYLE}>{m.group(1)}</li>', html, flags=re.MULTILINE)
    # 包裹 <ul>
    html = re.sub(
        r'(<li[^>]*>.*?</li>(?:\n<li[^>]*>.*?</li>)*)',
        lambda m: f'<ul {UL_STYLE}>{m.group(1)}</ul>',
        html,
        flags=re.DOTALL,
    )

    # 8. 有序列表
    html = re.sub(r'^\d+\.\s+(.+)$', lambda m: f'<li {LI_STYLE}>{m.group(1)}</li>', html, flags=re.MULTILINE)

    # 9. 水平线
    html = re.sub(r'^---+$', '<hr style="border: none; border-top: 1px solid #e8e8e8; margin: 2em 0;">', html, flags=re.MULTILINE)

    # 10. 段落处理（将连续纯文本包裹为 <p>）
    lines = html.split('\n')
    processed_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            processed_lines.append('')
        elif stripped.startswith('<'):
            processed_lines.append(stripped)
        else:
            processed_lines.append(f'<p {PARAGRAPH_STYLE}>{stripped}</p>')

    html = '\n'.join(processed_lines)

    # 11. 插入图片
    if images:
        img_idx = 0
        para_count = 0
        result_lines = []
        for line in html.split('\n'):
            result_lines.append(line)
            if '<p ' in line or '<h' in line:
                para_count += 1
                # 检查是否需要在此处插图
                while img_idx < len(images) and images[img_idx].get("position") == para_count:
                    img = images[img_idx]
                    src = img.get("url", img.get("path", ""))
                    alt = img.get("alt", "")
                    result_lines.append(f'<img src="{src}" alt="{alt}" {IMAGE_STYLE} />')
                    img_idx += 1

        html = '\n'.join(result_lines)

    # 12. 清理多余空行
    html = re.sub(r'\n{3,}', '\n\n', html)

    # 包裹在模板中
    return WECHAT_TEMPLATE.format(content=html)


def _escape_html(text: str) -> str:
    """HTML 转义"""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    return text


class ContentFormatter:
    """内容格式化器——模块C的核心"""

    def __init__(self, db: Database, config: dict | None = None):
        self.db = db
        self.config = config or {}
        self.template = self.config.get("template", "minimal")
        self.image_config = self.config.get("image", {})

    async def format_article(self, rewrite_data: dict) -> dict:
        """
        将改写结果格式化为公众号文章
        rewrite_data: rewrites 表的记录
        """
        content = rewrite_data.get("content", "")
        title = rewrite_data.get("title", "")

        # 如果内容不是 Markdown，跳过转换
        # 大部分改写输出是纯文本/Markdown混合，统一走 Markdown 转换
        images = []
        image_paths = self.image_config.get("paths", [])
        for i, img_path in enumerate(image_paths):
            if Path(img_path).exists():
                # 每隔3段插一张
                position = (i + 1) * 3
                images.append({"path": img_path, "position": position, "alt": title})

        html = markdown_to_wechat_html(content, images)

        # 格式化结果
        result = {
            "id": str(uuid.uuid4()),
            "rewrite_id": rewrite_data["id"],
            "format": "wechat_mp",
            "html": html,
            "cover_image": self.image_config.get("cover", None),
            "images": json.dumps(images, ensure_ascii=False),
            "exports": json.dumps({}, ensure_ascii=False),
        }

        # 存入数据库
        await self.db.insert_formatted(result)
        logger.info(f"Article formatted: {title} (format=wechat_mp)")
        return result

    async def export_markdown(self, rewrite_data: dict, output_dir: str = "./output/exports") -> str:
        """导出为 Markdown 文件"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        title = rewrite_data.get("title", "untitled")
        # 文件名安全化
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:50]
        filepath = Path(output_dir) / f"{safe_title}.md"

        content = f"# {title}\n\n{rewrite_data.get('content', '')}"
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Exported markdown: {filepath}")
        return str(filepath)
