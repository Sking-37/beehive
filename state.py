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


def _merge_subtasks(existing: list[dict], updates: list[dict]) -> list[dict]:
    """
    subtasks reducer：增量合并更新后的任务状态。
    每个 Agent 返回的 subtasks 只包含自己负责的任务子集，
    将这些增量合并到全局列表中（按 task_id 去重，后者覆盖前者）。
    """
    if not existing:
        return list(updates)
    merged = {t["id"]: t for t in existing}
    for t in updates:
        merged[t["id"]] = t
    return list(merged.values())


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
            final_result=None,
            logs=[],
            messages=[],
        )

    def duration(self) -> float:
        """返回执行耗时（秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0