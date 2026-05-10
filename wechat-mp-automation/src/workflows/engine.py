"""
工作流引擎
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from loguru import logger

from src.sources.base import BaseSource, SourceConfig, SourceType, Content
from src.processors.rewrite import RewriteProcessor, RewriteConfig, RewriteStrategy
from src.processors.filter import ContentFilter
from src.processors.formatter import ContentFormatter, FormatConfig, OutputFormat
from src.processors.image import ImageProcessor, ImageConfig
from src.workflows.state_machine import WorkflowStateMachine, WorkflowState


class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """步骤结果"""
    step_id: str
    status: StepStatus
    data: Any = None
    error: str | None = None
    duration: float = 0.0


@dataclass
class WorkflowResult:
    """工作流结果"""
    success: bool
    workflow_id: str
    workflow_name: str
    contents: list[dict] = field(default_factory=list)
    step_results: list[StepResult] = field(default_factory=list)
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    duration: float = 0.0
    metadata: dict = field(default_factory=dict)


class WorkflowEngine:
    """工作流引擎"""
    
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.state_machine = WorkflowStateMachine()
        self.logger = logger
        
        # 工作流配置
        self.workflows = config.get("workflows", {
            "default": {
                "name": "默认工作流",
                "timeout": 3600,
                "steps": ["collect", "filter", "rewrite", "generate_image", "format", "publish"]
            }
        })
    
    async def run(
        self,
        workflow_name: str = "default",
        source_ids: list[str] = None
    ) -> WorkflowResult:
        """运行工作流"""
        workflow_id = str(uuid.uuid4())
        started_at = datetime.now()
        
        self.logger.info(f"Starting workflow: {workflow_name} (ID: {workflow_id})")
        
        workflow_config = self.workflows.get(workflow_name, self.workflows["default"])
        step_results = []
        contents = []
        
        try:
            # 执行各步骤
            # 1. 采集
            result = await self._step_collect(source_ids)
            step_results.append(result)
            if result.status == StepStatus.FAILED:
                raise Exception(f"Collect step failed: {result.error}")
            contents = result.data or []
            
            # 2. 筛选
            result = await self._step_filter(contents)
            step_results.append(result)
            if result.status == StepStatus.FAILED:
                raise Exception(f"Filter step failed: {result.error}")
            contents = result.data or []
            
            # 3. 改写
            result = await self._step_rewrite(contents)
            step_results.append(result)
            if result.status == StepStatus.FAILED:
                raise Exception(f"Rewrite step failed: {result.error}")
            contents = result.data or []
            
            # 4. 生成配图
            result = await self._step_generate_image(contents)
            step_results.append(result)
            if result.status == StepStatus.SKIPPED:
                self.logger.warning("Image generation skipped")
            
            # 5. 格式化
            result = await self._step_format(contents)
            step_results.append(result)
            if result.status == StepStatus.FAILED:
                raise Exception(f"Format step failed: {result.error}")
            contents = result.data or []
            
            # 6. 发布
            result = await self._step_publish(contents)
            step_results.append(result)
            if result.status == StepStatus.FAILED:
                raise Exception(f"Publish step failed: {result.error}")
            
            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()
            
            self.logger.success(f"Workflow completed in {duration:.2f}s")
            
            return WorkflowResult(
                success=True,
                workflow_id=workflow_id,
                workflow_name=workflow_name,
                contents=contents,
                step_results=step_results,
                started_at=started_at,
                completed_at=completed_at,
                duration=duration
            )
            
        except Exception as e:
            self.logger.error(f"Workflow error: {e}")
            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()
            
            return WorkflowResult(
                success=False,
                workflow_id=workflow_id,
                workflow_name=workflow_name,
                contents=contents,
                step_results=step_results,
                error=str(e),
                started_at=started_at,
                completed_at=completed_at,
                duration=duration
            )
    
    async def _step_collect(self, source_ids: list[str] = None) -> StepResult:
        """采集步骤"""
        step_id = "collect"
        start_time = time.time()
        
        try:
            self.logger.info(f"Step {step_id}: Starting...")
            self.state_machine.transition(WorkflowState.COLLECTING)
            
            # TODO: 从配置加载数据源
            # 这里简化处理，返回空列表
            # 实际应该从 config/sources/ 加载配置并执行采集
            
            contents = []
            
            self.state_machine.transition(WorkflowState.COLLECTED)
            
            return StepResult(
                step_id=step_id,
                status=StepStatus.SUCCESS,
                data=contents,
                duration=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"Step {step_id} failed: {e}")
            self.state_machine.transition(WorkflowState.COLLECTION_FAILED)
            
            return StepResult(
                step_id=step_id,
                status=StepStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time
            )
    
    async def _step_filter(self, contents: list[Content]) -> StepResult:
        """筛选步骤"""
        step_id = "filter"
        start_time = time.time()
        
        try:
            self.logger.info(f"Step {step_id}: Filtering {len(contents)} contents...")
            self.state_machine.transition(WorkflowState.FILTERING)
            
            content_filter = ContentFilter(self.config)
            passed, failed = content_filter.filter_batch(contents)
            
            self.logger.info(f"Step {step_id}: Passed {len(passed)}, filtered {len(failed)}")
            self.state_machine.transition(WorkflowState.FILTERED)
            
            return StepResult(
                step_id=step_id,
                status=StepStatus.SUCCESS,
                data=passed,
                duration=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"Step {step_id} failed: {e}")
            self.state_machine.transition(WorkflowState.FILTER_FAILED)
            
            return StepResult(
                step_id=step_id,
                status=StepStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time
            )
    
    async def _step_rewrite(self, contents: list[Content]) -> StepResult:
        """改写步骤"""
        step_id = "rewrite"
        start_time = time.time()
        
        try:
            self.logger.info(f"Step {step_id}: Rewriting {len(contents)} contents...")
            self.state_machine.transition(WorkflowState.REWRITING)
            
            rewrite_config = self.config.get("rewrite", {})
            rewrite_processor = RewriteProcessor(self.config)
            
            async with rewrite_processor:
                rewrite_config_obj = RewriteConfig(
                    strategy=RewriteStrategy(rewrite_config.get("default_strategy", "rewrite")),
                    min_word_count=rewrite_config.get("min_word_count", 500),
                    max_word_count=rewrite_config.get("max_word_count", 5000),
                    target_word_count=rewrite_config.get("target_word_count", 3000)
                )
                
                results = await rewrite_processor.rewrite_batch(contents, rewrite_config_obj)
                
                # 转换为 dict
                rewritten = []
                for result in results:
                    if result.success:
                        rewritten.append({
                            "title": result.title,
                            "content": result.rewritten_content,
                            "summary": result.summary,
                            "keywords": result.keywords,
                            "original": result.original_content.to_dict() if result.original_content else None
                        })
            
            self.logger.info(f"Step {step_id}: Rewrote {len(rewritten)} contents")
            self.state_machine.transition(WorkflowState.REWRITTEN)
            
            return StepResult(
                step_id=step_id,
                status=StepStatus.SUCCESS,
                data=rewritten,
                duration=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"Step {step_id} failed: {e}")
            self.state_machine.transition(WorkflowState.REWRITE_FAILED)
            
            return StepResult(
                step_id=step_id,
                status=StepStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time
            )
    
    async def _step_generate_image(self, contents: list[dict]) -> StepResult:
        """生成配图步骤"""
        step_id = "generate_image"
        start_time = time.time()
        
        try:
            self.logger.info(f"Step {step_id}: Generating images for {len(contents)} contents...")
            self.state_machine.transition(WorkflowState.IMAGE_GENERATING)
            
            image_config = self.config.get("image", {})
            image_processor = ImageProcessor(self.config)
            
            async with image_processor:
                for content in contents:
                    img_config = ImageConfig(
                        count=image_config.get("default_count", 3)
                    )
                    
                    result = await image_processor.generate(
                        title=content.get("title", ""),
                        content=content.get("content", ""),
                        config=img_config
                    )
                    
                    if result.success:
                        content["images"] = [
                            {"id": img.id, "url": img.url, "prompt": img.prompt}
                            for img in result.images
                        ]
                    else:
                        self.logger.warning(f"Image generation failed: {result.error}")
                        content["images"] = []
            
            self.logger.info(f"Step {step_id}: Generated images")
            self.state_machine.transition(WorkflowState.IMAGED)
            
            return StepResult(
                step_id=step_id,
                status=StepStatus.SUCCESS,
                data=contents,
                duration=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"Step {step_id} failed: {e}")
            self.state_machine.transition(WorkflowState.IMAGE_FAILED)
            
            # 图片生成失败可以跳过
            return StepResult(
                step_id=step_id,
                status=StepStatus.SKIPPED,
                error=str(e),
                duration=time.time() - start_time
            )
    
    async def _step_format(self, contents: list[dict]) -> StepResult:
        """格式化步骤"""
        step_id = "format"
        start_time = time.time()
        
        try:
            self.logger.info(f"Step {step_id}: Formatting {len(contents)} contents...")
            self.state_machine.transition(WorkflowState.FORMATTING)
            
            formatter = ContentFormatter(self.config)
            
            for content in contents:
                images = [img.get("url") for img in content.get("images", []) if img.get("url")]
                
                formatted = formatter.format(
                    title=content.get("title", ""),
                    content=content.get("content", ""),
                    summary=content.get("summary", ""),
                    images=images,
                    config=FormatConfig(format=OutputFormat.MARKDOWN)
                )
                
                content["formatted_content"] = formatted
            
            self.logger.info(f"Step {step_id}: Formatted {len(contents)} contents")
            self.state_machine.transition(WorkflowState.FORMATTED)
            
            return StepResult(
                step_id=step_id,
                status=StepStatus.SUCCESS,
                data=contents,
                duration=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"Step {step_id} failed: {e}")
            self.state_machine.transition(WorkflowState.FORMAT_FAILED)
            
            return StepResult(
                step_id=step_id,
                status=StepStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time
            )
    
    async def _step_publish(self, contents: list[dict]) -> StepResult:
        """发布步骤"""
        step_id = "publish"
        start_time = time.time()
        
        try:
            self.logger.info(f"Step {step_id}: Publishing {len(contents)} contents...")
            self.state_machine.transition(WorkflowState.PUBLISHING)
            
            # TODO: 调用发布模块发布内容
            # 这里简化处理
            
            published = []
            for content in contents:
                published.append({
                    **content,
                    "published": True,
                    "published_at": datetime.now().isoformat()
                })
            
            self.logger.info(f"Step {step_id}: Published {len(published)} contents")
            self.state_machine.transition(WorkflowState.PUBLISHED)
            
            return StepResult(
                step_id=step_id,
                status=StepStatus.SUCCESS,
                data=published,
                duration=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"Step {step_id} failed: {e}")
            self.state_machine.transition(WorkflowState.PUBLISH_FAILED)
            
            return StepResult(
                step_id=step_id,
                status=StepStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time
            )
