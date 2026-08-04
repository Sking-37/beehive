"""项目配置"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# 日志目录
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# LLM 配置（这里放你常用的 API，支持 OpenAI / DeepSeek / 字节等）
LLM_CONFIG = {
    # OpenAI
    "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
    "openai_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o"),

    # DeepSeek（备用，官方）
    "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "deepseek_base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    "deepseek_model": os.getenv("DEEPSEEK_MODEL", "deepseek-v3"),

    # 字节豆包（备用）
    "doubao_api_key": os.getenv("DOUBAO_API_KEY", ""),
    "doubao_base_url": os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
    "doubao_model": os.getenv("DOUBAO_MODEL", "doubao-seed-2-1-turbo-260628"),

    # 硅基流动（性价比高）
    "siliconflow_api_key": "sk-yclnttnsegwkuklvhhvbnvplhiozgsdgdidgwuxaersjgvmf",
    "siliconflow_base_url": "https://api.siliconflow.cn/v1",
    "siliconflow_model": "THUDM/GLM-4-9B-0414",         # 规划/评估专用（中文JSON稳定）
    "siliconflow_model_executor": "deepseek-ai/DeepSeek-V3.1-Terminus",  # 内容生成

    # 默认使用哪个 provider
    "default": "siliconflow",
}

# Agent 超时配置（秒）
AGENT_TIMEOUT = 120

# 循环上限（防止无限重试）
MAX_LOOP = 5

# 任务重试次数
MAX_RETRIES = 2