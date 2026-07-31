#!/usr/bin/env python3
"""
蜂群 Web UI — 开发服务器
功能：
  1. serve ui/index.html 及静态资源
  2. 代理 /api/* → http://localhost:8000（绕过 CORS + 简化路径）

启动：
  python3 server.py

然后打开 http://localhost:5173
"""
import os
import re
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

# ── 配置 ──────────────────────────────────────────────
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
API_BASE = os.environ.get("BEEHIVE_API", "http://localhost:8000")
PORT = int(os.environ.get("UI_PORT", "5173"))

# ── FastAPI 应用 ──────────────────────────────────────
app = FastAPI(title="蜂群 UI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 静态文件 ──────────────────────────────────────────
@app.get("/")
async def index():
    path = os.path.join(THIS_DIR, "index.html")
    return FileResponse(path, media_type="text/html")


@app.get("/{filename}")
async def static_file(filename: str):
    """
    直接 serve ui/ 目录下的文件（.css, .js, 图片等）
    """
    safe = re.sub(r"[^a-zA-Z0-9._-]", "", filename)
    path = os.path.join(THIS_DIR, safe)
    if os.path.isfile(path):
        return FileResponse(path)
    return Response("Not Found", status_code=404)


# ── API 代理（开发时简化路径 /api/tasks → /tasks）────
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_api(path: str, request: Request):
    """
    将 /api/* 转发到后端 http://localhost:8000/*
    这样前端 SSE 路径可以写成 /api/tasks/stream
    （server.py 和后端各自处理不同路径，避免冲突）
    """
    target_url = f"{API_BASE}/{path}"
    headers = dict(request.headers)
    # 去掉 host，避免跨站
    headers.pop("host", None)

    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                follow_redirects=True,
            )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers),
        )
    except httpx.ConnectError:
        return Response(
            content='{"detail":"蜂群后端未启动，请先运行: python3 -m beehive.api.main"}',
            status_code=503,
            media_type="application/json",
        )


# ── 启动 ──────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🐝 蜂群 UI 启动中...")
    print(f"   访问地址: http://localhost:{PORT}")
    print(f"   API 代理: /api/* → {API_BASE}")
    print(f"   按 Ctrl+C 停止")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")