"""
领头模型（Orchestrator）
职责：理解任务 → 拆解为子任务 → 规划执行顺序 → 评估结果决定下一步
这是蜂群的大脑，不做具体执行，只做规划和判断
"""
import json
import uuid
from beehive.state import AgentState, SubTask
from beehive.llm import llm_json, llm_call, PROVIDER_PLAN
from beehive.config import MAX_LOOP


ORCHESTRATOR_SYSTEM = """你是一个任务规划专家（Orchestrator）。

你的职责是将复杂任务拆解为可执行的子任务，并规划执行顺序。
你**不**执行具体工作，只做规划和评估。

输出必须严格是 JSON 格式，不要有其他文字。用 ```json 代码块包裹。"""


def _build_planning_prompt(user_task: str, retry_feedback: str = "", is_replan: bool = False) -> str:
    """构建任务拆解的 prompt"""
    phase_note = "【重规划】请根据反馈调整计划，保留已完成且合格的任务，更新需改进的任务。" if is_replan else "【首次规划】请全面拆解任务，覆盖所有必要步骤。"
    retry_note = f"\n\n评审反馈（请据此调整计划）：\n{retry_feedback}" if retry_feedback else ""
    
    return f"""{phase_note}

用户任务：{user_task}{retry_note}

请将上述任务拆解为子任务列表，输出 JSON 数组格式：

```json
[
  {{
    "id": "task_1",
    "description": "任务描述，尽量具体清晰",
    "assigned_to": "researcher",
    "depends_on": [],
    "output_format": "期望的输出格式（如：JSON数组/文本段落/代码片段）"
  }}
]
```

角色说明：
- **researcher**：信息搜集、网页搜索、数据查找、竞品调研
- **coder**：代码实现、bug修复、技术方案
- **writer**：文案撰写、内容整理、报告生成
- **reviewer**：质量审核、结果评审、问题识别
- **orchestrator**（很少用）：需要领头模型直接处理的全局性任务

拆分原则：
1. 每个子任务尽量**单一职责**，不要一个任务做多件事
2. 有依赖关系的任务，depends_on 要写清楚
3. 没有依赖的任务尽量**并行**安排（depends_on 为空数组）
4. 总任务数控制在 5-9 个，太多拆太细，太少不够详细
5. 第一个任务通常是 researcher（搜集信息）

只输出 JSON，不要有其他文字。用 ```json 代码块包裹。"""


def orchestrator_plan(state: AgentState) -> AgentState:
    """
    领头模型：拆解任务阶段
    输入：user_task（用户原始任务）
    输出：subtasks（子任务列表）+ current_plan（计划描述）
    """
    task_id = state["task_id"]
    user_task = state["user_task"]
    logs = list(state.get("logs", []))

    # ─── loop_count：只增不减，防止异常时重复累加 ───
    prev_loop = state.get("loop_count", 0)
    evaluation = state.get("evaluation", "")
    next_action = state.get("next_action", "")

    if evaluation == "retry" or next_action == "retry":
        current_loop = prev_loop + 1  # retry 也算一次循环，继续累加
        retry_feedback = state.get("evaluation_reason", "")
        is_replan = True
        logs.append(f"[{task_id}] [Orchestrator] 重试（循环{current_loop}/{MAX_LOOP}），接入反馈：{retry_feedback[:60]}...")
    else:
        current_loop = prev_loop + 1
        retry_feedback = ""
        is_replan = False

    logs.append(f"[{task_id}] [Orchestrator] 拆解任务（第{current_loop}次）：{user_task[:50]}...")

    try:
        result = llm_json(
            prompt=_build_planning_prompt(user_task, retry_feedback=retry_feedback, is_replan=is_replan),
            system=ORCHESTRATOR_SYSTEM,
            provider=PROVIDER_PLAN,
        )

        raw_tasks = result if isinstance(result, list) else result.get("subtasks", [])

        # 保留已完成任务的状态，只新增未规划的任务
        existing_by_id = {s["id"]: s for s in state.get("subtasks", [])}
        subtasks = []
        for t in raw_tasks:
            tid = t.get("id", f"task_{uuid.uuid4().hex[:6]}")
            if tid in existing_by_id:
                subtasks.append(existing_by_id[tid])  # 保留原有状态
            else:
                subtasks.append({
                    "id": tid,
                    "description": t.get("description", ""),
                    "assigned_to": t.get("assigned_to", "researcher"),
                    "depends_on": t.get("depends_on", []),
                    "output_format": t.get("output_format", "文本"),
                    "status": "pending",
                    "result": None,
                    "error": None,
                    "confidence": None,
                    "attempts": 0,
                })

        plan_text = f"共 {len(subtasks)} 个子任务，"
        by_role = {}
        for s in subtasks:
            by_role[s["assigned_to"]] = by_role.get(s["assigned_to"], 0) + 1
        plan_text += " + ".join([f"{v}个{r}" for r, v in by_role.items()])

        logs.append(f"[{task_id}] [Orchestrator] 拆解完成：{plan_text}")

        return {
            **state,
            "subtasks": subtasks,
            "current_plan": plan_text,
            "loop_count": current_loop,
            "logs": logs,
        }

    except Exception as e:
        logs.append(f"[{task_id}] [Orchestrator] 拆解失败：{str(e)}")
        return {
            **state,
            "subtasks": state.get("subtasks", []),
            "current_plan": "",
            "loop_count": current_loop,        # 不重复累加
            "evaluation": "done",
            "next_action": "done",
            "logs": logs,
        }


