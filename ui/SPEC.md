# 蜂群 Web UI — 设计规范

## 1. 概述

- **名称**：蜂群 UI
- **类型**：实时任务可视化面板
- **技术栈**：纯 HTML + CSS + JavaScript（无框架依赖）
- **通信方式**：SSE（Server-Sent Events）流式接口
- **目标用户**：蜂群平台使用者，实时观察多 Agent 协作执行过程

---

## 2. 文件结构

```
ui/
├── index.html    ← 唯一前端文件（HTML + CSS + JS 内嵌）
├── SPEC.md       ← 本规范文档
└── server.py     ← 前端开发服务器（可选，生产用 FastAPI）
```

---

## 3. 视觉规范

### 3.1 配色

| 变量 | 色值 | 用途 |
|------|------|------|
| `--bg` | `#0f1419` | 页面背景 |
| `--panel-bg` | `#1a1f26` | 面板背景 |
| `--panel-alt` | `#20272f` | 交替面板/卡片背景 |
| `--border` | `#2a2f3a` | 默认边框 |
| `--border-hi` | `#3a4050` | 高亮边框 |
| `--accent` | `#f5a623` | 蜂巢黄（主色）|
| `--accent-dim` | `rgba(245,166,35,.15)` | 主色淡化背景 |
| `--blue` | `#00b4d8` | Plan/Evaluate 节点激活色 |
| `--green` | `#00c853` | 完成状态 |
| `--red` | `#ff5252` | 错误状态 |
| `--yellow` | `#f5a623` | 执行中状态（与 accent 相同）|
| `--text` | `#e8eaed` | 主文字 |
| `--text-dim` | `#8b9099` | 次要文字 |
| `--text-muted` | `#5a6270` | 占位/禁用文字 |

### 3.2 字体

| 用途 | 字体 |
|------|------|
| UI 文字 | Inter, system-ui, sans-serif |
| 日志/代码 | JetBrains Mono, Fira Code, monospace |

### 3.3 圆角

- 大圆角 `--radius: 10px` — 面板、按钮
- 小圆角 `--radius-sm: 6px` — 输入框、子任务卡片

### 3.4 过渡

`--transition: .25s ease` 全局过渡动画

---

## 4. 布局规范

### 4.1 整体结构

```
┌──────────────────────────────────────────────────────┐
│  HEADER (56px，高固定)                                │
├──────────┬────────────────────────┬────────────────┤
│ 左栏     │     中栏（flex:1）       │   右栏          │
│ 280px    │     SVG DAG 可视化       │   300px         │
│ 固定宽度  │     自适应               │   固定宽度       │
├──────────┴────────────────────────┴────────────────┤
│  FOOTER（折叠面板，可展开）                           │
└──────────────────────────────────────────────────────┘
```

最小宽度：900px（小于此右栏隐藏）

### 4.2 DAG 节点布局（SVG viewBox="0 0 620 340"）

| 节点 | transform | 说明 |
|------|-----------|------|
| plan | translate(260, 35) | 顶部中央，宽100×高55 |
| researcher | translate(70, 200) | 4个 Agent 排排站 |
| coder | translate(170, 200) | 同上 |
| writer | translate(350, 200) | 同上 |
| reviewer | translate(450, 200) | 同上 |
| evaluate | translate(260, 285) | 底部中央，宽100×高45 |

### 4.3 连接线坐标

| 边 | 坐标 | 说明 |
|----|------|------|
| plan → researcher | (360,90)→(70,200) | 从 plan 右边缘发出 |
| plan → coder | (360,90)→(170,200) | 同上 |
| plan → writer | (360,90)→(350,200) | 同上 |
| plan → reviewer | (360,90)→(450,200) | 同上 |
| writer → reviewer | (450,200)→(450,255) | writer 右上→reviewer 左上 |
| researcher → evaluate | (120,255)→(220,285) | 各 Agent→evaluate |
| coder → evaluate | (220,255)→(240,285) | 同上 |
| writer → evaluate | (400,255)→(380,285) | 同上 |
| reviewer → evaluate | (500,255)→(400,285) | 同上 |

---

## 5. 节点状态机

