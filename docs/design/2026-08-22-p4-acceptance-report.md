# P4 数据可靠性收尾 — 验收报告（主 Agent 独立核验）

**验收日期**: 2026-08-22
**被验收文档**: `docs/design/2026-08-22-p4-remaining-gaps-execution-plan.md` v1.2（pi agent 实施，提交 `c831884` + `b820b3e`）
**验收方法**: 独立读码 + 跑测试套件 + 追调用链，不采信实施者自述
**结论**: WO-1 / WO-3 / WO-4 / WO-5 **验收通过**；WO-2 **有条件通过（存在真实缺口，需返工）**

---

## 1. 测试套件核验

运行 `tests/services/` 下 P4 受影响套件（分页 / 覆盖 / 既有 loki 分页 / push_notifications / source_health）：

```
37 passed, 4 warnings in 223.96s
```

- 37 passed 与文档 §7 自述一致，**属实**。
- 其中 4 warnings 为某测试启停 uvicorn server 的线程退出噪声（`SystemExit: 3` 在 shutdown），与 P4 无关，不影响结论。
- ⚠️ **测试绿 ≠ 行为对**：`test_source_health_coverage.py` 场景 1 用的是**合成 `@track_task` 探针**（非真实资产同步），场景 2 仅测成功路径。真实 `WazuhAgentSyncService` 失败 → `source_health` 的路径**未被任何测试覆盖**（详见 §3）。

---

## 2. 逐工单验收

### WO-1 🔴 调度检测 Loki 分页接线 — ✅ 通过
- `scheduler.py:83-109`：`query_range` → `query_range_paginated`；`try/except LokiTruncationError` 降级单次拉取 + `stats["loki_truncated"/"loki_total_values"]` 透出。
- `stats` 在 try 前已初始化（`:62`），无 NameError。
- 测试 `test_browsing_scheduler_pagination.py`（10 项）覆盖「正常走分页 / 截断降级 + 信号」。
- 小注（非阻断）：`:91 if truncated:` 为**死分支**——`query_range_paginated` 成功恒返 `truncated=False`，截断走 `except`。无害，可后续清理。

### WO-3 🟡 API 层 Loki 分页接线 — ✅ 通过（合理收窄）
- 仅 `POST /rules/test`（`:391`）改分页 + 降级 + `truncated` 透出。
- 经独立读码核实收窄理由成立：
  - `:487 /logs`、`:699 /events/{id}/logs`：`limit` 为用户指定（`Query(200,le=10000)` / `Query(100,le=500)`），截断是参数契约非事故。
  - `:559-567 /statistics`：`query_range` 内是 `sum(count_over_time(...))` **LogQL 聚合查询**（返回 metric 序列），分页按时间分片会拆散聚合，确不适用。
- 对 :487/:699 强行分页会违背 limit 语义或拖垮 UI，收窄合理。

### WO-4 🟢 source_key 去重 — ✅ 通过
- `scheduler.py:52` `@track_task(source_key="loki:browsing_detection")`，与函数体内显式上报一致，消除同源双行。历史 `loki:browsing` 行只读保留。

### WO-5 🟢 alembic 文件名对齐 — ✅ 通过
- `git mv` 完成：`a1b2c3d4e5f6_*` → `a1b2c3d4e5f7_*`。
- 独立核验：`alembic history` HEAD=`i3j4k5l6m7n8`、BASE=`c5962ab1f662`、27 步、单链不变；`versions/` 下 `a1b2c3d4e5f6_*`（asset_data_classification，内部 revision 真为 e5f6，不可动）与 `a1b2c3d4e5f7_*`（vuln，内部 revision e5f7）前缀已唯一化，歧义消除。

### WO-2 🟡 采集源健康上报覆盖补全 — ⚠️ 部分完成（有真实缺口）

**✅ 已正确落地的部分：**
1. **隐藏 bug 修复（高价值，pi agent 自报、本 Agent 独立核实）**：原 decorator 成功路径 `SourceHealthRecorder(source_key=...)` 构造即 `TypeError`（构造器要求 `db`），被外层 `except` 静默吞 → **成功上报从未真正写入**。现改为 `SourceHealthRecorder(db)` 并补失败分支（`:340-361`，含 `db.commit()/rollback()`）。这是文档未覆盖、v1.0/v1.1 评审都漏掉的真实修复。
2. **opensearch 双路上报完整**：`opensearch_scap_sync.py` 成功 + 失败均 `record_success/record_failure("opensearch:vuln", ...)`。