def orchestrator_evaluate(state: AgentState) -> AgentState:
    """
    领头模型：评估阶段
    读取所有 Agent 的执行结果，判断下一步动作
    输入：所有 Agent 的 results
    输出：evaluation + next_action
    """
    task_id = state["task_id"]
    subtasks = state.get("subtasks", [])
    loop_count = state.get("loop_count", 0)
    logs = list(state.get("logs", []))

    logs.append(f"[{task_id}] [Orchestrator] 评估结果（循环 {loop_count}/{MAX_LOOP}）")

    # ─── 核心判断：有没有未执行的 pending 任务？ ───
    pending = [s for s in subtasks if s.get("status") == "pending"]
    executed = [s for s in subtasks if s.get("status") in ("completed", "failed")]
    completed = [s for s in subtasks if s.get("status") == "completed"]
    failed = [s for s in subtasks if s.get("status") == "failed"]

    all_results = {
        "researcher": state.get("researcher_results", []),
        "coder": state.get("coder_results", []),
        "writer": state.get("writer_results", []),
        "reviewer": state.get("reviewer_results", []),
    }

    # 超过上限 → 强制 done
    if loop_count >= MAX_LOOP:
        logs.append(f"[{task_id}] [Orchestrator] 达到循环上限，强制结束")
        return {**state, "evaluation": "done", "next_action": "done", "logs": logs}

    # ─── 新增：所有子任务都执行过了 → 直接 done，不再重复调度 ───
    if not pending and subtasks:
        logs.append(f"[{task_id}] [Orchestrator] 所有 {len(subtasks)} 个子任务已执行完毕，结束")
        return {**state, "evaluation": "done", "next_action": "done", "logs": logs}

    # 无子任务（规划失败）→ 强制 done
    if not subtasks:
        logs.append(f"[{task_id}] [Orchestrator] 无子任务，结束")
        return {**state, "evaluation": "done", "next_action": "done", "logs": logs}

    # 还有 pending → 让 LLM 决定是否 retry
    eval_prompt = f"""当前任务执行状态：

任务：{state['user_task']}

子任务（共 {len(subtasks)} 个，完成 {len(completed)} 个，失败 {len(failed)} 个，待执行 {len(pending)} 个）：
{json.dumps(subtasks, ensure_ascii=False, indent=2)}

各 Agent 结果：
{json.dumps(all_results, ensure_ascii=False, indent=2)}

请判断下一步动作（只能选一个）：
- "continue"：有任务还未执行，需要继续执行
- "retry"：已有执行结果质量不达标，需要针对具体失败任务重试
- "done"：所有必要任务已完成，质量合格

输出格式（纯JSON）：
{{"action": "continue/retry/done", "reason": "理由", "adjustment": "调整建议（仅 retry 时需要）"}}

只输出 JSON，用 ```json 代码块包裹。"""

    try:
        result = llm_json(eval_prompt, system="你是任务评审专家，客观判断执行结果，给出明确的下一步动作。", provider=PROVIDER_PLAN)

        action = result.get("action", "done")
        reason = result.get("reason", "")
        adjustment = result.get("adjustment", "")

        eval_reason = adjustment if action == "retry" else reason
        logs.append(f"[{task_id}] [Orchestrator] 评估：{action} — {reason}")

        return {
            **state,
            "evaluation": action,
            "evaluation_reason": eval_reason,
            "next_action": action,
            "logs": logs,
        }

    except Exception as e:
        logs.append(f"[{task_id}] [Orchestrator] 评估异常：{str(e)}，强制结束")
        return {**state, "evaluation": "done", "next_action": "done", "logs": logs}