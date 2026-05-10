"""
测试工作流引擎
"""

import pytest
from datetime import datetime

from src.workflows.engine import WorkflowEngine
from src.workflows.state_machine import WorkflowStateMachine, WorkflowState


class TestWorkflowStateMachine:
    """测试工作流状态机"""
    
    def test_initial_state(self):
        """测试初始状态"""
        sm = WorkflowStateMachine()
        assert sm.get_state() == WorkflowState.PENDING
    
    def test_valid_transition(self):
        """测试有效状态转换"""
        sm = WorkflowStateMachine()
        assert sm.transition(WorkflowState.COLLECTING) == True
        assert sm.get_state() == WorkflowState.COLLECTING
    
    def test_invalid_transition(self):
        """测试无效状态转换"""
        sm = WorkflowStateMachine()
        # 不能从 PENDING 直接跳到 PUBLISHED
        assert sm.transition(WorkflowState.PUBLISHED) == False
        assert sm.get_state() == WorkflowState.PENDING
    
    def test_can_retry(self):
        """测试重试状态"""
        sm = WorkflowStateMachine()
        sm.transition(WorkflowState.COLLECTING)
        sm.transition(WorkflowState.COLLECTION_FAILED)
        
        assert sm.can_retry() == True
        assert sm.get_retry_state() == WorkflowState.COLLECTING
    
    def test_terminal_state(self):
        """测试终态"""
        sm = WorkflowStateMachine()
        
        # 正常流程
        sm.transition(WorkflowState.COLLECTING)
        sm.transition(WorkflowState.COLLECTED)
        sm.transition(WorkflowState.FILTERING)
        sm.transition(WorkflowState.FILTERED)
        sm.transition(WorkflowState.REWRITING)
        sm.transition(WorkflowState.REWRITTEN)
        sm.transition(WorkflowState.FORMATTING)
        sm.transition(WorkflowState.FORMATTED)
        sm.transition(WorkflowState.APPROVED)
        sm.transition(WorkflowState.PUBLISHING)
        sm.transition(WorkflowState.PUBLISHED)
        sm.transition(WorkflowState.ARCHIVED)
        
        assert sm.is_terminal_state() == True
        # 终态不能转换
        assert sm.transition(WorkflowState.COLLECTING) == False
    
    def test_rejected_state(self):
        """测试拒绝状态"""
        sm = WorkflowStateMachine()
        
        sm.transition(WorkflowState.COLLECTING)
        sm.transition(WorkflowState.COLLECTED)
        sm.transition(WorkflowState.FILTERING)
        sm.transition(WorkflowState.FILTERED)
        sm.transition(WorkflowState.REWRITING)
        sm.transition(WorkflowState.REWRITTEN)
        sm.transition(WorkflowState.FORMATTING)
        sm.transition(WorkflowState.FORMATTED)
        sm.transition(WorkflowState.PENDING_REVIEW)
        sm.transition(WorkflowState.REJECTED)
        
        assert sm.is_failed_state() == True
        assert sm.is_terminal_state() == True
    
    def test_history(self):
        """测试状态历史"""
        sm = WorkflowStateMachine()
        
        sm.transition(WorkflowState.COLLECTING)
        sm.transition(WorkflowState.COLLECTED)
        sm.transition(WorkflowState.FILTERING)
        
        history = sm.get_history()
        assert len(history) == 4
        assert history == [
            WorkflowState.PENDING,
            WorkflowState.COLLECTING,
            WorkflowState.COLLECTED,
            WorkflowState.FILTERING,
        ]
    
    def test_reset(self):
        """测试重置"""
        sm = WorkflowStateMachine()
        
        sm.transition(WorkflowState.COLLECTING)
        sm.transition(WorkflowState.COLLECTED)
        
        sm.reset()
        
        assert sm.get_state() == WorkflowState.PENDING
        assert len(sm.get_history()) == 1


class TestWorkflowEngine:
    """测试工作流引擎"""

    def test_engine_initialization(self):
        """测试引擎初始化"""
        config = {
            "database": {"path": ":memory:"},
            "llm": {"provider": "deepseek", "api_key": "test-key"},
        }
        engine = WorkflowEngine(config)
        assert engine is not None
        assert engine.batch_id == ""

    def test_engine_init_default(self):
        """测试引擎使用默认配置"""
        engine = WorkflowEngine()
        assert engine.config == {}

    @pytest.mark.asyncio
    async def test_run_workflow_no_sources(self):
        """测试无数据源时运行工作流"""
        config = {
            "database": {"path": ":memory:"},
            "llm": {"provider": "deepseek", "api_key": "test-key"},
        }
        engine = WorkflowEngine(config)
        result = await engine.run()
        assert "batch_id" in result
