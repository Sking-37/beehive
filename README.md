# 🐝 Beehive（蜂群）

> 多 Agent 协作平台 — 一个大模型领头，多个专项 Agent 并行执行

[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green.svg)](https://langchain-ai.github.io/langgraph/)

## 🎯 是什么

蜂群是一个多 Agent 协作框架。你描述一个任务，领头模型自动拆解、分派，多个专项 Agent 并行执行，结果统一评估交付。

就像一个项目团队：项目经理（Orchestrator）接需求 → 分配给研究员、程序员、作家 → 各司其职 → 项目经理验收结果。

## ⚡ 快速开始

### 安装

```bash
pip install beehive
```

或从源码安装：

```bash
git clone https://github.com/Sking-37/beehive.git
cd beehive
pip install -e .
```

### 配置 API Key

```bash
export DEEPSEEK_API_KEY=sk-your-key-here
# 或者创建 config.yaml
cp config.example.yaml config.yaml
# 编辑 config.yaml 填入你的 key
```

### 命令行使用

```bash
# 运行任务
beehive run "帮我写一个博客系统，包含用户认证和文章发布"

# 查看任务状态
beehive status <task_id>

# 查看所有任务
beehive list

# 查看日志
beehive logs <task_id>
```

### Web 界面

```bash
# 启动 API + Web 服务
beehive serve

# 浏览器打开 http://localhost:5173
```

## 🏗️ 架构

```
用户输入任务
    │
    ▼
┌─────────────────┐
│  Orchestrator   │ ← 领头模型：理解需求 → 拆解子任务 → 规划执行顺序
│  (领头大模型)    │   评估结果 → 决定重试/继续/终止
└────────┬────────┘
         │ 分派任务
    ┌────┴────┬──────────┬──────────┐
    ▼         ▼          ▼          ▼
┌──────┐ ┌──────┐  ┌─────────┐ ┌──────────┐
│ 🔍   │ │ 💻   │  │ ✍️      │ │ 👀       │
│Research│ │Coder │  │ Writer  │ │ Reviewer│
│ 研究  │ │ 代码  │  │ 文案    │ │ 审查     │
└───┬──┘ └───┬──┘  └────┬────┘ └────┬────┘
    │        │          │           │
    └────────┴──────────┴───────────┘
                │ 汇总结果
                ▼
         ┌──────────────┐
         │ Orchestrator │
         │   评估输出    │
         └──────────────┘
                │
                ▼
           最终结果
```

## 📁 项目结构

```
beehive/
├── agents/          # Agent 角色定义
│   ├── orchestrator.py  # 领头模型
│   └── executors.py     # 执行 Agent 池
├── api/             # FastAPI 接口
│   └── main.py
├── cli.py           # 命令行入口
├── config.py        # 配置管理
├── graph/           # LangGraph 状态图
│   └── flow.py
├── llm.py           # LLM 统一调用
├── state.py         # AgentState 状态定义
├── storage.py       # SQLite 持久化
├── ui/              # Web 前端
│   ├── index.html
│   └── server.py
└── tools/           # Agent 可调用的工具
    └── search.py
```

## 🔧 配置

### 支持的模型后端

| 后端 | 模型 | 配置 Key |
|------|------|---------|
| DeepSeek | `deepseek-v4-flash` | `DEEPSEEK_API_KEY` |
| OpenAI | `gpt-4o-mini` 等 | `OPENAI_API_KEY` |
| 豆包 | `doubao-*` | `ARK_API_KEY` |

### config.yaml 示例

```yaml
llm:
  provider: "deepseek"       # deepseek / openai / doubao
  model: "deepseek-v4-flash"
  api_key: "${DEEPSEEK_API_KEY}"

orchestrator:
  model: "deepseek-v4-flash"  # 领头模型（可用更强的）
  max_loop: 5
  temperature: 0.3

execution:
  max_parallel: 4           # 最大并发数
  timeout_per_task: 120     # 单任务超时（秒）

search:
  provider: "tavily"        # tavily / duckduckgo
  api_key: "${TAVILY_API_KEY}"
```

## 📦 作为 Python 库使用

```python
from beehive import Beehive

# 初始化
hive = Beehive(
    llm_config={"provider": "deepseek", "api_key": "sk-xxx"},
    max_loop=5,
)

# 运行任务
result = hive.run("帮我分析量子计算行业报告")

print(result["final_result"])
print(result["subtasks"])
```

## 🧪 测试

```bash
# 单次测试
DEEPSEEK_API_KEY=sk-xxx python test_run.py

# 运行 pytest
pytest tests/
```

## 🐳 Docker 部署

```bash
docker build -t beehive .
docker run -p 8000:8000 -p 5173:5173 \
  -e DEEPSEEK_API_KEY=sk-xxx \
  beehive
```

## 📝 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件。

## 🤝 贡献

欢迎提交 Issue 和 PR！

---

Built with 🪷 by 藕生 + LangGraph