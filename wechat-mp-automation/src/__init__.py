"""
微信公众号自动化 - 核心模块
"""

__version__ = "1.0.0"
__author__ = "Colinchiu007"

from src.config.loader import ConfigLoader
from src.workflows.engine import WorkflowEngine

__all__ = ["ConfigLoader", "WorkflowEngine"]
