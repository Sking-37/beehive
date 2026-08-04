"""
蜂群 API 层 - FastAPI 服务
提供任务创建、状态查询、日志查看等接口
"""
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json

from beehive.state import ExecutionContext, AgentState
from beehive.graph.flow import get_task_graph
from beehive.agents.orchestrator import orchestrator_plan, orchestrator_evaluate

# LangGraph 同步调用必须跑在线程池，否则阻塞 event loop
_executor = ThreadPoolExecutor(max_workers=4)

app = FastAPI(title="蜂群 - Multi-Agent 协作平台", version="0.1.0")

# CORS 允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 内存任务存储（生产环境建议换 PostgreSQL + Redis）───
_tasks: dict[str, dict] = {}
_lock = asyncio.Lock()


# ─── 请求/响应模型 ───

class TaskCreate(BaseModel):
    task: str
    context: Optional[dict] = {}
    stream: bool = False


class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatus(BaseModel):
    task_id: str
    status: str
    loop_count: int
    current_plan: str
    progress: str  # 如 "3/5"
    subtasks: list
    final_result: Optional[dict]
    logs: list[str]
    created_at: str


# ─── 核心执行函数 ───

async def run_task_streaming(task_id: str, user_task: str, context: dict):
    """流式执行任务，实时推送状态更新（LangGraph 跑在线程池，不阻塞 event loop）"""
    import queue as syncqueue

    ctx = ExecutionContext(task_id, user_task)
    state = ctx.to_state()
    graph = get_task_graph()

    q: syncqueue.Queue = syncqueue.Queue()

    async with _lock:
        _tasks[task_id] = {"status": "running", "state": state}

    def _sync_producer():
        """同步函数，运行在 ThreadPoolExecutor 线程里"""
        try:
            for step in graph.stream(state):
                step_name = list(step.keys())[0]
                step_state = step[step_name]
                q.put((step_name, step_state))
                if step_state.get("next_action") == "done":
                    break
        except Exception as e:
            q.put(("error", str(e)))
        finally:
            q.put((None, None))

    # 把同步 producer 扔进线程池
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _sync_producer)

    final_info = None
    try:
        while True:
            # 用 await wait_for 做超时保护
            step_name, step_state = await asyncio.wait_for(
                loop.run_in_executor(_executor, q.get), timeout=300
            )
            if step_name is None:
                break
            if step_name == "error":
                raise RuntimeError(step_state)

            progress = (
                f"{sum(1 for s in step_state.get('subtasks', []) if s.get('status') in ('completed', 'failed'))}"
                f"/{len(step_state.get('subtasks', []))}"
            )
            event = {
                "event": "step",
                "node": step_name,
                "progress": progress,
                "logs": step_state.get("logs", [])[-5:],
                "subtasks": step_state.get("subtasks", []),
            }
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            final_info = step_state

        if final_info:
            final_result = _build_final_result(final_info)
            async with _lock:
                _tasks[task_id] = {"status": "done", "state": final_info, "result": final_result}
            yield f"data: {json.dumps({'event': 'done', 'result': final_result}, ensure_ascii=False)}\n\n"

    except Exception as e:
        async with _lock:
            _tasks[task_id] = {"status": "failed", "error": str(e)}
        yield f"data: {json.dumps({'event': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"


def _build_final_result(state: AgentState) -> dict:
    """汇总最终结果"""
    return {
        "task_id": state["task_id"],
        "user_task": state["user_task"],
        "plan": state.get("current_plan", ""),
        "subtasks_count": len(state.get("subtasks", [])),
        "completed_count": sum(1 for s in state.get("subtasks", []) if s.get("status") == "completed"),
        "results": {
            "researcher": state.get("researcher_results", []),
            "coder": state.get("coder_results", []),
            "writer": state.get("writer_results", []),
            "reviewer": state.get("reviewer_results", []),
        },
        "logs": state.get("logs", []),
    }


# ─── API 路由 ───

@app.get("/")
def root():
    return {"name": "蜂群", "version": "0.1.0", "status": "running"}


