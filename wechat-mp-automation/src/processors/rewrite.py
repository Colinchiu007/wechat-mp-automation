"""
内容改写处理器
================

本模块负责调用 LLM 对采集的内容进行改写，是整个系统的核心处理层。

核心设计：
- 支持 5 种改写策略：摘要提取、风格迁移、伪原创、深度改写、内容扩展
- 兼容 OpenAI 和 Anthropic API（通过配置切换）
- 自动重试机制（应对 API 限流）
- 并发控制（避免同时发起过多请求）

改写流程：
1. 接收 Content 对象和 RewriteConfig 配置
2. 根据策略选择系统提示词模板
3. 组装用户提示词（标题+正文）
4. 调用 LLM API
5. 解析响应，提取标题、摘要、正文
6. 返回 RewriteResult

使用示例：
    async with RewriteProcessor({"llm": {...}}) as processor:
        config = RewriteConfig(
            strategy=RewriteStrategy.REWRITE,
            target_word_count=3000
        )
        result = await processor.rewrite(content, config)
        if result.success:
            print(result.rewritten_content)

成本控制：
- 使用 min_word_count / max_word_count 约束输出长度
- 记录 tokens_used 用于成本核算
- 输入截断到 10000 字符（避免超 token）

Phase 规划：
- Phase 1: 仅支持单次改写
- Phase 2: 支持多风格切换、风格学习
- Phase 4: 支持质量评分、多版本对比
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
from loguru import logger

from src.sources.base import Content


class RewriteStrategy(Enum):
    """
    改写策略枚举
    
    每种策略对应不同的改写深度和目的：
    
    - SUMMARIZE: 摘要提取
      目的：提取文章核心观点，生成精简摘要
      适用：资讯类内容，需要快速了解要点
      输出：200-500字摘要
    
    - STYLE_TRANSFER: 风格迁移
      目的：保持内容不变，改变表达风格
      适用：已有优质内容，需要调整语气/人称
      输出：与原文长度相近，风格不同
    
    - PARAPHRASE: 伪原创
      目的：同义替换，降低重复度
      适用：SEO 需求，避免重复内容惩罚
      输出：意思相同，表达不同
    
    - REWRITE: 深度改写 (默认)
      目的：重新组织结构和表达
      适用：通用改写场景
      输出：保留核心观点，全新表达
    
    - EXPAND: 内容扩展
      目的：添加背景、案例、数据
      适用：内容较单薄，需要丰富
      输出：比原文更长更丰富
    """
    SUMMARIZE = "summarize"
    STYLE_TRANSFER = "style_transfer"
    PARAPHRASE = "paraphrase"
    REWRITE = "rewrite"
    EXPAND = "expand"


@dataclass
class RewriteConfig:
    """
    改写配置
    
    属性：
        strategy: 改写策略（默认 REWRITE）
        style_id: 风格ID（如 "professional"、"casual"）
        style_config: 风格详细配置
            - tone: 语气（如 "轻松"、"严肃"）
            - perspective: 人称（first_person/second_person/third_person）
            - structure: 结构（problem_solution/comparison/list/narrative/question_answer）
            - rules: 自定义规则列表
        min_word_count: 最小字数
        max_word_count: 最大字数
        target_word_count: 目标字数
    
    使用示例：
        config = RewriteConfig(
            strategy=RewriteStrategy.STYLE_TRANSFER,
            style_config={
                "tone": "轻松幽默",
                "perspective": "first_person",
                "structure": "list"
            }
        )
    """
    strategy: RewriteStrategy = RewriteStrategy.REWRITE
    style_id: str | None = None
    style_config: dict[str, Any] = field(default_factory=dict)
    min_word_count: int = 500
    max_word_count: int = 5000
    target_word_count: int = 3000


@dataclass
class RewriteResult:
    """
    改写结果
    
    属性：
        success: 是否成功
        original_content: 原始内容对象
        rewritten_content: 改写后的正文（Markdown 格式）
        title: 改写后的标题
        summary: 摘要
        keywords: 关键词列表
        error: 错误信息（失败时）
        duration: 执行耗时（秒）
        metadata: 元数据（策略、字数统计、token 消耗等）
    """
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
    """
    内容改写处理器
    
    核心方法：
        rewrite(): 改写单篇内容
        rewrite_batch(): 批量改写（并发控制）
    
    使用异步上下文管理器模式：
        async with RewriteProcessor(config) as processor:
            result = await processor.rewrite(content)
    
    这样设计的原因：
        - HTTP 客户端需要复用（避免每次创建新连接）
        - 需要正确的资源清理（关闭连接）
    """
    
    # ========================================================================
    # 系统提示词模板
    # ========================================================================
    # 每种策略对应一个提示词，定义改写的具体要求
    # ========================================================================
    
    SYSTEM_PROMPTS = {
        # 摘要提取：只保留核心要点
        RewriteStrategy.SUMMARIZE: """你是一个专业的文章摘要助手。请根据提供的文章内容，提取核心要点，生成简洁准确的摘要。
