# 代码知识图谱工具链（AI agent 提效）

> 目的：减少 agent 熟悉代码的 token 消耗。三层：符号检索、调用图谱、静态文档。

## 1. Serena MCP（符号级检索，agent 日常用）

- 已接入 pi（`pi-mcp-adapter` + `~/.pi/agent/mcp-adapter.json`），懒启动常驻。
- 二进制：`~/.local/bin/serena`（`uv tool install git+https://github.com/oraios/serena`）。
- 典型用法：`find_symbol`（找定义）、`find_referencing_symbols`（找调用方，代替 grep+读多文件）。
- 语言：Python（LSP 精确）+ TS/JS（本项目前端）。

## 2. codebase-memory-mcp（调用图/影响分析）

- 已接入 pi 同一配置文件，懒启动常驻。
- 二进制：`~/.npm-global/bin/codebase-memory-mcp`（native，GitHub release 经 gh-proxy 镜像下载——直连超时）。
- 本项目索引：**20,373 节点 / 59,025 边**（Tree-sitter，排除 venv/.git 等 31 目录）。
- 工具：`get_architecture`、调用链查询、影响分析；另有 UI（`--ui=true`，端口 9749）。
- 重新索引：`codebase-memory-mcp cli index_repository '{"repo_path": "<repo>"}'`

## 3. 前端 madge（TS 层依赖检查）

- madge 解析不了 `.vue` SFC，限定目录分析 TS 层（api/hooks/store/utils/router，111 文件）。
- 当前结果（2026-10-10）：**无循环依赖**；orphans 均为动态引用或入口（正常）。
- 命令：
  ```bash
  cd src/frontend
  npx madge src/api src/hooks src/store src/utils src/router --extensions ts --circular
  npx madge src/api src/hooks src/store src/utils src/router --extensions ts --orphans
  ```
- `.vue` 组件间依赖由 Serena TS 后端 + codebase-memory 覆盖。

## 4. 静态文档（高频硬事实）

- `docs/project-truth/snapshot.md` — `scripts/sync_claude_md_truth.py` 生成，保持权威。
- `docs/code-wiki.md` — 手写架构概览（**较陈旧**，结构以 snapshot + 本文件为准）。

## 维护约定

- 日常开发不用手动跑任何东西：Serena / codebase-memory 均懒启动 + 增量。
- 大重构或里程碑后跑一次 `scripts/gen_code_graph.sh` 刷新本文件第 2/3 节数字。
