"""
蜂群任务图 - LangGraph 编排层
定义节点、边、以及条件路由逻辑
"""
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from beehive.state import AgentState
from beehive.agents import (
    orchestrator_plan,
    orchestrator_evaluate,
    researcher_agent,
    coder_agent,
    writer_agent,
    reviewer_agent,
)


def build_task_graph():
    """构建完整的任务执行图"""
    
    # 创建状态图
    graph = StateGraph(AgentState)
    
    # ─── 节点定义 ───
    
    # 1. 领头模型：拆解任务
    graph.add_node("plan", orchestrator_plan, name="任务拆解")
    
    # 2. 执行层节点（可并行）
    graph.add_node("researcher", researcher_agent, name="研究员Agent")
    graph.add_node("coder", coder_agent, name="程序员Agent")
    graph.add_node("writer", writer_agent, name="文案Agent")
    graph.add_node("reviewer", reviewer_agent, name="评审Agent")
    
    # 3. 领头模型：评估结果
    graph.add_node("evaluate", orchestrator_evaluate, name="结果评估")
    
    # ─── 边定义 ───

    # 入口：拆解任务
    graph.set_entry_point("plan")

    # 拆解完成后，并行触发执行 Agent（3个并行，reviewer 除外）
    graph.add_edge("plan", "researcher")
    graph.add_edge("plan", "coder")
    graph.add_edge("plan", "writer")

    # reviewer 必须在 writer 完成后才能审，所以串行在 writer 之后
    graph.add_edge("writer", "reviewer")

    # researcher/coder 完成后也触发 review（内容可能来自多个 Agent）
    graph.add_edge("researcher", "reviewer")
    graph.add_edge("coder", "reviewer")

    # review 完成后进入评估
    graph.add_edge("reviewer", "evaluate")

    # ─── 条件边：根据评估结果决定下一步 ───

    def route_after_evaluate(state: AgentState) -> str:
        """评估后路由：根据 next_action 决定下一步"""
        action = state.get("next_action", "")

        if action in ("continue", "retry"):
            return "plan"
        else:
            return END

    graph.add_conditional_edges(
        "evaluate",
        route_after_evaluate,
        {"plan": "plan", END: END},
    )

    return graph.compile()


def build_simple_graph():
    """
    简化版任务图（单轮执行，无循环）
    适用于：任务拆解 → 串行执行 → 评估结束
    """
    graph = StateGraph(AgentState)
    
    graph.add_node("plan", orchestrator_plan)
    graph.add_node("researcher", researcher_agent)
    graph.add_node("coder", coder_agent)
    graph.add_node("writer", writer_agent)
    graph.add_node("evaluate", orchestrator_evaluate)
    
    graph.set_entry_point("plan")
    
    # 串行执行（简单但慢）
    graph.add_edge("plan", "researcher")
    graph.add_edge("researcher", "coder")
    graph.add_edge("coder", "writer")
    graph.add_edge("writer", "evaluate")
    graph.add_edge("evaluate", END)
    
    return graph.compile()


# 全局单例，惰性加载
_task_graph = None


def get_task_graph() -> CompiledStateGraph:
    """获取任务图实例"""
    global _task_graph
    if _task_graph is None:
        _task_graph = build_task_graph()
    return _task_graph


def get_simple_graph() -> CompiledStateGraph:
    """获取简化版任务图实例"""
    return build_simple_graph()