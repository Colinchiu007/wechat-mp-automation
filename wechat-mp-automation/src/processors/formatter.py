"""
内容格式化器
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class OutputFormat(Enum):
    """输出格式"""
    MARKDOWN = "markdown"
    HTML = "html"
    TEXT = "text"
    WECHAT = "wechat"
    XIAOHONGSHU = "xiaohongshu"
    DOUYIN = "douyin"
    YOUTUBE = "youtube"


@dataclass
class FormatConfig:
    """格式化配置"""
    format: OutputFormat = OutputFormat.MARKDOWN
    template: str | None = None
    include_cover: bool = True
    include_description: bool = True
    add_toc: bool = False
    heading_style: str = "atx"
    max_paragraph_length: int = 500


class ContentFormatter:
    """内容格式化器"""
    
    def __init__(self, config: dict[str, Any] = None):
        self.config = config or {}
    
    def format(
        self,
        title: str,
        content: str,
        summary: str = "",
        images: list[str] = None,
        config: FormatConfig | None = None
    ) -> str:
        """格式化内容"""
        if config is None:
            config = FormatConfig()
        
        if images is None:
            images = []
        
        if config.format == OutputFormat.MARKDOWN:
            return self._format_markdown(title, content, summary, images, config)
        elif config.format == OutputFormat.HTML:
            return self._format_html(title, content, summary, images, config)
        elif config.format == OutputFormat.WECHAT:
            return self._format_wechat(title, content, summary, images, config)
        elif config.format == OutputFormat.XIAOHONGSHU:
            return self._format_xiaohongshu(title, content, images, config)
        elif config.format == OutputFormat.DOUYIN:
            return self._format_douyin(title, content, config)
        elif config.format == OutputFormat.YOUTUBE:
            return self._format_youtube(title, content, summary, config)
        else:
            return content
    
    def _format_markdown(
        self,
        title: str,
        content: str,
        summary: str,
        images: list[str],
        config: FormatConfig
    ) -> str:
        """格式化为 Markdown"""
        lines = []
        
        # 标题
        lines.append(f"# {title}\n")
        
        # 摘要
        if summary and config.include_description:
            lines.append(f"> {summary}\n")
        
        # 目录
        if config.add_toc:
            lines.append(self._generate_toc(content))
        
        # 封面图
        if images and config.include_cover:
            lines.append(f"![封面]({images[0]})\n")
        
        # 正文
        formatted_content = self._format_paragraphs(content, config)
        lines.append(formatted_content)
        
        # 其他图片
        if len(images) > 1:
            lines.append("\n## 图片\n")
            for i, img in enumerate(images[1:], 1):
                lines.append(f"图{i}：![图片{i}]({img})")
        
        return "\n".join(lines)
    
    def _format_html(
        self,
        title: str,
        content: str,
        summary: str,
        images: list[str],
        config: FormatConfig
    ) -> str:
        """格式化为 HTML"""
        lines = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            f"<title>{title}</title>",
            "<meta charset='utf-8'>",
            "<style>",
            "body { font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }",
            "h1 { color: #333; }",
            "blockquote { border-left: 4px solid #ddd; margin: 0; padding-left: 16px; color: #666; }",
            "img { max-width: 100%; }",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>{title}</h1>",
        ]
        
        if summary and config.include_description:
            lines.append(f"<blockquote>{summary}</blockquote>")
        
        if images and config.include_cover:
            lines.append(f"<img src='{images[0]}' alt='封面'>")
        
        # 转换 Markdown 为 HTML
        html_content = self._markdown_to_html(content)
        lines.append(html_content)
        
        lines.extend(["</body>", "</html>"])
        
        return "\n".join(lines)
    
    def _format_wechat(
        self,
        title: str,
        content: str,
        summary: str,
        images: list[str],
        config: FormatConfig
    ) -> str:
        """格式化为微信公众号格式"""
        lines = []
        
        # 标题
        lines.append(f"**{title}**\n")
        
        # 摘要
        if summary:
            lines.append(f"_{summary}_\n")
        
        # 格式化内容
        formatted_content = self._format_paragraphs(content, config)
        
        # 处理图片引用（转换为微信格式）
        formatted_content = self._convert_images_for_wechat(formatted_content, images)
        
        lines.append(formatted_content)
        
        return "\n".join(lines)
    
    def _format_xiaohongshu(
        self,
        title: str,
        content: str,
        images: list[str],
        config: FormatConfig
    ) -> str:
        """格式化为小红书格式"""
        lines = []
        
        # 标题
        lines.append(f"## {title}\n")
        
        # 封面图
        if images:
            lines.append(f"[图片]\n")
        
        # 简短内容（小红书限制1000字）
        max_length = 1000
        if len(content) > max_length:
            content = content[:max_length] + "..."
        
        lines.append(content)
        
        # 标签
        lines.append("\n\n#标签1 #标签2 #标签3")
        
        return "\n".join(lines)
    
    def _format_douyin(
        self,
        title: str,
        content: str,
        config: FormatConfig
    ) -> str:
        """格式化为抖音脚本格式"""
        lines = [
            f"# {title}",
            "",
            "## 开头（3秒抓眼球）",
            self._extract_opening_hook(content),
            "",
            "## 正文",
            self._format_script_content(content),
            "",
            "## 结尾引导互动",
            "关注我，获取更多精彩内容！",
            "评论区告诉我你的想法...",
        ]
        
        return "\n".join(lines)
    
    def _format_youtube(
        self,
        title: str,
        content: str,
        summary: str,
        config: FormatConfig
    ) -> str:
        """格式化为 YouTube 脚本格式"""
        lines = [
            f"# {title}",
            "",
            "## 描述 (Description)",
            summary or content[:5000],
            "",
            "## 标签 (Tags)",
            "#shorts #youtube #vlog #trending",
        ]
        
        return "\n".join(lines)
    
    def _format_paragraphs(self, content: str, config: FormatConfig) -> str:
        """格式化段落"""
        paragraphs = content.split("\n\n")
        formatted = []
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # 处理标题
            if para.startswith("#"):
                formatted.append(para)
            # 处理列表
            elif para.startswith("- ") or para.startswith("* "):
                formatted.append(para)
            # 处理引用
            elif para.startswith(">"):
                formatted.append(para)
            # 普通段落
            else:
                # 分割过长的段落
                if len(para) > config.max_paragraph_length:
                    sub_paragraphs = self._split_long_paragraph(para, config.max_paragraph_length)
                    formatted.extend(sub_paragraphs)
                else:
                    formatted.append(para)
        
        return "\n\n".join(formatted)
    
    def _split_long_paragraph(self, text: str, max_length: int) -> list[str]:
        """分割过长的段落"""
        sentences = re.split(r"([。！？；\n])", text)
        result = []
        current = ""
        
        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            if i + 1 < len(sentences):
                sentence += sentences[i + 1]
            
            if len(current) + len(sentence) <= max_length:
                current += sentence
            else:
                if current:
                    result.append(current)
                current = sentence
        
        if current:
            result.append(current)
        
        return result
    
    def _generate_toc(self, content: str) -> str:
        """生成目录"""
        lines = ["## 目录\n"]
        headers = re.findall(r"^#{1,3}\s+(.+)$", content, re.MULTILINE)
        
        for i, header in enumerate(headers, 1):
            level = header.count("#")
            indent = "  " * (level - 1)
            lines.append(f"{indent}{i}. [{header}](#{header})")
        
        lines.append("")
        return "\n".join(lines)
    
    def _markdown_to_html(self, markdown: str) -> str:
        """Markdown 转 HTML"""
        html = markdown
        
        # 标题
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        
        # 粗体和斜体
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        
        # 段落
        html = re.sub(r"\n\n", "</p><p>", html)
        html = f"<p>{html}</p>"
        
        # 换行
        html = html.replace("\n", "<br>")
        
        return html
    
    def _convert_images_for_wechat(self, content: str, images: list[str]) -> str:
        """转换图片引用为微信格式"""
        if not images:
            return content
        
        # 将 ![alt](url) 格式转换为微信图片格式
        for i, img_url in enumerate(images):
            placeholder = f"[图片{i+1}]"
            content = content.replace(f"![图片{i+1}]({img_url})", placeholder)
            content = content.replace(f"![alt]({img_url})", placeholder)
        
        return content
    
    def _extract_opening_hook(self, content: str) -> str:
        """提取开头钩子"""
        # 取前100字作为开头
        first_para = content.split("\n")[0][:100]
        if len(first_para) < 100 and len(content.split("\n")) > 1:
            first_para += content.split("\n")[1][:100 - len(first_para)]
        return first_para + "..."
    
    def _format_script_content(self, content: str) -> str:
        """格式化脚本内容"""
        # 添加场景描述
        lines = content.split("\n")
        formatted = []
        
        for i, line in enumerate(lines, 1):
            if line.strip():
                formatted.append(f"{i}. {line}")
        
        return "\n".join(formatted)
