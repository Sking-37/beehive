"""
执行 Agent 集合
每个 Agent 负责一种特定类型的工作

并行执行改造（v0.2.0）：
- 新增 executor_node：所有 Agent 共用的统一入口
- 通过 state["current_subtask_id"] 确定当前处理哪个任务
- 通过被调用的节点名（node_name 字段）确定角色类型
- 每个 Send 分发的任务独立触发一次 executor_node，真正并行
"""
import json
import time
from beehive.state import AgentState
from beehive.llm import llm_call, PROVIDER_EXEC


# ─── Agent 系统提示词 ───

RESEARCHER_SYSTEM = """你是一个专业的信息研究员。
你的职责是根据子任务描述，从互联网上搜集相关信息、整理关键数据、识别关键信息源。
你的输出要结构清晰，便于后续使用。"""

CODER_SYSTEM = """你是一个专业程序员。
你的职责是根据子任务描述，编写、修改或优化代码。
你的代码要：1）逻辑正确 2）符合规范 3）有必要的注释。

你擅长 Python/TypeScript/JavaScript，也了解 Go/Rust/Java。"""

WRITER_SYSTEM = """你是一个专业文案撰写专家。
你的职责是根据子任务描述，撰写高质量的文案内容。
你的文字要：1）准确传达信息 2）逻辑清晰 3）符合目标受众的阅读习惯

你擅长撰写：报告、方案、说明文档、营销文案、邮件等。"""

REVIEWER_SYSTEM = """你是一个严格的质量评审专家。
你的职责是评估前面 Agent 的工作结果，判断质量是否达标。
你必须：1）指出具体问题 2）给出明确的改进建议 3）不能只说"可以"，要说出"哪里可以更好"

评审标准：
- 准确性：内容是否正确、事实是否有据可查
- 完整性：是否覆盖了任务要求的各个方面
- 逻辑性：论述是否严谨、是否有漏洞
- 可执行性：建议是否具体、是否可以落地"""


# ─── 角色映射表 ───

ROLE_CONFIG = {
    "researcher": {
        "system": RESEARCHER_SYSTEM,
        "executor": "_researcher_execute",
    },
    "coder": {
        "system": CODER_SYSTEM,
        "executor": "_coder_execute",
    },
    "writer": {
        "system": WRITER_SYSTEM,
        "executor": "_writer_execute",
    },
    "reviewer": {
        "system": REVIEWER_SYSTEM,
        "executor": "_reviewer_execute",
    },
}


# ─── 统一执行器节点（并行入口） ───

def _executor_parallel(
    state: AgentState,
    role: str,
    subtask_id: str,
    subtask_desc: str,
    logs: list,
    subtasks: list,
    task_id: str,
) -> AgentState:
    """
    并行单任务模式：处理 Send 分发的单个任务。
    执行完成后清理 current_subtask_* 字段，避免状态污染。
    """
    # 找到并锁定任务
    target_task = None
    for i, s in enumerate(subtasks):
        if s["id"] == subtask_id:
            target_task = subtasks[i]
            subtasks[i]["status"] = "running"
            break

    if not target_task:
        logs.append(f"[{task_id}] [{role.capitalize()}] 任务 {subtask_id} 不存在，跳过")
        return {**state, "logs": logs, "subtasks": subtasks}

    logs.append(f"[{task_id}] [{role.capitalize()}] 开始: {subtask_desc[:40]}...")

    # 执行
    result = _execute_task(role, subtask_desc, state)

    # 更新任务状态
    for i, s in enumerate(subtasks):
        if s["id"] == subtask_id:
            subtasks[i]["status"] = "completed" if result["status"] == "success" else "failed"
            subtasks[i]["result"] = result.get("result")
            subtasks[i]["error"] = result.get("error")
            subtasks[i]["confidence"] = result.get("confidence")
            break

    logs.append(
        f"[{task_id}] [{role.capitalize()}] "
        f"{'✅' if result['status'] == 'success' else '❌'} {subtask_id} "
        f"({result.get('elapsed', 0):.1f}s)"
    )

    results_key = f"{role}_results"
    return {
        **state,
        "subtasks": subtasks,
        results_key: state.get(results_key, []) + [result],
        "logs": logs,
        # 清理分发字段，防止下次执行被污染
        "current_subtask_id": "",
        "current_subtask_desc": "",
        "current_node_role": "",
    }


