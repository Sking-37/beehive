"""
蜂群状态定义
定义任务执行过程中的所有状态字段
"""
from typing import TypedDict, Annotated, Optional, Sequence
from langgraph.graph import add_messages
from datetime import datetime


# ── 字段 reducer ─────────────────────────────────────────

_LWW = lambda old, new: new          # last-write-wins，并发安全
_append_or_create = lambda old, new: (old if old else []) + (new if new else [])


def _append_logs(existing: list, updates: Sequence) -> list:
    """日志字段 reducer：追加新日志（允许多节点并发追加）"""
    if not existing:
        existing = []
    if isinstance(updates, str):
        updates = [updates]
    return existing + list(updates)


def _detect_cycle(subtasks: list[dict]) -> bool:
    """
    检测 subtasks 中是否存在循环依赖。
    用 DFS 检查：有向图中是否存在环。
    返回 True = 有环（异常），False = 无环（正常）。
    """
    graph: dict[str, list[str]] = {}
    for t in subtasks:
        graph[t["id"]] = t.get("depends_on", [])

    visited = set()
    rec_stack = set()

    def has_cycle(node: str) -> bool:
        if node in rec_stack:
            return True  # 回边，发现环
        if node in visited:
            return False
        visited.add(node)
        rec_stack.add(node)
        for dep in graph.get(node, []):
            if has_cycle(dep):
                return True
        rec_stack.remove(node)
        return False

    for node_id in graph:
        if node_id not in visited:
            if has_cycle(node_id):
                return True
    return False


def _merge_subtasks(existing: list[dict], updates: list[dict]) -> list[dict]:
    """
    subtasks reducer：增量合并更新后的任务状态。
    每个 Agent 返回的 subtasks 只包含自己负责的任务子集，
    将这些增量合并到全局列表中（按 task_id 去重，后者覆盖前者）。

    如果合并后检测到循环依赖，打印警告并保留原有任务列表。
    """
    if not existing:
        merged = list(updates)
        if _detect_cycle(merged):
            print(f"[蜂群警告] 检测到循环依赖，已拒绝更新！")
            return []  # 有环时返回空（不会真正生效，LangGraph 会用旧状态）
        return merged

    # 合并：existing 优先（保持已完成任务的状态），updates 补充新任务
    merged = {t["id"]: t for t in existing}
    for t in updates:
        merged[t["id"]] = t

    result = list(merged.values())

    # 循环依赖检测：有环时拒绝更新，保留原有列表
    if _detect_cycle(result):
        print(f"[蜂群警告] 检测到循环依赖，已拒绝本次更新，保留原有状态")
        return list(existing)

    return result


class SubTask(TypedDict, total=False):
    """子任务定义"""
    id: str
    description: str
    assigned_to: str
    depends_on: list[str]
    output_format: str
    status: str
    result: Optional[str]
    error: Optional[str]
    confidence: Optional[float]
    attempts: int


class AgentState(TypedDict):
    """
    全局状态——贯穿整个任务图。

    ⚠️ 所有字段都用 Annotated 标注了 reducer。
    LangGraph 的并发图结构（plan → [A,B,C,D]）会导致多个节点在同一步
    写回 state，不标注的字段会报 InvalidUpdateError。
    """
    # 顶层信息（初始化后不变，但并发边会触发写回，用 last-write-wins）
    task_id: Annotated[str, _LWW]
    user_task: Annotated[str, _LWW]
    created_at: Annotated[str, _LWW]

    # 领头模型规划结果
    subtasks: Annotated[list[SubTask], _merge_subtasks]   # 增量合并
    current_plan: Annotated[str, _LWW]
    loop_count: Annotated[int, _LWW]

    # 各 Agent 执行结果（各自独占，但并发图结构中需标注）
    researcher_results: Annotated[list[dict], _append_or_create]
    coder_results: Annotated[list[dict], _append_or_create]
    writer_results: Annotated[list[dict], _append_or_create]
    reviewer_results: Annotated[list[dict], _append_or_create]

    # 评估与控制
    evaluation: Annotated[str, _LWW]
    evaluation_reason: Annotated[str, _LWW]
    next_action: Annotated[str, _LWW]

    # ── 并行分发专用字段（Send API 模式）────────────────────
    # Send 分发的单任务信息，由 plan_dispatch 填充
    current_subtask_id: Annotated[str, _LWW]       # 当前要执行的子任务 ID
    current_subtask_desc: Annotated[str, _LWW]      # 当前子任务描述
    current_node_role: Annotated[str, _LWW]         # 节点角色：'parallel'/'researcher'/'coder'/'writer'/'reviewer'
    # ─────────────────────────────────────────────────────────

    # 最终输出
    final_result: Annotated[Optional[dict], _LWW]
    logs: Annotated[list[str], _append_logs]   # 并发追加日志
    messages: Annotated[list, add_messages]       # LangGraph 内置消息传递


class ExecutionContext:
    """任务执行上下文——贯穿单个任务的生命周期"""

    def __init__(self, task_id: str, user_task: str):
        self.task_id = task_id
        self.user_task = user_task
        self.created_at = datetime.now().isoformat()
        self.status = "pending"
        self.loop_count = 0
        self.start_time = None
        self.end_time = None

    def to_state(self) -> AgentState:
        """转换为 LangGraph 使用的状态字典"""
        return AgentState(
            task_id=self.task_id,
            user_task=self.user_task,
            created_at=self.created_at,
            subtasks=[],
            current_plan="",
            loop_count=0,
            researcher_results=[],
            coder_results=[],
            writer_results=[],
            reviewer_results=[],
            evaluation="pending",
            evaluation_reason="",
            next_action="",
            current_subtask_id="",
            current_subtask_desc="",
            current_node_role="",
            final_result=None,
            logs=[],
            messages=[],
        )

    def duration(self) -> float:
        """返回执行耗时（秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0