**❌ 未达成的部分（wazuh / tplink 失败路径缺失）：**
- `asset_sync_handler.py` 全文件 grep 结果：**仅 1 处 `record_success`（`:83`）、0 处 `record_failure`**。
- `WazuhAgentSyncService.sync_agents`（`:27`）/ `sync_single_agent`（`:134`）是**普通方法，未被 `@track_task` 包裹**；异常仅 `logger.error` + `raise`（`:52-54`），无 `record_failure`。
- 调用入口 `app/api/data_sync.py:87`、`app/api/webhooks.py:65`（tplink 推送）均非 `@track_task`，故 decorator 的失败分支对这两源**永不触发**。
- 文档 §7 声称「wazuh/tplink 都流经 `AssetSyncHandler.handle`，集中上报即覆盖两源」——**仅覆盖成功**；源中断时 `handle` 根本不会被调用，失败无人记录。

**直接后果（与 WO-2 验收标准 #2 冲突）：**
- `wazuh/tplink` 行 `record_success` 时**未传 `expected_interval_seconds`** → 该行 `expected_interval_seconds = NULL`。
- `app/api/data_health.py:_source_status`（`:62-63`）守卫为 `if interval and sh.last_success_at:` → `interval` 为 NULL 时跳过 degraded 判定；又因无 `record_failure`，`last_failure_at` 为 NULL → 不走 "down" 分支（`:58-61`）。
- 结果：wazuh/tplink **中断数天，`GET /api/v1/data-health` 仍显示 `healthy`（假绿）**，而 WO-2 验收标准 #2 明确要求「停掉 wazuh 同步 → 该源标红」。

**缓解（非等价）：**
- `push_notification_service.check_source_health`（`:182` `or 0` + `down_hours` 阈值）与 `dashboard_service`（`:146` `or 300`）会因 `last_success_at` 陈旧而**报 critical / 标红**——所以「主动推送」基本达成，但用户最直接看的 `/data-health` 页面不红，且缺 `last_failure_message` 诊断信息。
- 对比：opensearch 有 `record_failure` → `last_failure_at` 被写 → `_source_status` 返回 `down`（红）。**有无 `record_failure` 正是 wazuh/tplink 与 opensearch 行为分叉的根因**。

---

## 3. 返工建议（WO-2 补丁，任选其一即可闭环）

- **A（最小改动，推荐）**：在 `AssetSyncHandler.handle` 外层包 `try/except`，异常时 `SourceHealthRecorder(db).record_failure(key, source_type=source, error=...)` 再 `raise`；同类补 `WazuhAgentSyncService.sync_agents` 的 `except`（`:52`）。
- **B（最契原计划 §3.1.1 设计 #2）**：把资产同步入口 `@track_task(source_key="wazuh:agents"/"tplink:collector")` 包裹，直接复用已修好的 decorator 失败分支，未来新采集器自动纳入。
- **C（一致性）**：`record_success` 补 `expected_interval_seconds`（如 300），使 `data_health` 的 degraded 判定与 `dashboard_service` 对齐。

并补一条**真实失败路径**测试（直接调 `WazuhAgentSyncService.sync_agents` 且 `wazuh_client.get_agents` 抛异常 → 断言 `wazuh:agents` 行 `last_failure_at` 非空 / `_source_status` 为 `down`），替代现有合成探针。

---

## 4. 签字建议

| 工单 | 验收 | 说明 |
|---|---|---|
| WO-1 | ✅ 通过 | 代码 + 测试齐全 |
| WO-2 | ⚠️ 有条件通过 | opensearch 完整；wazuh/tplink 失败标红未达成（`/data-health` 假绿），需补 A/B/C 之一后复验 |
| WO-3 | ✅ 通过 | 收窄有理有据 |
| WO-4 | ✅ 通过 | |
| WO-5 | ✅ 通过 | alembic 链完好 |

