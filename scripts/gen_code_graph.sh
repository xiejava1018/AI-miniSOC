#!/usr/bin/env bash
# 刷新代码知识图谱：codebase-memory 重索引 + 前端 madge 依赖检查
# 结果人工回填 docs/project-truth/code-graph.md 第 2/3 节
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "== codebase-memory 重索引 =="
codebase-memory-mcp cli --quiet index_repository "{\"repo_path\": \"$REPO\"}" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"nodes={d['nodes']} edges={d['edges']} status={d['status']}\")"

echo "== 前端 TS 层循环依赖 =="
cd "$REPO/src/frontend"
npx -y madge src/api src/hooks src/store src/utils src/router --extensions ts --circular

echo "== 前端 TS 层 orphans =="
npx -y madge src/api src/hooks src/store src/utils src/router --extensions ts --orphans
