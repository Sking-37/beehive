"""Agent 集合导出"""
from beehive.agents.orchestrator import orchestrator_plan, orchestrator_evaluate
from beehive.agents.executors import executor_node

# 保持向后兼容的别名（内部调用仍可用 researcher's 旧函数名）
from beehive.agents.executors import (
    researcher_agent,
    coder_agent,
    writer_agent,
    reviewer_agent,
)

__all__ = [
    "orchestrator_plan",
    "orchestrator_evaluate",
    "executor_node",
    # 向后兼容别名
    "researcher_agent",
    "coder_agent",
    "writer_agent",
    "reviewer_agent",
]