"""
内容改写处理器
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
from loguru import logger

from src.sources.base import Content


class RewriteStrategy(Enum):
    """改写策略"""
    SUMMARIZE = "summarize"           # 摘要提取
    STYLE_TRANSFER = "style_transfer"  # 风格迁移
    PARAPHRASE = "paraphrase"          # 伪原创
    REWRITE = "rewrite"               # 深度改写
    EXPAND = "expand"                 # 扩展丰富


@dataclass
class RewriteConfig:
    """改写配置"""
    strategy: RewriteStrategy = RewriteStrategy.REWRITE
    style_id: str | None = None
    style_config: dict[str, Any] = field(default_factory=dict)
    min_word_count: int = 500
    max_word_count: int = 5000
    target_word_count: int = 3000


@dataclass
class RewriteResult:
    """改写结果"""
    success: bool
    original_content: Content | None = None
    rewritten_content: str = ""
    title: str = ""
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    error: str | None = None
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class RewriteProcessor:
    """内容改写处理器"""
    
    # 系统提示词模板
    SYSTEM_PROMPTS = {
        RewriteStrategy.SUMMARIZE: """你是一个专业的文章摘要助手。请根据提供的文章内容，提取核心要点，生成简洁准确的摘要。
要求：
1. 保留关键信息和核心观点
2. 语言简洁流畅
3. 长度控制在200-500字
4. 使用中文输出""",
        
        RewriteStrategy.STYLE_TRANSFER: """你是一个专业的文案风格转换助手。请将文章内容转换为指定的风格。
要求：
1. 保持原文的核心信息和观点
2. 严格按照指定的风格要求进行转换
3. 语言流畅自然
4. 使用中文输出""",
        
        RewriteStrategy.PARAPHRASE: """你是一个专业的伪原创助手。请在不改变原文核心意思的前提下，对文章进行改写，使其具有原创性。
要求：
1. 保持原文的核心信息和观点不变
2. 改变表达方式和句式结构
3. 替换同义词和近义词
4. 降低重复度，提高原创度
5. 使用中文输出""",
        
        RewriteStrategy.REWRITE: """你是一个专业的文章改写助手。请对原文进行深度改写，重新组织结构和表达方式。
要求：
1. 保持原文的核心信息和主要观点
2. 重新组织文章结构和段落
3. 改变表达方式和句式
4. 添加适当的过渡和衔接
5. 使文章更加流畅和有逻辑性
6. 使用中文输出""",
        
        RewriteStrategy.EXPAND: """你是一个专业的内容扩展助手。请在原文基础上添加更多背景、案例、数据等信息，生成更丰富的内容。
要求：
1. 保持原文的核心主题和观点
2. 添加相关的背景信息和行业数据
3. 引入更多实际案例
4. 提供更深入的分析
5. 使内容更加丰富和有价值
6. 使用中文输出""",
    }
    
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.llm_config = config.get("llm", {})
        self.client = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.client = httpx.AsyncClient(timeout=self.llm_config.get("timeout", 120))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.client:
            await self.client.aclose()
    
    async def rewrite(
        self,
        content: Content,
        rewrite_config: RewriteConfig | None = None
    ) -> RewriteResult:
        """改写内容"""
        if rewrite_config is None:
            rewrite_config = RewriteConfig()
        
        start_time = time.time()
        
        try:
            # 构建提示词
            prompt = self._build_prompt(content, rewrite_config)
            
            # 调用 LLM
            response = await self._call_llm(prompt, rewrite_config)
            
            # 解析结果
            result = self._parse_response(response, content, rewrite_config)
            result.duration = time.time() - start_time
            
            return result
            
        except Exception as e:
            logger.error(f"Rewrite error: {e}")
            return RewriteResult(
                success=False,
                original_content=content,
                error=str(e),
                duration=time.time() - start_time
            )
    
    async def rewrite_batch(
        self,
        contents: list[Content],
        rewrite_config: RewriteConfig | None = None
    ) -> list[RewriteResult]:
        """批量改写内容"""
        if rewrite_config is None:
            rewrite_config = RewriteConfig()
        
        results = []
        
        # 并发改写，但限制并发数
        semaphore = asyncio.Semaphore(3)
        
        async def rewrite_with_limit(content: Content) -> RewriteResult:
            async with semaphore:
                return await self.rewrite(content, rewrite_config)
        
        tasks = [rewrite_with_limit(content) for content in contents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(RewriteResult(
                    success=False,
                    original_content=contents[i],
                    error=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    def _build_prompt(self, content: Content, config: RewriteConfig) -> str:
        """构建提示词"""
        system_prompt = self.SYSTEM_PROMPTS.get(config.strategy, self.SYSTEM_PROMPTS[RewriteStrategy.REWRITE])
        
        # 添加风格配置
        if config.style_config:
            style_rules = []
            
            tone = config.style_config.get("tone")
            if tone:
                style_rules.append(f"语气：{tone}")
            
            perspective = config.style_config.get("perspective")
            if perspective:
                perspective_map = {
                    "first_person": "第一人称",
                    "second_person": "第二人称",
                    "third_person": "第三人称"
                }
                style_rules.append(f"人称：{perspective_map.get(perspective, perspective)}")
            
            structure = config.style_config.get("structure")
            if structure:
                structure_map = {
                    "problem_solution": "问题-解决方案",
                    "comparison": "对比分析",
                    "list": "列表式",
                    "narrative": "叙事式",
                    "question_answer": "问答式"
                }
                style_rules.append(f"结构：{structure_map.get(structure, structure)}")
            
            rules = config.style_config.get("rules", [])
            if rules:
                style_rules.extend([f"规则{i+1}：{rule}" for i, rule in enumerate(rules)])
            
            if style_rules:
                system_prompt += "\n\n风格要求：\n" + "\n".join(style_rules)
        
        # 添加字数要求
        system_prompt += f"\n\n字数要求：{config.min_word_count}-{config.max_word_count}字，目标{config.target_word_count}字。"
        
        # 添加原文
        user_prompt = f"""请处理以下文章：

