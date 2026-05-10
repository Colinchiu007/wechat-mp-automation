"""
测试工作流引擎
"""

import pytest
from datetime import datetime

from src.workflows.engine import WorkflowEngine, WorkflowResult
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
            "workflows": {
                "default": {
                    "name": "测试工作流",
                    "timeout": 3600
                }
            }
        }
        
        engine = WorkflowEngine(config)
        assert engine is not None
        assert "default" in engine.workflows
    
    @pytest.mark.asyncio
    async def test_run_workflow(self):
        """测试运行工作流"""
        config = {
            "workflows": {
                "default": {
                    "name": "测试工作流",
                    "timeout": 3600
                }
            }
        }
        
        engine = WorkflowEngine(config)
        result = await engine.run("default")
        
        assert isinstance(result, WorkflowResult)
        # 因为没有配置数据源，应该失败
        # 但至少应该返回结果对象
        assert result.workflow_id is not None
        assert result.workflow_name == "default"