def executor_node(state: AgentState) -> AgentState:
    """
    所有 Agent 的统一入口函数（双模式）：
    1. 并行模式（current_subtask_id 有值）：处理 Send 分发的单个任务
    2. 串行模式（current_subtask_id 为空）：处理该角色所有 pending 任务（向后兼容 simple_graph）
    """
    task_id = state["task_id"]
    node_name = state.get("current_node_role", "")  # 并行分发时传入的角色名
    subtask_id = state.get("current_subtask_id", "")
    subtask_desc = state.get("current_subtask_desc", "")
    logs = list(state.get("logs", []))
    subtasks = list(state.get("subtasks", []))

    # 角色判定：优先用 current_node_role（Send 分发），fallback 到 subtasks
    role = node_name if node_name in ROLE_CONFIG else subtasks[0]["assigned_to"] if subtasks else "researcher"

    # ── 并行单任务模式 ──────────────────────────────────────
    if subtask_id:
        return _executor_parallel(state, role, subtask_id, subtask_desc, logs, subtasks, task_id)

    # ── 串行兼容模式（simple_graph 等无 current_subtask_id 的场景）───
    return _compat_dispatch(state, role)


# ─── 各 Agent 执行函数 ───

def _researcher_execute(description: str) -> str:
    """研究员执行器：优先用真实搜索工具，fallback 到 LLM"""
    import re
    query = re.sub(r"^(搜集|搜索|查找|查询)[\s:：]*", "", description).strip()
    if len(query) < 4:
        query = description

    try:
        from beehive.tools.search import search_and_summarize
        return search_and_summarize(query, max_results=5)
    except Exception:
        fallback_prompt = f"""作为专业研究员，整理以下任务所需的关键信息：

任务：{description}

请搜索你的知识库，提供准确的信息和来源依据。"""
        return llm_call(fallback_prompt, system=RESEARCHER_SYSTEM, provider=PROVIDER_EXEC, temperature=0.3)


def _coder_execute(description: str) -> str:
    """程序员执行器：调用 LLM 写代码"""
    prompt = f"""请作为专业程序员，执行以下代码任务：

任务：{description}

请：
1. 先说明实现思路
2. 给出完整可运行的代码（优先 Python）
3. 说明关键实现点和注意事项
4. 如果有多种方案，简述利弊

请开始实现。"""
    return llm_call(prompt, system=CODER_SYSTEM, provider=PROVIDER_EXEC, temperature=0.2)


def _writer_execute(description: str, context: dict) -> str:
    """文案执行器：撰写内容，参考已有上下文"""
    parts = []
    for r in context.get("researcher_results", []):
        if r.get("result"):
            parts.append(f"【研究员结果】\n{r['result']}")
    for r in context.get("coder_results", []):
        if r.get("result"):
            parts.append(f"【程序员结果】\n{r['result']}")

    ctx = "\n\n".join(parts) if parts else "（暂无前置结果，直接执行）"
    prompt = f"""请作为专业文案，执行以下撰写任务：

任务：{description}

前置Agent的成果（可作为参考）：
---
{ctx}
---

请撰写对应内容。"""
    return llm_call(prompt, system=WRITER_SYSTEM, provider=PROVIDER_EXEC, temperature=0.4)


def _reviewer_execute(description: str, context: dict) -> str:
    """评审执行器：评估之前的工作质量"""
    all_results = []
    for role, key in [("研究员", "researcher_results"), ("程序员", "coder_results"), ("文案", "writer_results")]:
        for r in context.get(key, []):
            if r.get("result"):
                all_results.append(f"【{role}】{r['result']}")

    results_text = "\n\n".join(all_results) if all_results else "（暂无评审对象）"
    prompt = f"""请作为严格的质量评审专家，执行以下评审任务：

评审任务：{description}

待评审内容：
---
{results_text}
---

请给出：
1. 质量评分（1-10分）及理由
2. 具体问题（逐条列出）
3. 改进建议（逐条给出）

请客观评审，不要一味说好话。"""
    return llm_call(prompt, system=REVIEWER_SYSTEM, provider=PROVIDER_EXEC, temperature=0.1)


