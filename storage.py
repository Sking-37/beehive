"""
蜂群存储层 - 任务状态持久化
目前使用 SQLite，生产环境可换 PostgreSQL
"""
import sqlite3
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional
from beehive.config import DATA_DIR

DB_PATH = DATA_DIR / "beehive.db"
_db_lock = threading.Lock()  # 全局锁，保证 SQLite 并发写入安全


def _init_db():
    """初始化数据库"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            user_task TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            state_json TEXT,
            result_json TEXT,
            error TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            ts TEXT,
            level TEXT,
            message TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(task_id)
        )
    """)
    conn.commit()
    conn.close()


def save_task(task_id: str, user_task: str, status: str, state_json: str = "", result_json: str = "", error: str = ""):
    """保存或更新任务（线程安全）"""
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        now = datetime.now().isoformat()
        # 先查旧记录保留 created_at
        old_row = conn.execute("SELECT created_at FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        created_at = old_row[0] if old_row else now
        conn.execute("""
            INSERT OR REPLACE INTO tasks (task_id, user_task, status, created_at, updated_at, state_json, result_json, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (task_id, user_task, status, created_at, now, state_json, result_json, error))
        conn.commit()
        conn.close()


def append_log(task_id: str, level: str, message: str):
    """追加任务日志（线程安全）"""
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO task_logs (task_id, ts, level, message) VALUES (?, ?, ?, ?)",
            (task_id, datetime.now().isoformat(), level, message)
        )
        conn.commit()
        conn.close()


def get_task(task_id: str) -> Optional[dict]:
    """读取任务"""
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "task_id": row[0],
            "user_task": row[1],
            "status": row[2],
            "created_at": row[3],
            "updated_at": row[4],
            "state_json": row[5],
            "result_json": row[6],
            "error": row[7],
        }


def list_tasks(limit: int = 20, status: str = None) -> list[dict]:
    """列出任务"""
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        if status:
            rows = conn.execute(
                "SELECT task_id, user_task, status, created_at FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT task_id, user_task, status, created_at FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
        return [
            {"task_id": r[0], "user_task": r[1], "status": r[2], "created_at": r[3]}
            for r in rows
        ]


# 初始化数据库
_init_db()