【标题】
{content.title}

【正文】
{content.content[:10000]}  # 限制输入长度
"""
        
        return f"{system_prompt}\n\n{user_prompt}"
    
    async def _call_llm(self, prompt: str, config: RewriteConfig) -> str:
        """调用 LLM API"""
        provider = self.llm_config.get("provider", "openai")
        api_key = self.llm_config.get("api_key")
        model = self.llm_config.get("model", "gpt-4o")
        base_url = self.llm_config.get("base_url", "https://api.openai.com/v1")
        max_tokens = self.llm_config.get("max_tokens", 4096)
        
        if not api_key:
            raise ValueError("LLM API key is required")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        if provider == "openai":
            data = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7
            }
            url = f"{base_url}/chat/completions"
            
        elif provider == "anthropic":
            data = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens
            }
            url = f"{base_url}/messages"
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
            
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        
        retry = self.llm_config.get("retry", 3)
        last_error = None
        
        for attempt in range(retry):
            try:
                response = await self.client.post(url, json=data, headers=headers)
                
                if response.status_code == 200:
                    result = response.json()
                    
                    if provider == "openai":
                        return result["choices"][0]["message"]["content"]
                    elif provider == "anthropic":
                        return result["content"][0]["text"]
                        
                elif response.status_code == 429:
                    # Rate limit，等待后重试
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    error_msg = f"API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                    
            except Exception as e:
                last_error = e
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(1)
        
        raise Exception(f"LLM call failed after {retry} attempts: {last_error}")
    
    def _parse_response(
        self,
        response: str,
        original_content: Content,
        config: RewriteConfig
    ) -> RewriteResult:
        """解析 LLM 响应"""
        # 尝试提取标题
        title = original_content.title
        if "【标题】" in response or "标题：" in response:
            import re
            title_match = re.search(r"【标题】[:：]?\s*(.+?)(?:\n|$)", response)
            if title_match:
                title = title_match.group(1).strip()
        
        # 尝试提取摘要
        summary = ""
        if "【摘要】" in response or "摘要：" in response:
            import re
            summary_match = re.search(r"【摘要】[:：]?\s*(.+?)(?:\n【|\n\n|$)", response, re.DOTALL)
            if summary_match:
                summary = summary_match.group(1).strip()
        
        # 提取正文（去掉标题和摘要部分）
        content_text = response
        for prefix in ["【标题】", "【摘要】", "标题：", "摘要："]:
            if prefix in content_text:
                parts = content_text.split(prefix, 1)
                if len(parts) > 1:
                    # 保留后半部分
                    content_text = parts[1]
                    # 去掉标题/摘要部分
                    for sep in ["\n【", "\n\n"]:
                        if sep in content_text:
                            content_text = content_text.split(sep, 1)[1]
                            break
        
        # 清理格式
        content_text = content_text.strip()
        
        # 提取关键词（如果有）
        keywords = []
        if "【关键词】" in response or "关键词：" in response:
            import re
            kw_match = re.search(r"【关键词】[:：]?\s*(.+?)(?:\n|$)", response)
            if kw_match:
                keywords = [k.strip() for k in kw_match.group(1).split(",")]
        
        return RewriteResult(
            success=True,
            original_content=original_content,
            rewritten_content=content_text,
            title=title,
            summary=summary or self._truncate(content_text, 200),
            keywords=keywords,
            metadata={
                "strategy": config.strategy.value,
                "original_length": len(original_content.content),
                "rewritten_length": len(content_text),
            }
        )
    
    def _truncate(self, text: str, length: int) -> str:
        """截断文本"""
        if len(text) <= length:
            return text
        return text[:length] + "..."
