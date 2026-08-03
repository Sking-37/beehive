"""
蜂群核心链路测试脚本（绕过 API/CLI，直接跑 LangGraph）
用法：DEEPSEEK_API_KEY=sk-xxx python3 test_run.py
"""
import os
import sys

# 设置环境变量（方便测试）
os.environ.setdefault("DEEPSEEK_API_KEY", "YOUR_DEEPSEEK_API_KEY_HERE")
os.environ.setdefault("DEEPSEEK_MODEL", "deepseek-v4-flash")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # workspace/

from beehive.state import ExecutionContext
from beehive.graph.flow import get_task_graph

def main():
    test_task = "用三句话介绍一下你自己。"

    print("=" * 60)
    print(f"🎯 测试任务：{test_task}")
    print("=" * 60)

    # 初始化执行上下文
    task_id = "test_run_001"
    ctx = ExecutionContext(task_id, test_task)
    state = ctx.to_state()
    print(f"✅ 上下文初始化完成：{task_id}")

    # 获取任务图
    graph = get_task_graph()
    print("✅ LangGraph 图加载完成")

    # 执行
    print("\n🚀 开始执行...")
    print("-" * 60)

    step_count = 0
    final_state = None

    try:
        for step in graph.stream(state):
            step_count += 1
            step_name = list(step.keys())[0]
            step_state = step[step_name]

            subtasks = step_state.get("subtasks", [])
            completed = sum(1 for s in subtasks if s.get("status") == "completed")
            total = len(subtasks)

            logs = step_state.get("logs", [])
            recent_log = logs[-1] if logs else ""

            print(f"\n[步骤{step_count}] {step_name}")
            print(f"  进度：{completed}/{total}")
            if recent_log:
                print(f"  日志：{recent_log[:100]}")

            # 打印关键输出
            if step_state.get("researcher_results"):
                for r in step_state["researcher_results"]:
                    print(f"\n  📄 研究员输出：{str(r)[:200]}")
            if step_state.get("writer_results"):
                for r in step_state["writer_results"]:
                    print(f"\n  📄 文案输出：{str(r)[:200]}")

            final_state = step_state

            # 结束条件
            next_action = step_state.get("next_action", "")
            if next_action == "done":
                print("\n✅ 任务流结束（领头模型判定 done）")
                break

    except Exception as e:
        print(f"\n❌ 执行异常：{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    # 输出最终结果
    if final_state:
        print("\n" + "=" * 60)
        print("📊 最终状态摘要")
        print("=" * 60)

        subtasks = final_state.get("subtasks", [])
        print(f"\n子任务（{len(subtasks)}个）：")
        for s in subtasks:
            icon = {"completed": "✅", "failed": "❌", "running": "⚡", "pending": "⏳"}.get(s.get("status"), "○")
            print(f"  {icon} [{s.get('assigned_to')}] {s.get('description', '')[:60]}")

        all_logs = final_state.get("logs", [])
        print(f"\n日志（共 {len(all_logs)} 条）：")
        for log in all_logs:
            print(f"  {log[:120]}")

        results_by_role = {
            "researcher": final_state.get("researcher_results", []),
            "coder": final_state.get("coder_results", []),
            "writer": final_state.get("writer_results", []),
            "reviewer": final_state.get("reviewer_results", []),
        }

        for role, results in results_by_role.items():
            if results:
                print(f"\n── {role.upper()} 结果 ──")
                for r in results:
                    status = r.get("status", "")
                    result_text = str(r.get("result", ""))[:300]
                    print(f"  [{status}] {result_text}")

        print(f"\n循环次数：{final_state.get('loop_count', 0)}/{final_state.get('max_loop', '?')}")
        print(f"最终动作：{final_state.get('next_action', '?')}")


if __name__ == "__main__":
    main()