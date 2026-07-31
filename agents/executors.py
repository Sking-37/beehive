"""
执行 Agent 集合
每个 Agent 负责一种特定类型的工作
"""
import json
import time
from typing import Callable
from beehive.state import AgentState, SubTask
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


# ─── 辅助函数 ───

def _run_single_task(
    task_desc: str,
    executor_fn: Callable[[str], str],
    task_id: str,
    task_role: str,
    logs: list,
) -> dict:
    """运行单个子任务，捕获异常，统一的执行包装器"""
    logs.append(f"  → [{task_role}] 开始执行: {task_desc[:40]}")
    
    start = time.time()
    try:
        result = executor_fn(task_desc)
        elapsed = time.time() - start
        logs.append(f"  → [{task_role}] 完成 {task_id}（{elapsed:.1f}s）")
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
        logs.append(f"  → [{task_role}] {task_id} 失败：{str(e)}（{elapsed:.1f}s）")
        return {
            "task_id": task_id,
            "status": "failed",
            "result": None,
            "error": str(e),
            "confidence": 0.0,
            "elapsed": elapsed,
        }


# ─── 各角色 Agent 入口 ───

def researcher_agent(state: AgentState) -> AgentState:
    """
    研究员 Agent：信息搜集
    负责执行所有 assigned_to='researcher' 的子任务
    """
    task_id = state["task_id"]
    subtasks = state.get("subtasks", [])
    logs = list(state.get("logs", []))
    
    my_tasks = [t for t in subtasks if t["assigned_to"] == "researcher" and t.get("status") == "pending"]
    
    if not my_tasks:
        return {**state, "logs": logs}
    
    logs.append(f"[{task_id}] [Researcher] 接收到 {len(my_tasks)} 个任务")
    
    results = []
    for task in my_tasks:
        task_desc = task["description"]  # 立即捕获，防止闭包陷阱
        
        # 更新状态为 running
        for s in subtasks:
            if s["id"] == task["id"]:
                s["status"] = "running"
        
        result = _run_single_task(
            task_desc=task_desc,
            executor_fn=_researcher_execute,
            task_id=task["id"],
            task_role=task["assigned_to"],
            logs=logs,
        )
        results.append(result)
        
        # 更新任务状态
        for s in subtasks:
            if s["id"] == task["id"]:
                s["status"] = "completed" if result["status"] == "success" else "failed"
                s["result"] = result["result"]
                s["error"] = result["error"]
                s["confidence"] = result["confidence"]
    
    return {
        **state,
        "subtasks": subtasks,
        "researcher_results": state.get("researcher_results", []) + results,
        "logs": logs,
    }


def coder_agent(state: AgentState) -> AgentState:
    """程序员 Agent：代码实现"""
    task_id = state["task_id"]
    subtasks = state.get("subtasks", [])
    logs = list(state.get("logs", []))
    
    my_tasks = [t for t in subtasks if t["assigned_to"] == "coder" and t.get("status") == "pending"]
    if not my_tasks:
        return {**state, "logs": logs}
    
    logs.append(f"[{task_id}] [Coder] 接收到 {len(my_tasks)} 个任务")
    
    results = []
    for task in my_tasks:
        task_desc = task["description"]
        for s in subtasks:
            if s["id"] == task["id"]:
                s["status"] = "running"
        
        result = _run_single_task(
            task_desc=task_desc,
            executor_fn=_coder_execute,
            task_id=task["id"],
            task_role=task["assigned_to"],
            logs=logs,
        )
        results.append(result)
        
        for s in subtasks:
            if s["id"] == task["id"]:
                s["status"] = "completed" if result["status"] == "success" else "failed"
                s["result"] = result["result"]
                s["error"] = result["error"]
                s["confidence"] = result["confidence"]
    
    return {
        **state,
        "subtasks": subtasks,
        "coder_results": state.get("coder_results", []) + results,
        "logs": logs,
    }