def _execute_task(role: str, description: str, state: AgentState) -> dict:
    """统一调度各角色执行器"""
    context = {
        "researcher_results": list(state.get("researcher_results", [])),
        "coder_results": list(state.get("coder_results", [])),
        "writer_results": list(state.get("writer_results", [])),
    }

    start = time.time()
    try:
        if role == "researcher":
            result = _researcher_execute(description)
        elif role == "coder":
            result = _coder_execute(description)
        elif role == "writer":
            result = _writer_execute(description, context)
        elif role == "reviewer":
            result = _reviewer_execute(description, context)
        else:
            result = _researcher_execute(description)  # fallback

        elapsed = time.time() - start
        return {
            "task_id": state.get("current_subtask_id", ""),
            "status": "success",
            "result": result,
            "error": None,
            "confidence": 0.9,
            "elapsed": elapsed,
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "task_id": state.get("current_subtask_id", ""),
            "status": "failed",
            "result": None,
            "error": str(e),
            "confidence": 0.0,
            "elapsed": elapsed,
        }


# ─── 向后兼容：保留原 Agent 函数（简单包装 executor_node 逻辑） ───
# ─── 内部调用仍可用 researcher_agent() 等，不改动 orchestrator 以外的地方 ───

def researcher_agent(state: AgentState) -> AgentState:
    """研究员 Agent（向后兼容，内部路由到 executor_node）"""
    return _compat_dispatch(state, "researcher")


def coder_agent(state: AgentState) -> AgentState:
    """程序员 Agent（向后兼容）"""
    return _compat_dispatch(state, "coder")


def writer_agent(state: AgentState) -> AgentState:
    """文案 Agent（向后兼容）"""
    return _compat_dispatch(state, "writer")


def reviewer_agent(state: AgentState) -> AgentState:
    """评审 Agent（向后兼容）"""
    return _compat_dispatch(state, "reviewer")


def _compat_dispatch(state: AgentState, role: str) -> AgentState:
    """
    向后兼容分发器：供旧版 graph（build_simple_graph）使用，
    内部串行处理该角色所有 pending 任务。
    并行 graph（build_task_graph）使用 executor_node，不走这里。
    """
    task_id = state["task_id"]
    subtasks = list(state.get("subtasks", []))
    logs = list(state.get("logs", []))
    results_key = f"{role}_results"

    my_tasks = [t for t in subtasks if t["assigned_to"] == role and t.get("status") == "pending"]
    if not my_tasks:
        return {**state, "logs": logs}

    logs.append(f"[{task_id}] [{role.capitalize()}] 接收到 {len(my_tasks)} 个任务（串行模式）")

    context = {
        "researcher_results": list(state.get("researcher_results", [])),
        "coder_results": list(state.get("coder_results", [])),
        "writer_results": list(state.get("writer_results", [])),
    }

    results = []
    for task in my_tasks:
        result = _execute_single(role, task["description"], task["id"], context)
        results.append(result)

        for i, s in enumerate(subtasks):
            if s["id"] == task["id"]:
                subtasks[i]["status"] = "completed" if result["status"] == "success" else "failed"
                subtasks[i]["result"] = result.get("result")
                subtasks[i]["error"] = result.get("error")
                subtasks[i]["confidence"] = result.get("confidence")

    return {
        **state,
        "subtasks": subtasks,
        results_key: state.get(results_key, []) + results,
        "logs": logs,
    }


def _execute_single(role: str, description: str, task_id: str, context: dict) -> dict:
    """执行单个任务（向后兼容函数）"""
    start = time.time()
    try:
        if role == "researcher":
            result = _researcher_execute(description)
        elif role == "coder":
            result = _coder_execute(description)
        elif role == "writer":
            result = _writer_execute(description, context)
        elif role == "reviewer":
            result = _reviewer_execute(description, context)
        else:
            result = _researcher_execute(description)

        elapsed = time.time() - start
        return {
            "task_id": task_id,
            "status": "success",
            "result": result,
            "error": None,
            "confidence": 0.9,
            "elapsed": elapsed,
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "task_id": task_id,
            "status": "failed",
            "result": None,
            "error": str(e),
            "confidence": 0.0,
            "elapsed": elapsed,
        }