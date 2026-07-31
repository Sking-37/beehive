# 🐝 蜂群（Beehive）

> 多 Agent 协作平台 — 一个大模型领头，多个专项 Agent 分工执行

## 架构

```
用户任务
   ↓
┌─────────────────────────┐
│  Orchestrator（领头模型） │
│  · 理解意图              │
│  · 拆解子任务            │
│  · 评估结果决定下一步     │
└─────────────────────────┘
   ↓ 分发
┌──────┐ ┌──────┐ ┌──────┐
│研究员│ │程序员│ │文案  │  ← 执行 Agent 池
└──────┘ └──────┘ └──────┘
```

## 快速开始

### 1. 安装依赖

```bash
cd /home/sandboxadm/openclaw/workspace/beehive
pip install -r requirements.txt

# 配置 API Key（支持 OpenAI / DeepSeek / 豆包）
export OPENAI_API_KEY="sk-xxxx"
# 或
export DEEPSEEK_API_KEY="sk-xxxx"
```

### 2. 启动 API 服务

```bash
cd /home/sandboxadm/openclaw/workspace
python -m beehive.api
# 输出：Uvicorn running on http://0.0.0.0:8000
```

### 3. 提交任务

```bash
# 方式一：命令行（推荐先用这个验证）
python -m beehive.cli run "分析这篇访谈记录，输出核心洞察"

# 方式二：API 直接调用
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"task": "帮我写一份竞品分析报告"}'

# 方式三：流式输出（实时看执行过程）
python -m beehive.cli run "帮我做市场调研" --verbose
```

### 4. 查看状态

```bash
python -m beehive.cli list                    # 列出最近任务
python -m beehive.cli status <task_id>        # 查看状态
python -m beehive.cli logs <task_id>          # 查看日志
```

### 5. 访问 Web 界面

```
http://localhost:8000  （API docs）
```

## 项目结构

```
beehive/
├── __init__.py          # 项目标识
├── config.py            # 全局配置（API Key、模型选择、超时等）
├── llm.py               # LLM 统一调用接口（支持 OpenAI/DeepSeek/豆包）
├── state.py             # 状态定义（AgentState / SubTask）
├── storage.py           # SQLite 持久化
├── cli.py               # 命令行入口
│
├── agents/             # Agent 定义
│   ├── orchestrator.py # 领头模型（拆解 + 评估）
│   └── executors.py     # 执行 Agent（研究员/程序员/文案/评审）
│
├── graph/              # LangGraph 任务编排
│   └── flow.py         # 任务图 + 条件边路由
│
└── api/                # FastAPI 服务层
    └── main.py         # REST API + SSE 流式接口
```

## Agent 角色说明

| Agent | 职责 | 适用场景 |
|-------|------|---------|
| **researcher** | 信息搜集、数据查找、竞品调研 | 任何需要外部信息的任务 |
| **coder** | 代码实现、bug修复、技术方案 | 编程相关任务 |
| **writer** | 文案撰写、报告生成、内容整理 | 写作相关任务 |
| **reviewer** | 质量评审、问题识别、改进建议 | 结果审核 |
| **orchestrator** | 领头模型全局决策 | 极少单独使用 |

## 设计原则

1. **领头模型专注规划，不做执行**：拆解和评估是领头模型的核心职责
2. **结构化输出**：领头模型返回 JSON 格式的任务拆解结果，有明确的 Schema
3. **循环控制**：评估结果触发 next/retry/done，配合 max_loop=5 防卡死
4. **错误隔离**：单个 Agent 失败不影响全局，错误信息反馈给领头模型重新规划

## 开发说明

```bash
# 目录
cd /home/sandboxadm/openclaw/workspace/beehive

# 测试单个模块
cd /home/sandboxadm/openclaw/workspace/beehive
python -c "from beehive.graph import get_task_graph; print('✅ 图构建正常')"

# 测试 API（需要先配 API Key）
python -m beehive.api &
curl http://localhost:8000/
```

## 版本说明

- **v0.1.0**：最小可行版本，包含核心 Orchestrator + 4个执行 Agent + CLI + API
- 后续版本计划：Web 界面、OpenClaw 集成、真实工具接入、并发队列、Docker 部署