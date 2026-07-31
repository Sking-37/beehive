"""搜索工具 - Tavily API 封装"""
import os

TVLY_API_KEY = os.getenv("TVLY_API_KEY", "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")


def search(query: str, max_results: int = 5) -> list[dict]:
    """使用 Tavily 搜索真实网络内容"""
    import urllib.request
    import json

    payload = {
        "api_key": TVLY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("results", [])
    except Exception as e:
        return [{"error": f"搜索失败：{str(e)}", "title": "", "url": "", "content": ""}]


def search_and_summarize(query: str, max_results: int = 5) -> str:
    """搜索并用 LLM 提炼摘要"""
    from beehive.llm import llm_call, PROVIDER_EXEC

    results = search(query, max_results)

    if not results or "error" in results[0]:
        return f"搜索失败：{results[0].get('error', '未知错误') if results else '无结果'}"

    # 把搜索结果拼成摘要
    content_lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "无标题")
        url = r.get("url", "")
        snippet = r.get("content", "")[:300]
        content_lines.append(f"{i}. {title}\n   来源：{url}\n   摘要：{snippet}")

    raw = "\n\n".join(content_lines)

    # 让 LLM 提炼关键信息
    summary_prompt = f"""以下是从网络搜索到的相关内容，请提炼出最重要的事实和观点（150字以内）：

{raw}

提炼要点："""

    summary = llm_call(summary_prompt, system="你是一个信息提炼专家，从搜索结果中提取关键信息。", provider=PROVIDER_EXEC)
    return f"【搜索结果】{query}\n\n{summary}\n\n【原始来源】\n" + "\n".join([f"- {r.get('title','无标题')}：{r.get('url','')}" for r in results])