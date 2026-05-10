"""
工作流状态机
"""

from enum import Enum
from typing import Set


class WorkflowState(Enum):
    """工作流状态"""
    # 初始状态
    PENDING = "pending"
    
    # 采集阶段
    COLLECTING = "collecting"
    COLLECTED = "collected"
    COLLECTION_FAILED = "collection_failed"
    
    # 筛选阶段
    FILTERING = "filtering"
    FILTERED = "filtered"
    FILTER_FAILED = "filter_failed"
    
    # 改写阶段
    REWRITING = "rewriting"
    REWRITTEN = "rewritten"
    REWRITE_FAILED = "rewrite_failed"
    
    # 配图阶段
    IMAGE_GENERATING = "image_generating"
    IMAGED = "imaged"
    IMAGE_FAILED = "image_failed"
    
    # 格式化阶段
    FORMATTING = "formatting"
    FORMATTED = "formatted"
    FORMAT_FAILED = "format_failed"
    
    # 审核阶段
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    
    # 发布阶段
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PUBLISH_FAILED = "publish_failed"
    
    # 终态
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class WorkflowStateMachine:
    """工作流状态机"""
    
    # 状态转换规则
    TRANSITIONS = {
        # 从 PENDING 开始
        WorkflowState.PENDING: {WorkflowState.COLLECTING},
        
        # 采集阶段
        WorkflowState.COLLECTING: {WorkflowState.COLLECTED, WorkflowState.COLLECTION_FAILED},
        WorkflowState.COLLECTED: {WorkflowState.FILTERING},
        WorkflowState.COLLECTION_FAILED: {WorkflowState.COLLECTING},  # 可重试
        
        # 筛选阶段
        WorkflowState.FILTERING: {WorkflowState.FILTERED, WorkflowState.FILTER_FAILED},
        WorkflowState.FILTERED: {WorkflowState.REWRITING},
        WorkflowState.FILTER_FAILED: {WorkflowState.FILTERING},  # 可重试
        
        # 改写阶段
        WorkflowState.REWRITING: {WorkflowState.REWRITTEN, WorkflowState.REWRITE_FAILED},
        WorkflowState.REWRITTEN: {WorkflowState.IMAGE_GENERATING, WorkflowState.FORMATTING},
        WorkflowState.REWRITE_FAILED: {WorkflowState.REWRITING},  # 可重试
        
        # 配图阶段（可选）
        WorkflowState.IMAGE_GENERATING: {WorkflowState.IMAGED, WorkflowState.IMAGE_FAILED},
        WorkflowState.IMAGED: {WorkflowState.FORMATTING},
        WorkflowState.IMAGE_FAILED: {WorkflowState.FORMATTING},  # 可跳过
        
        # 格式化阶段
        WorkflowState.FORMATTING: {WorkflowState.FORMATTED, WorkflowState.FORMAT_FAILED},
        WorkflowState.FORMATTED: {WorkflowState.PENDING_REVIEW, WorkflowState.APPROVED},
        WorkflowState.FORMAT_FAILED: {WorkflowState.FORMATTING},  # 可重试
        
        # 审核阶段
        WorkflowState.PENDING_REVIEW: {WorkflowState.APPROVED, WorkflowState.REJECTED},
        WorkflowState.APPROVED: {WorkflowState.PUBLISHING},
        WorkflowState.REJECTED: {},  # 终态
        
        # 发布阶段
        WorkflowState.PUBLISHING: {WorkflowState.PUBLISHED, WorkflowState.PUBLISH_FAILED},
        WorkflowState.PUBLISHED: {WorkflowState.ARCHIVED},
        WorkflowState.PUBLISH_FAILED: {WorkflowState.PUBLISHING},  # 可重试
        
        # 终态
        WorkflowState.ARCHIVED: {},
        WorkflowState.CANCELLED: {},
    }
    
    def __init__(self):
        self.current_state = WorkflowState.PENDING
        self.state_history = [WorkflowState.PENDING]
    
    def transition(self, new_state: WorkflowState) -> bool:
        """状态转换"""
        if self.can_transition(new_state):
            self.current_state = new_state
            self.state_history.append(new_state)
            return True
        return False
    
    def can_transition(self, new_state: WorkflowState) -> bool:
        """检查是否可以转换到新状态"""
        allowed_states = self.TRANSITIONS.get(self.current_state, set())
        return new_state in allowed_states
    
    def get_allowed_transitions(self) -> Set[WorkflowState]:
        """获取允许的转换目标"""
        return self.TRANSITIONS.get(self.current_state, set())
    
    def is_terminal_state(self) -> bool:
        """检查是否为终态"""
        return self.current_state in {
            WorkflowState.REJECTED,
            WorkflowState.ARCHIVED,
            WorkflowState.CANCELLED,
        }
    
    def is_failed_state(self) -> bool:
        """检查是否为失败状态"""
        return self.current_state in {
            WorkflowState.COLLECTION_FAILED,
            WorkflowState.FILTER_FAILED,
            WorkflowState.REWRITE_FAILED,
            WorkflowState.IMAGE_FAILED,
            WorkflowState.FORMAT_FAILED,
            WorkflowState.PUBLISH_FAILED,
            WorkflowState.REJECTED,
        }
    
    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return self.current_state in {
            WorkflowState.COLLECTION_FAILED,
            WorkflowState.FILTER_FAILED,
            WorkflowState.REWRITE_FAILED,
            WorkflowState.FORMAT_FAILED,
            WorkflowState.PUBLISH_FAILED,
        }
    
    def get_retry_state(self) -> WorkflowState:
        """获取重试时应转换到的状态"""
        retry_map = {
            WorkflowState.COLLECTION_FAILED: WorkflowState.COLLECTING,
            WorkflowState.FILTER_FAILED: WorkflowState.FILTERING,
            WorkflowState.REWRITE_FAILED: WorkflowState.REWRITING,
            WorkflowState.FORMAT_FAILED: WorkflowState.FORMATTING,
            WorkflowState.PUBLISH_FAILED: WorkflowState.PUBLISHING,
        }
        return retry_map.get(self.current_state, self.current_state)
    
    def reset(self):
        """重置状态机"""
        self.current_state = WorkflowState.PENDING
        self.state_history = [WorkflowState.PENDING]
    
    def get_state(self) -> WorkflowState:
        """获取当前状态"""
        return self.current_state
    
    def get_history(self) -> list[WorkflowState]:
        """获取状态历史"""
        return self.state_history.copy()
