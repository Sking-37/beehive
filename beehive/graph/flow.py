"""
蜂群任务图 - LangGraph 编排层
定义节点、边、以及条件路由逻辑

并行执行改造（v0.2.0）：
- plan 节点用 Send API 直接分发单任务到各 Agent，不再走固定边
- 各 Agent 同时接收任务、并发执行
- 每个 Agent 只处理自己负责的任务，不再内部串行循环
"""
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.constants import Send
from beehive.state import AgentState
from beehive.agents import (
    orchestrator_plan,
    orchestrator_evaluate,
    executor_node,
)


def plan_dispatch(state: AgentState) -> list[Send]:
    """
    plan 节点完成后立即分发：根据 subtasks 列表生成 Send 对象列表。
    只分发无依赖或依赖已全部完成（completed/failed）的 pending 任务。
    有依赖的任务由 evaluate 节点再次调用 plan_dispatch 判断是否可分发。
    """
    subtasks = state.get("subtasks", [])
    pending = [s for s in subtasks if s.get("status") == "pending"]

    completed_ids = {
        s["id"]
        for s in subtasks
        if s.get("status") in ("completed", "failed")
    }

    def can_dispatch(task: dict) -> bool:
        deps = task.get("depends_on", [])
        return all(d in completed_ids for d in deps)

    dispatchable = [s for s in pending if can_dispatch(s)]

    return [
        Send(
            s["assigned_to"],
            {
                **state,
                # 单任务模式：只带当前要处理的任务
                "current_subtask_id": s["id"],
                "current_subtask_desc": s["description"],
                # 显式传入角色名（Send 不带节点名，靠 state 传递）
                "current_node_role": s["assigned_to"],
            },
        )
        for s in dispatchable
    ]


def build_task_graph():
    """构建完整的任务执行图（并行版本）"""

    graph = StateGraph(AgentState)

    # ─── 节点定义 ───

    # 1. 领头模型：拆解任务
    graph.add_node("plan", orchestrator_plan, name="任务拆解")

    # 2. 执行层：所有 Agent 共用同一个节点函数，内部根据 current_subtask_id 路由
    #    这样 Send 分发的每个任务都触发一次独立执行，真正并行
    graph.add_node("researcher", executor_node, name="研究员Agent")
    graph.add_node("coder", executor_node, name="程序员Agent")
    graph.add_node("writer", executor_node, name="文案Agent")
    graph.add_node("reviewer", executor_node, name="评审Agent")

    # 3. 领头模型：评估结果
    graph.add_node("evaluate", orchestrator_evaluate, name="结果评估")

    # ─── 边定义 ───

    # 入口：拆解任务
    graph.set_entry_point("plan")

    # plan 完成后，通过 Send API 并发分发到所有 pending 子任务
    graph.add_conditional_edges("plan", plan_dispatch)

    # 所有 Agent 完成后进入评估（用条件边，检查是否还有 pending 任务）
    def all_done_or_replan(state: AgentState) -> str:
        """所有执行节点都完成后，汇总进入 evaluate"""
        return END  # 统一从 evaluate 判断下一步

    # 各 Agent → evaluate
    graph.add_edge("researcher", "evaluate")
    graph.add_edge("coder", "evaluate")
    graph.add_edge("writer", "evaluate")
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
    graph.add_node("researcher", executor_node)
    graph.add_node("coder", executor_node)
    graph.add_node("writer", executor_node)
    graph.add_node("evaluate", orchestrator_evaluate)

    graph.set_entry_point("plan")

    # 串行执行（简单但慢，用于简单/调试场景）
    graph.add_edge("plan", "researcher")
    graph.add_edge("researcher", "coder")
    graph.add_edge("coder", "writer")
    graph.add_edge("writer", "evaluate")
    graph.add_edge("evaluate", END)

    return graph.compile()


# 全局单例，惰性加载
_task_graph = None


def get_task_graph() -> CompiledStateGraph:
    """获取任务图实例（并行版本）"""
    global _task_graph
    if _task_graph is None:
        _task_graph = build_task_graph()
    return _task_graph


def get_simple_graph() -> CompiledStateGraph:
    """获取简化版任务图实例"""
    return build_simple_graph()