@app.post("/tasks", response_model=TaskResponse)
async def create_task(body: TaskCreate):
    """创建新任务（异步执行）"""
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    ctx = ExecutionContext(task_id, body.task)
    
    async with _lock:
        _tasks[task_id] = {
            "status": "pending",
            "task": body.task,
            "context": body.context,
            "created_at": ctx.created_at,
        }
    
    # 后台异步执行（不等待完成）
    asyncio.create_task(_run_task_background(task_id, body.task, body.context))
    
    return TaskResponse(
        task_id=task_id,
        status="pending",
        message="任务已创建，正在排队执行",
    )


async def _run_task_background(task_id: str, user_task: str, context: dict):
    """后台异步执行任务（LangGraph 跑在线程池，不阻塞 event loop）"""
    ctx = ExecutionContext(task_id, user_task)
    state = ctx.to_state()
    graph = get_task_graph()

    async with _lock:
        _tasks[task_id]["status"] = "running"

    def _run():
        final_state = None
        for step in graph.stream(state):
            step_name = list(step.keys())[0]
            step_state = step[step_name]
            final_state = step_state
            if step_state.get("next_action") == "done":
                break
        return final_state

    try:
        final_state = await asyncio.wrap_future(_executor.submit(_run))
        if final_state:
            async with _lock:
                _tasks[task_id]["status"] = "done"
                _tasks[task_id]["result"] = _build_final_result(final_state)
    except Exception as e:
        async with _lock:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(e)


@app.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """查询任务状态"""
    async with _lock:
        task = _tasks.get(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    state: Optional[AgentState] = task.get("state", {})
    subtasks = state.get("subtasks", []) if state else []
    finished = sum(1 for s in subtasks if s.get("status") in ("completed", "failed"))
    
    return TaskStatus(
        task_id=task_id,
        status=task.get("status", "unknown"),
        loop_count=state.get("loop_count", 0) if state else 0,
        current_plan=state.get("current_plan", "") if state else "",
        progress=f"{finished}/{len(subtasks)}",
        subtasks=subtasks,
        final_result=task.get("result"),
        logs=state.get("logs", [])[-20:] if state else [],
        created_at=task.get("created_at", ""),
    )


@app.get("/tasks/{task_id}/logs")
async def get_task_logs(task_id: str, lines: int = 50):
    """查看任务日志"""
    async with _lock:
        task = _tasks.get(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    state = task.get("state", {})
    all_logs = state.get("logs", []) if state else []
    return {"task_id": task_id, "logs": all_logs[-lines:], "total": len(all_logs)}


@app.delete("/tasks/{task_id}")
async def cancel_task(task_id: str):
    """取消任务（目前仅标记，不实际中断执行）"""
    async with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task["status"] in ("done", "failed", "cancelled"):
            raise HTTPException(status_code=409, detail=f"任务已是 {task['status']} 状态，无法取消")
        task["status"] = "cancelled"
    return {"task_id": task_id, "message": "任务已取消"}


@app.post("/tasks/stream")
async def create_task_stream(body: TaskCreate):
    """创建任务并流式返回执行过程"""
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    
    async with _lock:
        _tasks[task_id] = {
            "status": "running",
            "task": body.task,
            "created_at": datetime.now().isoformat(),
        }
    
    return StreamingResponse(
        run_task_streaming(task_id, body.task, body.context or {}),
        media_type="text/event-stream",
    )


@app.get("/tasks")
async def list_tasks(status: Optional[str] = None, limit: int = 20):
    """列出所有任务"""
    async with _lock:
        items = list(_tasks.items())  # 保留 (tid, task) 元组
    
    # 先过滤再取切片，保持一致性
    if status:
        filtered = [(tid, t) for tid, t in items if t.get("status") == status]
    else:
        filtered = items
    
    # 最近 limit 条
    recent = filtered[-limit:]
    
    return {
        "total": len(filtered),
        "tasks": [
            {
                "task_id": tid,
                "status": t.get("status"),
                "task": t.get("task", "")[:60],
                "created_at": t.get("created_at", ""),
            }
            for tid, t in recent
        ]
    }