def writer_agent(state: AgentState) -> AgentState:
    """文案 Agent：内容撰写"""
    task_id = state["task_id"]
    subtasks = state.get("subtasks", [])
    logs = list(state.get("logs", []))
    
    my_tasks = [t for t in subtasks if t["assigned_to"] == "writer" and t.get("status") == "pending"]
    if not my_tasks:
        return {**state, "logs": logs}
    
    logs.append(f"[{task_id}] [Writer] 接收到 {len(my_tasks)} 个任务")
    
    # 捕获 state 的快照（避免在 lambda 闭包中直接引用 state）
    state_snapshot = {
        "researcher_results": list(state.get("researcher_results", [])),
        "coder_results": list(state.get("coder_results", [])),
        "writer_results": list(state.get("writer_results", [])),
    }
    
    results = []
    for task in my_tasks:
        task_desc = task["description"]
        for s in subtasks:
            if s["id"] == task["id"]:
                s["status"] = "running"
        
        result = _run_single_task(
            task_desc=task_desc,
            executor_fn=lambda desc: _writer_execute(desc, state_snapshot),
            task_id=task["id"],
            task_role=task["assigned_to"],
            logs=logs,
        )
        results.append(result)
        
        for s in subtasks:
            if s["id"] == task["id"]:
                s["status"] = "completed" if result["status"] == "success" else "failed"
                s["result"] = result["result"]
                s["error"] = result["error"]
                s["confidence"] = result["confidence"]
    
    return {
        **state,
        "subtasks": subtasks,
        "writer_results": state.get("writer_results", []) + results,
        "logs": logs,
    }


def reviewer_agent(state: AgentState) -> AgentState:
    """评审 Agent：质量审核"""
    task_id = state["task_id"]
    subtasks = state.get("subtasks", [])
    logs = list(state.get("logs", []))
    
    my_tasks = [t for t in subtasks if t["assigned_to"] == "reviewer" and t.get("status") == "pending"]
    if not my_tasks:
        return {**state, "logs": logs}
    
    logs.append(f"[{task_id}] [Reviewer] 接收到 {len(my_tasks)} 个任务")
    
    # 捕获 state 快照（避免闭包陷阱）
    state_snapshot = {
        "researcher_results": list(state.get("researcher_results", [])),
        "coder_results": list(state.get("coder_results", [])),
        "writer_results": list(state.get("writer_results", [])),
    }
    
    results = []
    for task in my_tasks:
        task_desc = task["description"]
        for s in subtasks:
            if s["id"] == task["id"]:
                s["status"] = "running"
        
        result = _run_single_task(
            task_desc=task_desc,
            executor_fn=lambda desc: _reviewer_execute(desc, state_snapshot),
            task_id=task["id"],
            task_role=task["assigned_to"],
            logs=logs,
        )
        results.append(result)
        
        for s in subtasks:
            if s["id"] == task["id"]:
                s["status"] = "completed" if result["status"] == "success" else "failed"
                s["result"] = result["result"]
                s["error"] = result["error"]
                s["confidence"] = result["confidence"]
    
    return {
        **state,
        "subtasks": subtasks,
        "reviewer_results": state.get("reviewer_results", []) + results,
        "logs": logs,
    }


# ─── 各 Agent 的执行函数 ───

def _researcher_execute(description: str) -> str:
    """研究员执行器：优先用真实搜索工具，fallback 到 LLM"""
    # 尝试从任务描述中提取搜索关键词
    import re
    # 去掉 "搜集"/"搜索" 等前缀，提取核心关键词
    query = re.sub(r"^(搜集|搜索|查找|查询)[\s:：]*", "", description).strip()
    if len(query) < 4:
        query = description

    try:
        from beehive.tools.search import search_and_summarize
        result = search_and_summarize(query, max_results=5)
        return result
    except Exception as e:
        # 搜索失败时降级到 LLM 自身知识
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

    result = llm_call(prompt, system=CODER_SYSTEM, provider=PROVIDER_EXEC, temperature=0.2)
    return result


def _writer_execute(description: str, state: AgentState) -> str:
    """文案执行器：撰写内容，参考已有上下文"""
    # 汇总之前的执行结果作为上下文
    context_parts = []
    for r in state.get("researcher_results", []):
        if r.get("result"):
            context_parts.append(f"【研究员结果】\n{r['result']}")
    for r in state.get("coder_results", []):
        if r.get("result"):
            context_parts.append(f"【程序员结果】\n{r['result']}")
    
    context = "\n\n".join(context_parts) if context_parts else "（暂无前置结果，直接执行）"
    
    prompt = f"""请作为专业文案，执行以下撰写任务：

任务：{description}

前置Agent的成果（可作为参考）：
---
{context}
---

请撰写对应内容。"""

    result = llm_call(prompt, system=WRITER_SYSTEM, provider=PROVIDER_EXEC, temperature=0.4)
    return result


def _reviewer_execute(description: str, state: AgentState) -> str:
    """评审执行器：评估之前的工作质量"""
    # 汇总所有结果
    all_results = []
    for role, results_key in [("研究员", "researcher_results"), ("程序员", "coder_results"), ("文案", "writer_results")]:
        for r in state.get(results_key, []):
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

    result = llm_call(prompt, system=REVIEWER_SYSTEM, provider=PROVIDER_EXEC, temperature=0.1)
    return result