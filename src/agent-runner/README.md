# AI-miniSOC Agent Runner

POC 阶段:Node.js 子进程运行时,用于在 AI-miniSOC 后端(FastAPI)中以 stdio JSON-RPC 方式托管 Pi Agent。

## 角色定位

- **不是** Web 前端、不是后端 API、不是采集器
- **是** 一个独立的 Node.js 子进程,由 Python 端通过 `subprocess.Popen` 拉起
- 与 Python 端通过 **stdin/stdout(行分隔 JSON)** 通信
- 内部使用 Pi Agent Core / Pi AI 作为推理引擎

## 目录结构

```text
src/agent-runner/
├── package.json            # Node 包定义 (ESM, type=module)
├── .npmrc                  # save-exact + min-release-age=2 (跟随 Pi 项目实践)
├── .gitignore              # node_modules / *.log / dist
├── README.md               # 本文件
├── config.example.json     # 配置模板(由实际配置加载流程读取)
└── src/
    └── pi-agent-runner.js  # 入口(stdio 模式) — 由后续 agent 实现
```

## 运行

```bash
# 安装依赖(由后续 agent 执行,本骨架不安装)
npm install --ignore-scripts

# stdio 模式:由 Python 父进程启动,通常不直接手动跑
npm start
```

## 通信协议(POC 草案)

- **传输**: stdin/stdout,**行分隔 JSON**(每行一条消息)
- **方向**:
  - `Python -> Node`: `{"type": "chat", "id": "...", "messages": [...], "tools": [...]}`
  - `Node -> Python`: `{"type": "event", "event": "...", "data": {...}}` 或最终回复
- **鉴权**: 启动时 Python 端传入 `service_token`,本进程在每个请求中带上

## 依赖

| 包 | 用途 |
|----|------|
| `@earendil-works/pi-agent-core` | Pi Agent 主循环、工具注册、消息流 |
| `@earendil-works/pi-ai` | Pi 的 LLM 客户端(provider 抽象) |

> **注意**: 实际版本在 `npm install` 时由 `save-exact=true` 锁定,本文件暂用 `*` 占位。

## 约束

- Node >= 20(本地验证 v24.12.0 可用)
- 纯 ESM(`"type": "module"`)
- 不连外网,所有依赖通过 npm 拉取后冻结
- 不触碰 `src/backend/` 或 `src/frontend/` 任何文件