**P4 整体签字条件（文档 §5）当前未完全满足**：「任意采集源（含 wazuh/tplink）中断 → 标红 + 主动推送」对 wazuh/tplink 因 WO-2 缺口仍不成立（推送可达、dashboard 可达，但 `/data-health` 页面假绿）。建议 WO-2 补丁落地并复验后再宣布 P4 完成。

> 诚实留痕：文档 §7 当前写「WO-1~WO-5 全部实施完成」，与本节核验结论不一致，建议追加 v1.3 段落记录 WO-2 wazuh/tplink 失败路径缺口（与 §0 既有的「诚实留痕、结论置信度须与验证深度成正比」文化一致）。

---

## 5. 复核（2026-08-22 16:13）：WO-2 返工已验收通过

pi agent 据 §3 返工建议实施（提交 `dcee4a5` fix(wo2) + `fda3276` 文档记录），本 Agent 独立读码 + 跑测试复核，结论：**WO-2 真实缺口已闭环，P4 现可整体宣布完成。**

### 复核证据
- **`asset_sync_handler.py`**：`handle()`(`:59-129`) 整体包 try/except；成功路径 `record_success(key, expected_interval_seconds=_SOURCE_HEALTH_INTERVALS.get(source))`（`:96-101`）；源级异常走 `record_failure(key, source_type, error)` 且用**独立 session**(`fail_db=SessionLocal()`) 防被外层 rollback 灭掉（`:112-128`）后照 `raise`（上游 API 返 500）。✅
- **`wazuh_agent_sync.py:52-71`**：`sync_agents` 异常分支独立 session 记 `record_failure("wazuh:agents")` — 兜住「Wazuh API 本身不可达、handle() 都没调」的情况。✅
- **`asset_sync.py`**：`sync_from_wazuh` / `sync_single_asset` / `sync_single_agent_webhook` 均补成功+失败双路（双 session 隔离）。✅
- **key 对齐**：`_SOURCE_HEALTH_KEYS`(`:29-33`) `"wazuh"→"wazuh:agents"`，与 `wazuh_agent_sync` 硬编码 `"wazuh:agents"` 同表同行；`tplink`/`tplink-router"→"tplink:collector"` 与生产实测一致 → 无双行错位。✅
- **签名匹配**：`source_health.record_failure(source_key,*,source_type,error)` / `record_success(...,expected_interval_seconds)` 与调用完全一致。✅
- **页面判红**：`data_health._source_status(:58-61)` 在 `last_failure_at` 晚于 `last_success_at` 时返回 `down` — 假绿根因已堵。✅
- **迁移** `n1o2p3q4r5s6`：回填 `tplink:collector`/`wazuh:agents` 的 `expected_interval_seconds=300`，旧生产行 degraded 判定立即生效。✅
- **测试**：删合成探针 `test_source_health_coverage.py`，新增 `test_wo2_real_failure_path.py`(5 项真失败路径：patch `wazuh_client.get_agents` 抛错 → 断言 `wazuh:agents` 行 `last_failure_at`/`failure_count`/`last_failure_message`)+ `test_source_health.py`(7 项)；独立运行 **12 passed**（4 warnings 为 uvicorn 启停噪声，exit 0）。✅

### 签字更新
| 工单 | 验收 | 说明 |
|---|---|---|
| WO-1 | ✅ 通过 | |
| WO-2 | ✅ 通过（复验） | wazuh/tplink 失败标红 + interval 回填 + 真失败测试，缺口闭环 |
| WO-3 | ✅ 通过 | |
| WO-4 | ✅ 通过 | |
| WO-5 | ✅ 通过 | |

**P4 整体签字条件（文档 §5）现已满足**：「任意采集源（含 wazuh/tplink）中断 → 标红 + 主动推送」已对全部资产类同步源成立。可宣布 **P4（数据可靠性）完成**。

> 小注（非阻断）：当 `wazuh_client.get_agents()` 抛错时，`handle()` 的 except 与 `sync_agents` 的 except 会**对同一 `wazuh:agents` 行各记一次 `record_failure`**（failure_count +2），无害仅冗余，可后续合并去重。
