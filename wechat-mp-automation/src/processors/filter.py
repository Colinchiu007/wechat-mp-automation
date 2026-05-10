"""
内容过滤器
"""

import re
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from src.sources.base import Content


@dataclass
class FilterResult:
    """过滤结果"""
    passed: bool
    reasons: list[str] = field(default_factory=list)
    score: float = 1.0


class ContentFilter:
    """内容过滤器"""
    
    # 默认敏感词列表（简化版）
    DEFAULT_SENSITIVE_WORDS = [
        "敏感词示例1",
        "敏感词示例2",
        # 添加更多敏感词
    ]
    
    def __init__(self, config: dict[str, Any] = None):
        self.config = config or {}
        self.sensitive_words = self._load_sensitive_words()
    
    def _load_sensitive_words(self) -> set[str]:
        """加载敏感词"""
        words = set(self.DEFAULT_SENSITIVE_WORDS)
        
        # 从配置文件加载
        custom_words = self.config.get("sensitive_words", [])
        words.update(custom_words)
        
        return words
    
    def filter(self, content: Content) -> FilterResult:
        """过滤内容"""
        reasons = []
        score = 1.0
        
        # 检查标题长度
        if len(content.title) < 5:
            reasons.append("标题太短")
            score -= 0.2
        elif len(content.title) > 100:
            reasons.append("标题太长")
            score -= 0.1
        
        # 检查内容长度
        if len(content.content) < 100:
            reasons.append("内容太短")
            score -= 0.3
        
        # 检查敏感词
        sensitive_found = self._check_sensitive_words(content)
        if sensitive_found:
            reasons.append(f"包含敏感词: {', '.join(sensitive_found)}")
            score -= 0.5
        
        # 检查是否为低质量内容
        if self._is_low_quality(content):
            reasons.append("内容质量较低")
            score -= 0.3
        
        # 检查重复内容
        if self._is_duplicate_pattern(content):
            reasons.append("包含重复模式")
            score -= 0.2
        
        passed = score >= 0.5 and not sensitive_found
        
        return FilterResult(passed=passed, reasons=reasons, score=score)
    
    def _check_sensitive_words(self, content: Content) -> list[str]:
        """检查敏感词"""
        found = []
        text = content.title + content.content
        
        for word in self.sensitive_words:
            if word in text:
                found.append(word)
        
        return found
    
    def _is_low_quality(self, content: Content) -> bool:
        """检查是否为低质量内容"""
        # 检查重复字符过多
        if self._has_excessive_repetition(content.content):
            return True
        
        # 检查链接过多
        url_count = len(re.findall(r"https?://", content.content))
        if url_count > 10:
            return True
        
        # 检查图片标签过多（可能是纯图片内容）
        img_count = len(re.findall(r"!\[.*?\]\(.*?\)", content.content))
        text_ratio = len(re.findall(r"\w", content.content)) / max(len(content.content), 1)
        if img_count > 5 and text_ratio < 0.3:
            return True
        
        return False
    
    def _has_excessive_repetition(self, text: str, threshold: float = 0.3) -> bool:
        """检查是否有过多重复"""
        if len(text) < 100:
            return False
        
        # 简单的重复检测：计算连续相同字符的比例
        if not text:
            return False
            
        max_repeat = 1
        current_repeat = 1
        prev_char = ""
        
        for char in text:
            if char == prev_char:
                current_repeat += 1
                max_repeat = max(max_repeat, current_repeat)
            else:
                current_repeat = 1
            prev_char = char
        
        return max_repeat / len(text) > threshold
    
    def _is_duplicate_pattern(self, content: Content) -> bool:
        """检查是否有重复模式"""
        # 检查是否有明显的重复段落
        paragraphs = content.content.split("\n\n")
        if len(paragraphs) < 3:
            return False
        
        # 简单检查：是否有完全相同的段落
        unique_paragraphs = set(paragraphs)
        if len(unique_paragraphs) / len(paragraphs) < 0.5:
            return True
        
        return False
    
    def filter_batch(self, contents: list[Content]) -> tuple[list[Content], list[tuple[Content, FilterResult]]]:
        """批量过滤内容"""
        passed = []
        failed = []
        
        for content in contents:
            result = self.filter(content)
            if result.passed:
                passed.append(content)
            else:
                failed.append((content, result))
        
        logger.info(f"Filtered {len(failed)}/{len(contents)} contents")
        
        return passed, failed