要求：
1. 保留关键信息和核心观点
2. 语言简洁流畅
3. 长度控制在200-500字
4. 使用中文输出""",
        
        # 风格迁移：保持内容，改变风格
        RewriteStrategy.STYLE_TRANSFER: """你是一个专业的文案风格转换助手。请将文章内容转换为指定的风格。
要求：
1. 保持原文的核心信息和观点
2. 严格按照指定的风格要求进行转换
3. 语言流畅自然
4. 使用中文输出""",
        
        # 伪原创：同义替换，降低重复度
        RewriteStrategy.PARAPHRASE: """你是一个专业的伪原创助手。请在不改变原文核心意思的前提下，对文章进行改写，使其具有原创性。
要求：
1. 保持原文的核心信息和观点不变
2. 改变表达方式和句式结构
3. 替换同义词和近义词
4. 降低重复度，提高原创度
5. 使用中文输出""",
        
        # 深度改写：重新组织结构和表达（默认策略）
        RewriteStrategy.REWRITE: """你是一个专业的文章改写助手。请对原文进行深度改写，重新组织结构和表达方式。
要求：
1. 保持原文的核心信息和主要观点
2. 重新组织文章结构和段落
3. 改变表达方式和句式
4. 添加适当的过渡和衔接
5. 使文章更加流畅和有逻辑性
6. 使用中文输出""",
        
        # 内容扩展：添加背景、案例、数据
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
        """
        初始化改写处理器
        
        参数：
            config: 配置字典，需包含 "llm" 键
                - provider: "openai" 或 "anthropic"
                - api_key: API 密钥
                - model: 模型名称（如 "gpt-4o"）
                - base_url: API 基础 URL（可选，用于代理）
                - timeout: 请求超时时间（秒）
                - retry: 重试次数
        
        配置示例：
            {
                "llm": {
                    "provider": "openai",
                    "api_key": "sk-xxx",
                    "model": "gpt-4o",
                    "base_url": "https://api.openai.com/v1",
                    "timeout": 120,
                    "retry": 3
                }
            }
        """
        self.config = config
        self.llm_config = config.get("llm", {})
        self.client: httpx.AsyncClient | None = None
    
    async def __aenter__(self):
        """
        异步上下文管理器入口
        
        创建 HTTP 客户端，复用连接
        """
        timeout = self.llm_config.get("timeout", 120)
        self.client = httpx.AsyncClient(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        异步上下文管理器退出
        
        关闭 HTTP 客户端，释放资源
        """
        if self.client:
            await self.client.aclose()
    
    async def rewrite(
        self,
        content: Content,
        rewrite_config: RewriteConfig | None = None
    ) -> RewriteResult:
        """
        改写单篇内容
        
        参数：
            content: 原始内容对象
            rewrite_config: 改写配置，None 则使用默认配置
        
        返回：
            RewriteResult 对象，包含改写结果或错误信息
        
        执行流程：
        1. 使用默认配置（如果未提供）
        2. 构建系统提示词 + 用户提示词
        3. 调用 LLM API
        4. 解析响应，提取标题、摘要、正文
        5. 返回结果
        
        错误处理：
        - API 调用失败时返回 success=False 和 error 信息
        - 不抛出异常，让调用方决定如何处理
        """
        if rewrite_config is None:
            rewrite_config = RewriteConfig()
        
        start_time = time.time()
        
        try:
            # ----------------------------------------------------------------
            # 构建提示词
            # ----------------------------------------------------------------
            prompt = self._build_prompt(content, rewrite_config)
            
            # ----------------------------------------------------------------
            # 调用 LLM
            # ----------------------------------------------------------------
            response = await self._call_llm(prompt, rewrite_config)
            
            # ----------------------------------------------------------------
            # 解析响应
            # ----------------------------------------------------------------
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
        """
        批量改写内容
        
        参数：
            contents: 内容列表
            rewrite_config: 改写配置（所有内容使用相同配置）
        
        返回：
            RewriteResult 列表（与输入顺序对应）
        
        并发控制：
            使用 Semaphore 限制同时进行的请求数为 3
            原因：
            - 避免触发 API 限流（429 错误）
            - 控制内存和 CPU 使用
        
        使用示例：
            results = await processor.rewrite_batch(contents, config)
            for result in results:
                if result.success:
                    print(f"成功: {result.title}")
                else:
                    print(f"失败: {result.error}")
        """
        if rewrite_config is None:
            rewrite_config = RewriteConfig()
        
        results = []
        
        # 并发限制：最多 3 个并发请求
        semaphore = asyncio.Semaphore(3)
        
        async def rewrite_with_limit(content: Content) -> RewriteResult:
            """带并发限制的改写"""
            async with semaphore:
                return await self.rewrite(content, rewrite_config)
        
        # 并发执行所有任务
        tasks = [rewrite_with_limit(content) for content in contents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常（gather 返回的异常对象）
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
    
    # ========================================================================
    # 内部方法：提示词构建
    # ========================================================================
    
    def _build_prompt(self, content: Content, config: RewriteConfig) -> str:
        """
        构建完整的提示词
        
        参数：
            content: 原始内容
            config: 改写配置
        
        返回：
            组装后的完整提示词
        
        组装顺序：
        1. 系统提示词（根据策略选择）
        2. 风格要求（如果有配置）
        3. 字数要求
        4. 原文（标题+正文）
        """
        # 获取策略对应的系统提示词
        system_prompt = self.SYSTEM_PROMPTS.get(
            config.strategy,
            self.SYSTEM_PROMPTS[RewriteStrategy.REWRITE]
        )
        
        # ----------------------------------------------------------------
        # 添加风格配置
        # ----------------------------------------------------------------
        if config.style_config:
            style_rules = []
            
            # 语气
            tone = config.style_config.get("tone")
            if tone:
                style_rules.append(f"语气：{tone}")
            
            # 人称（转换为中文）
            perspective = config.style_config.get("perspective")
            if perspective:
                perspective_map = {
                    "first_person": "第一人称",
                    "second_person": "第二人称",
                    "third_person": "第三人称"
                }
                style_rules.append(
                    f"人称：{perspective_map.get(perspective, perspective)}"
                )
            
            # 文章结构（转换为中文）
            structure = config.style_config.get("structure")
            if structure:
                structure_map = {
                    "problem_solution": "问题-解决方案",
                    "comparison": "对比分析",
                    "list": "列表式",
                    "narrative": "叙事式",
                    "question_answer": "问答式"
                }
                style_rules.append(
                    f"结构：{structure_map.get(structure, structure)}"
                )
            
            # 自定义规则
            rules = config.style_config.get("rules", [])
            if rules:
                style_rules.extend(
                    [f"规则{i+1}：{rule}" for i, rule in enumerate(rules)]
                )
            
            if style_rules:
                system_prompt += "\n\n风格要求：\n" + "\n".join(style_rules)
        
        # ----------------------------------------------------------------
        # 添加字数要求
        # ----------------------------------------------------------------
        system_prompt += (
            f"\n\n字数要求：{config.min_word_count}-{config.max_word_count}字，"
            f"目标{config.target_word_count}字。"
        )
        
        # ----------------------------------------------------------------
        # 添加原文
        # ----------------------------------------------------------------
        # 输入截断：避免超 token（大多数模型 token 限制在 128K 以下）
        # 10000 字符 ≈ 5000 汉字，对于大多数文章足够
        user_prompt = f"""请处理以下文章：

【标题】
{content.title}

【正文】
{content.content[:10000]}
"""
        
        return f"{system_prompt}\n\n{user_prompt}"
    
    # ========================================================================
    # 内部方法：LLM API 调用
    # ========================================================================
    
    async def _call_llm(self, prompt: str, config: RewriteConfig) -> str:
        """
        调用 LLM API
        
        参数：
            prompt: 完整提示词
            config: 改写配置（未使用，预留扩展）
        
        返回：
            LLM 生成的文本
        
        重试机制：
            - 429 错误（限流）：指数退避后重试
            - 其他错误：立即重试（最多 3 次）
        
        支持的 Provider：
            - openai: 兼容 OpenAI API 格式（包括 Azure、各种代理）
            - anthropic: Claude API
        
        配置示例（环境变量）：
            export OPENAI_API_KEY="sk-xxx"
            export OPENAI_BASE_URL="https://api.openai.com/v1"
        """
        provider = self.llm_config.get("provider", "openai")
        api_key = self.llm_config.get("api_key")
        model = self.llm_config.get("model", "gpt-4o")
        base_url = self.llm_config.get("base_url", "https://api.openai.com/v1")
        max_tokens = self.llm_config.get("max_tokens", 4096)
        
        if not api_key:
            raise ValueError(
                "LLM API key is required. "
                "Set OPENAI_API_KEY environment variable or pass in config."
            )
        
        # ----------------------------------------------------------------
        # 构建请求头
        # ----------------------------------------------------------------
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # ----------------------------------------------------------------
        # 根据不同 Provider 构建请求体
        # ----------------------------------------------------------------
        if provider == "openai":
            data = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7  # 适中的创造性
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
        
        # ----------------------------------------------------------------
        # 带重试的请求
        # ----------------------------------------------------------------
        retry = self.llm_config.get("retry", 3)
        last_error = None
        
        for attempt in range(retry):
            try:
                response = await self.client.post(url, json=data, headers=headers)
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # 提取响应文本
                    if provider == "openai":
                        return result["choices"][0]["message"]["content"]
                    elif provider == "anthropic":
                        return result["content"][0]["text"]
                
                elif response.status_code == 429:
                    # Rate limit - 指数退避
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Rate limited, waiting {wait_time}s before retry"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                
                else:
                    error_msg = (
                        f"API error: {response.status_code} - {response.text}"
                    )
                    logger.error(error_msg)
                    raise Exception(error_msg)
            
            except Exception as e:
                last_error = e
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(1)  # 等待后重试
        
        raise Exception(f"LLM call failed after {retry} attempts: {last_error}")
    
    # ========================================================================
    # 内部方法：响应解析
    # ========================================================================
    
    def _parse_response(
        self,
        response: str,
        original_content: Content,
        config: RewriteConfig
    ) -> RewriteResult:
        """
        解析 LLM 响应
        
        参数：
            response: LLM 返回的原始文本
            original_content: 原始内容（用于回填标题）
            config: 改写配置
        
        返回：
            RewriteResult 对象
        
        解析策略：
        - 尝试提取【标题】【摘要】【关键词】等结构化字段
        - 如果没有结构化标记，使用整段文本作为正文
        - 截取前 200 字作为摘要（如果没有摘要）
        
        注意：
            这里假设 LLM 会按照提示词输出结构化内容
            实际输出可能不标准，需要鲁棒的解析逻辑
        """
        # ----------------------------------------------------------------
        # 尝试提取标题
        # ----------------------------------------------------------------
        title = original_content.title
        if "【标题】" in response or "标题：" in response:
            title_match = re.search(r"【标题】[:：]?\s*(.+?)(?:\n|$)", response)
            if title_match:
                title = title_match.group(1).strip()
        
        # ----------------------------------------------------------------
        # 尝试提取摘要
        # ----------------------------------------------------------------
        summary = ""
        if "【摘要】" in response or "摘要：" in response:
            summary_match = re.search(
                r"【摘要】[:：]?\s*(.+?)(?:\n【|\n\n|$)",
                response,
                re.DOTALL
            )
            if summary_match:
                summary = summary_match.group(1).strip()
        
        # ----------------------------------------------------------------
        # 提取正文（去掉标题和摘要部分）
        # ----------------------------------------------------------------
        content_text = response
        for prefix in ["【标题】", "【摘要】", "标题：", "摘要："]:
            if prefix in content_text:
                parts = content_text.split(prefix, 1)
                if len(parts) > 1:
                    # 保留后半部分
                    content_text = parts[1]
                    # 去掉标题/摘要内容
                    for sep in ["\n【", "\n\n"]:
                        if sep in content_text:
                            content_text = content_text.split(sep, 1)[1]
                            break
        
        content_text = content_text.strip()
        
        # ----------------------------------------------------------------
        # 尝试提取关键词
        # ----------------------------------------------------------------
        keywords = []
        if "【关键词】" in response or "关键词：" in response:
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
    
    # ========================================================================
    # 内部方法：工具函数
    # ========================================================================
    
    def _truncate(self, text: str, length: int) -> str:
        """
        截断文本
        
        参数：
            text: 原始文本
            length: 最大长度
        
        返回：
            截断后的文本（末尾加省略号）
        """
        if len(text) <= length:
            return text
        return text[:length] + "..."