| 状态 | CSS Class | 背景色 | 边框色 | 文字色 |
|------|-----------|--------|--------|--------|
| 空闲（默认）| `.dag-node` | `#20272f` | `#3a4050` | `--text-dim` |
| 激活 | `.dag-node.active` | `rgba(0,180,216,.2)` | `#00b4d8` | `#00b4d8` |
| 执行中 | `.dag-node.running` | `rgba(245,166,35,.2)` | `#f5a623` | `#f5a623` |
| 完成 | `.dag-node.done` | `rgba(0,200,83,.15)` | `#00c853` | `#00c853` |
| 错误 | `.dag-node.error` | `rgba(255,82,82,.15)` | `#ff5252` | `#ff5252` |

---

## 6. 边状态

| 状态 | CSS Class | 颜色 | 线型 |
|------|-----------|------|------|
| 空闲 | `.dag-edge` | `#3a4050` | 虚线（5,3）|
| 激活 | `.dag-edge.active` | `#00b4d8` | 实线 |
| 完成 | `.dag-edge.done` | `#00c853` | 实线 |
| 错误 | `.dag-edge.error` | `#ff5252` | 实线 |

---

## 7. 日志类型

| 类型 | CSS Class | 颜色 |
|------|-----------|------|
| 信息 | `.log-info` | `--text-dim` |
| 成功 | `.log-success` | `--green` |
| 警告 | `.log-warn` | `--yellow` |
| 错误 | `.log-error` | `--red` |
| 激活 | `.log-accent` | `--blue` |
| 节点事件 | `.log-node` | `--accent` + 左边框 |

---

## 8. 子任务状态

| 状态 | CSS Class | 样式 |
|------|-----------|------|
| pending | `.subtask-item.pending` | 半透明灰点 |
| running | `.subtask-item.running` | 黄色闪烁点 + 黄色边框 |
| done | `.subtask-item.done` | 绿色实心点 + 绿色边框 |
| failed | `.subtask-item.failed` | 红色实心点 + 红色边框 |

---

## 9. 快捷模板

```javascript
[
  '搜索最新AI新闻，总结3个关键趋势，写一份300字报告',
  '调研 Vue3 和 React 的优劣，给出选型建议',
  '分析某竞品，输出对比报告和优化建议',
]
```

---

## 10. API 接口（对接 FastAPI）

| 接口 | 方法 | 用途 |
|------|------|------|
| `POST /tasks` | JSON body `{task}` | 提交任务，返回 `{task_id}` |
| `GET /tasks/stream?task_id=xxx` | SSE | 流式接收 step/done/error 事件 |
| `GET /tasks/{id}` | — | 查询任务状态（备用）|

### SSE 事件格式

```json
// step 事件
{"event":"step","node":"plan","loop_count":1,"progress":"2/5","subtasks":[...],"logs":[...]}

// done 事件
{"event":"done","result":{"completed_count":4,"subtasks_count":4,"total_tokens":50000}}

// error 事件
{"event":"error","error":"错误描述"}
```

---

## 11. 响应式断点

| 断点 | 效果 |
|------|------|
| ≤900px | 右栏隐藏，左栏缩窄至 220px |
| ≤640px | Header 副标题隐藏，内边距缩小，左栏 180px |

---

## 12. 动画

```css
@keyframes blink     { 0%,100% opacity:1;  50% opacity:.3; }    /* 连接灯闪烁 */
@keyframes edgePulse { 0%,100% opacity:1;  50% opacity:.5; }    /* 活跃边脉冲 */
@keyframes nodePulse { 0%,100% filter:drop-shadow(0 0 4px yellow); 50% filter:drop-shadow(0 0 12px yellow); }  /* plan 循环脉冲 */
```

---

## 13. 滚动条

Webkit 风格：宽 5px，深色轨道，浅色滑块，hover 变亮。

---

## 14. server.py 设计

- 功能：静态文件服务器，serve `ui/` 目录
- 端口：`5173`（与 Vite 兼容）
- 路由：`/` → `index.html`，其他 → 静态文件
- 可选：代理 `/api/*` 到 `http://localhost:8000`（开发时绕过 CORS）
- 生产：直接用 FastAPI 的 `StaticFiles` 挂载 `ui/` 目录