"""LLM 统一调用接口"""
import json
import re
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from beehive.config import LLM_CONFIG


# 特殊 provider：规划专用（用硅基流动 Qwen）
PROVIDER_PLAN = "siliconflow-plan"
# 特殊 provider：执行专用（用硅基流动 DeepSeek V3.1）
PROVIDER_EXEC = "siliconflow-exec"


def get_llm(provider: str = "openai", temperature: float = 0.0) -> ChatOpenAI:
    """获取 LLM 实例，空 key 时自动回退"""
    def _key(cfg_key: str) -> str:
        v = LLM_CONFIG.get(cfg_key, "")
        return v if v else ""

    # 所有可用的 provider（按优先级）
    all_providers = ["siliconflow", "deepseek", "openai", "doubao"]
    providers_with_keys = [p for p in all_providers if _key(f"{p}_api_key")]

    if not providers_with_keys:
        raise ValueError(
            "没有配置任何 LLM API Key！"
            "请在 config.py 中配置 API Key"
        )

    # 如果指定 provider 无 key，往后排
    if provider not in providers_with_keys and provider not in (PROVIDER_PLAN, PROVIDER_EXEC):
        provider = providers_with_keys[0]

    if provider == PROVIDER_PLAN:
        # 规划用 Qwen（硅基流动，便宜快）
        return ChatOpenAI(
            model=LLM_CONFIG["siliconflow_model"],
            api_key=LLM_CONFIG["siliconflow_api_key"],
            base_url=LLM_CONFIG["siliconflow_base_url"],
            temperature=temperature,
        )
    elif provider == PROVIDER_EXEC:
        # 执行用 DeepSeek V3.1 Terminus（硅基流动，性价比高）
        return ChatOpenAI(
            model=LLM_CONFIG["siliconflow_model_executor"],
            api_key=LLM_CONFIG["siliconflow_api_key"],
            base_url=LLM_CONFIG["siliconflow_base_url"],
            temperature=temperature,
        )
    elif provider == "siliconflow":
        return ChatOpenAI(
            model=LLM_CONFIG["siliconflow_model"],
            api_key=LLM_CONFIG["siliconflow_api_key"],
            base_url=LLM_CONFIG["siliconflow_base_url"],
            temperature=temperature,
        )
    elif provider == "deepseek":
        return ChatOpenAI(
            model=LLM_CONFIG["deepseek_model"],
            api_key=_key("deepseek_api_key"),
            base_url=LLM_CONFIG["deepseek_base_url"],
            temperature=temperature,
        )
    elif provider == "doubao":
        return ChatOpenAI(
            model=LLM_CONFIG["doubao_model"],
            api_key=_key("doubao_api_key"),
            base_url=LLM_CONFIG["doubao_base_url"],
            temperature=temperature,
        )
    else:
        return ChatOpenAI(
            model=LLM_CONFIG["openai_model"],
            api_key=_key("openai_api_key"),
            base_url=LLM_CONFIG["openai_base_url"],
            temperature=temperature,
        )


def llm_call(
    prompt: str,
    system: str = "",
    provider: str = PROVIDER_PLAN,
    temperature: float = 0.0,
) -> str:
    """统一 LLM 调用入口"""
    llm = get_llm(provider, temperature)
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))

    try:
        response = llm.invoke(messages)
        return response.content
    except Exception as e:
        err_type = type(e).__name__
        err_msg = str(e)
        if err_type in ("AuthenticationError", "BadRequestError", "RateLimitError", "APIError"):
            raise
        raise ValueError(f"[{err_type}] LLM 调用失败：{err_msg}") from e


def llm_json(prompt: str, system: str = "", provider: str = PROVIDER_PLAN) -> dict:
    """返回 JSON 结构的 LLM 调用"""
    text = llm_call(prompt, system, provider)
    # 优先从 ```json 代码块提取（可能有多层嵌套）
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        raw = match.group(1).strip()
        # 递归去掉外层 code block（如果还有的话）
        while True:
            inner = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if inner:
                raw = inner.group(1).strip()
            else:
                break
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    # 直接解析裸 JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # 兜底：从文本提取第一个 JSON 对象/数组
    for pattern in [r"(\{[\s\S]*\})", r"(\[[\s\S]*\])"]:
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    raise ValueError(f"无法解析 JSON 输出（前200字）: {text[:200]}")