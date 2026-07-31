"""
蜂群 CLI - 命令行入口
用法：
  python -m beehive.cli run "你的任务描述"
  python -m beehive.cli status <task_id>
  python -m beehive.cli list
  python -m beehive.cli logs <task_id>
"""
import sys
import json
import argparse

# 如果 API 服务已启动，直接调用 API
BASE_URL = "http://localhost:8000"


def _print_result(result: dict, verbose: bool = False):
    """打印最终结果（流式和非流式共用）"""
    print("\n" + "─" * 60)
    print("✅ 任务完成！")
    print(f"   任务：{result.get('user_task', '')}")
    print(f"   计划：{result.get('plan', '')}")
    print(f"   完成：{result.get('completed_count', 0)}/{result.get('subtasks_count', 0)} 个子任务")

    if verbose:
        for role, results in result.get("results", {}).items():
            if results:
                print(f"\n── {role.upper()} 结果 ──")
                for r in results:
                    print(f"  [{r.get('task_id')}] {r.get('result', '')[:300]}")


def cmd_run(task: str, verbose: bool = False, stream: bool = True):
    """提交并执行任务"""
    try:
        import requests

        if stream:
            # 流式：实时显示执行过程
            resp = requests.post(
                f"{BASE_URL}/tasks/stream", json={"task": task}, stream=True, timeout=300
            )
            resp.raise_for_status()
            print(f"🎯 任务已提交：{task[:60]}{'...' if len(task) > 60 else ''}")
            print("─" * 60)

            for line in resp.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8")
                if not text.startswith("data: "):
                    continue
                data = json.loads(text[6:])
                event = data.get("event", "")

                if event == "step":
                    node_names = {
                        "plan": "🧠 任务拆解",
                        "researcher": "🔍 研究员",
                        "coder": "💻 程序员",
                        "writer": "✍️ 文案",
                        "reviewer": "🔎 评审",
                        "evaluate": "📊 结果评估",
                    }
                    node_name = node_names.get(data.get("node", ""), data.get("node", ""))
                    print(f"\n[{node_name}] 进度：{data.get('progress', '')}")
                    for log in data.get("logs", []):
                        print(f"  {log}")

                elif event == "done":
                    result = data.get("result", {})
                    _print_result(result, verbose)
                    return

                elif event == "error":
                    print(f"\n❌ 执行出错：{data.get('error', '')}")
                    return

        else:
            # 非流式：轮询直到完成
            import time
            create_resp = requests.post(f"{BASE_URL}/tasks", json={"task": task}, timeout=30)
            create_resp.raise_for_status()
            task_id = create_resp.json()["task_id"]
            print(f"🎯 任务已提交：{task[:60]}...")
            print(f"   任务ID：{task_id}，等待完成...")

            while True:
                time.sleep(3)
                status_resp = requests.get(f"{BASE_URL}/tasks/{task_id}", timeout=10)
                status_data = status_resp.json()
                status = status_data.get("status", "")
                print(f"   状态：{status} — {status_data.get('progress', '')}")
                if status == "done":
                    _print_result(status_data.get("final_result") or {}, verbose)
                    return
                elif status in ("failed", "cancelled"):
                    print(f"\n❌ 任务失败/取消：{status_data.get('error', '')}")
                    return

    except ImportError:
        print("❌ requests 库未安装，请先安装：pip install requests")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 调用失败：{e}")
        print("   提示：确认 API 服务已启动（python -m beehive.api）")
        sys.exit(1)


def cmd_status(task_id: str):
    """查看任务状态"""
    try:
        import requests
        resp = requests.get(f"{BASE_URL}/tasks/{task_id}")
        resp.raise_for_status()
        data = resp.json()

        print(f"任务ID：{task_id}")
        print(f"状态：{data.get('status', '')}")
        print(f"进度：{data.get('progress', '')}")
        print(f"计划：{data.get('current_plan', '')}")
        print(f"循环：{data.get('loop_count', 0)}")
        print(f"创建：{data.get('created_at', '')}")

        subtasks = data.get("subtasks", [])
        if subtasks:
            print(f"\n子任务（{len(subtasks)}）：")
            for s in subtasks:
                status_icon = {
                    "pending": "⏳",
                    "running": "⚡",
                    "completed": "✅",
                    "failed": "❌",
                }.get(s.get("status", ""), "○")
                print(f"  {status_icon} [{s.get('assigned_to')}] {s.get('description', '')[:50]}")

        if data.get("final_result"):
            print("\n✅ 最终结果已就绪")

    except Exception as e:
        print(f"❌ 查询失败：{e}")
        sys.exit(1)


def cmd_list(limit: int = 10):
    """列出最近任务"""
    try:
        import requests
        resp = requests.get(f"{BASE_URL}/tasks", params={"limit": limit})
        resp.raise_for_status()
        data = resp.json()

        print(f"共 {data.get('total', 0)} 个任务（显示最近 {limit} 个）：")
        print("─" * 60)
        for t in data.get("tasks", []):
            status = t.get("status", "")
            icon = {"pending": "⏳", "running": "⚡", "done": "✅", "failed": "❌"}.get(status, "○")
            created = t.get("created_at", "")[:19]
            print(f"  {icon} {t.get('task_id')}  [{status}]  {t.get('task', '')[:40]}  {created}")

    except Exception as e:
        print(f"❌ 查询失败：{e}")
        sys.exit(1)


def cmd_logs(task_id: str, lines: int = 50):
    """查看任务日志"""
    try:
        import requests
        resp = requests.get(f"{BASE_URL}/tasks/{task_id}/logs", params={"lines": lines})
        resp.raise_for_status()
        data = resp.json()

        print(f"日志（{data.get('total', 0)} 条，显示最近 {lines}）：")
        print("─" * 60)
        for log in data.get("logs", []):
            print(f"  {log}")

    except Exception as e:
        print(f"❌ 查询失败：{e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="蜂群 - Multi-Agent 协作平台 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # run 子命令
    run_p = sub.add_parser("run", help="提交并执行任务")
    run_p.add_argument("task", help="任务描述")
    run_p.add_argument("-v", "--verbose", action="store_true", help="显示详细结果")
    run_p.add_argument("--no-stream", action="store_true", help="禁用流式输出（同步轮询）")

    # status 子命令
    sub.add_parser("status", help="查看任务状态").add_argument("task_id", help="任务ID")

    # list 子命令
    list_p = sub.add_parser("list", help="列出最近任务")
    list_p.add_argument("-n", "--limit", type=int, default=10, help="显示数量")

    # logs 子命令
    logs_p = sub.add_parser("logs", help="查看任务日志")
    logs_p.add_argument("task_id", help="任务ID")
    logs_p.add_argument("-n", "--lines", type=int, default=50, help="日志行数")

    args = parser.parse_args()

    if args.cmd == "run":
        cmd_run(args.task, verbose=args.verbose, stream=not args.no_stream)
    elif args.cmd == "status":
        cmd_status(args.task_id)
    elif args.cmd == "list":
        cmd_list(limit=args.limit)
    elif args.cmd == "logs":
        cmd_logs(args.task_id, lines=args.lines)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()