#!/usr/bin/env bash
# OH-Q.1 mypy 类型检查闸门
#
# 分两层（诚实反映现状，不搞假绿）：
#   1) enforced：本项目新写的纯逻辑模块必须 0 mypy 错误（阻塞 CI）
#   2) baseline：全 app 扫描只记录数量（advisory，不阻塞），
#      随代码逐步收紧；历史代码 ~700 错误（多为 SQLAlchemy/implicit-Optional）
#      不是本闸门要一次清掉的。
set -uo pipefail
cd "$(dirname "$0")/.."

PYTHON=${PYTHON:-python}
# 优先用项目 venv（脚本位于 src/backend/scripts，venv 在项目根）
if [ -x ../../venv/bin/python ]; then PYTHON=../../venv/bin/python; fi

echo "==> [1/2] enforced clean subset"
ENFORCED=(
  app/core/asset_ontology.py
  app/core/asset_ontology_owl.py
  app/core/asset_ontology_stix.py
  app/core/alert_levels.py
  app/services/identity_fusion.py
  app/services/identity_ueba.py
  app/mcp/tools/asset_base.py
)
$PYTHON -m mypy --follow-imports=silent "${ENFORCED[@]}"
rc=$?
if [ $rc -ne 0 ]; then
  echo "FAIL: enforced subset has type errors"
  exit $rc
fi

echo
echo "==> [2/2] advisory full baseline (non-blocking)"
$PYTHON -m mypy app/core app/services app/api app/models 2>&1 \
  | tail -1 | sed 's/^/baseline: /' || true

echo
echo "PASS: enforced subset clean"
