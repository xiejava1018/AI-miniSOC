# P4 数据可靠性 — 剩余缺口详细设计与可执行工单

**文档版本**: v1.1
**创建日期**: 2026-08-22
**最后更新**: 2026-08-22（v1.1：按 pi agent 评审意见修订，含第三处误判留痕）
**状态**: RevDraft（v1.0 评审后修订，待终审）
**作者**: 主 Agent（代码核实）/ 交付 pi agent 评审
**关联文档**:
- `docs/design/2026-08-16-数据可靠性全面梳理与完善方案.md`（P4 原始梳理）
- `docs/design/2026-08-16-后台任务执行可观测性梳理与方案-v0.4.1.md`（任务可观测性）

---

## 0. 修订说明（诚实留痕）

本文档的"剩余缺口"是在**逐文件代码核实**后得出的，并**修正了历史评审中的三处误判**（前两处为 v1.0 自查发现，第三处为 v1.1 评审发现），特此留痕：

| 上一轮误判 | 本轮代码核实结论 | 修正动作 |
|---|---|---|
| "GAP C：行为事件 `ai_analysis_id` 模型未声明 FK、无 ondelete（与 incident_id 不一致）" | `src/backend/app/models/browsing_event.py:57-59` 实际已声明 `ForeignKey("soc_ai_analyses.id", ondelete="SET NULL")`，与 `incident_id`(:50-52) 一致；迁移 `b5c6d7e8f9a0` 也加了同语义 FK | **GAP C 关闭，不立工单**（见 §3.3） |
| "GAP A：源健康 `SourceHealthRecorder` 全仓生产代码零调用" | `browsing_detection/scheduler.py:140-165` 已显式调用 `record_success/record_failure`；`task_observability/decorator.py:337-342` 在任务成功时记录 source_key 健康 | **GAP A 边界收窄**：recording 已部分落地，缺口转为"覆盖不全 + 缺主动告警触发"（见 §3.1） |

> v1.1 补充留痕（**第三处误判，评审发现**）：v1.0 的 GAP A.2 断言
> `check_source_health()`「没有任何周期调度调用它」——**同样是误报**。实际调用链：
> `main.py:71 start_push_scheduler()` → `push_scheduler._loop()`（默认 30 分钟）→
> `run_push_once()` → `PushNotificationService.run_all()`（:430）→
> `check_source_health()`（:198）。生产日志实锤（2026-08-22）：
> `08:20:09 push scheduler round: {'source_health': 2, ...}`——源健康巡检
> 当天在生产实际发出了 2 条 critical 通知，闭环早已运转（P3 F4.2 交付的
> 5 场景推送第 1 场景即此，v1.0 作者漏看了 push_scheduler 调度入口）。
> 原 GAP A.2 与 WO-1 整体撤销，详见 §3.1.2。

> 本文档 v1.0 的"已修复"断言均经 `grep`/`Read` 实测；但 GAP A.2 的"未修复"断言
> （无周期调度）恰恰漏验了调度入口存在性而误报——教训：**结论置信度必须与验证
> 深度成正比，severity 最高的断言尤需生产实据背书**（静态代码阅读之外，运行时
> 日志/调用链是更强的证据层）。

---

## 1. 背景与现状核实（哪些已修复）

P4 原始 7 项 + Fernet，经代码核实，当前真实状态如下：

| 原始项 | 代码证据 | 结论 |
|---|---|---|
| ① alembic 孤儿修订 / 无 alembic.ini | `src/backend/alembic/versions/` 实测为单链（根 `c5962ab1f662` → 头 `i3j4k5l6m7n8`），`alembic.ini`+`versions`+`migrations` 齐备；遗留文件 `a1b2c3d4e5f6_add_vulnerability_management_tables.py` 内含 `revision = a1b2c3d4e5f7`（仅文件名/修订号不一致，见 GAP E） | ✅ 已修复 |
| ② OpenSearch 双源字段不一致 | `src/backend/app/services/opensearch_scap_sync.py:43,203` 已走 `os_field_map` 映射层（集中 `os_field_map.py`），仅遗留壳 `wazuh_scap_sync.py` 仍被复用（见 GAP F） | ✅ 已修复 |
| ④ 行为事件 `risk_score` 常 null | 模型仅 `score` 字段，API 返回 `score`，根本无 `risk_score` 契约——原"常 null"系误报 | ✅ 已关闭（误报） |
| ⑤ 行为事件缺 FK | `browsing_event.py:50-59` 两 FK 均已声明 + 迁移 `b5c6d7e8f9a0` 加同语义 FK | ✅ 已修复（即被误判的 GAP C） |
| ⑥ 采集中断无感知 | `soc_source_health` 表 + `SourceHealthRecorder` + `is_healthy()` 已实现 + 单测通过；browsing scheduler 已接线 | 🟡 **部分**：recording 有、主动告警未触发（GAP A） |
| ⑦ KEV∩漏洞=0 未对齐 | `cisa_kev_service.py` 已按 `upper(cve_id)∈kev_set` 富化 `has_exploit` + 调度 | ✅ 已修复 |
| Fernet / ENCRYPTION_KEY | 此前实测为合法 Fernet | ✅ 已修复 |
| Loki `query_range` 截断 | `query_range_paginated` 已实现 + 单测通过，但**生产零调用**（仅 browsing scheduler 用截断版 `query_range`） | 🟡 **未接线**（GAP B） |

**结论**：P4 的 7 项原始硬伤中，5 项已真修、1 项误报关闭、1 项（⑥）经生产日志实锚也已闭环（v1.1 改判），外加 1 项新核出的"未接线"（Loki 分页）。真正的剩余缺口收敛为 **GAP A.1（源健康上报覆盖不全）**、**GAP A.3（source_key 重复）** 与 **GAP B（Loki 分页接线）**，加 2 项低优先级卫生项。
（v1.1 修订理由：v1.0 将 GAP A.2 列为唯一 🔴 核心，但该缺口被生产日志证伪，详见 §0 留痕；剩余缺口中唯一的 🔴 上移为 GAP B.1 调度检测截断。）

---

## 2. 剩余缺口总览

| 缺口 | 严重度 | 影响 | 已具备的 building block | 缺什么 |
|---|---|---|---|---|
| **GAP A.1** 采集源健康上报覆盖不全 | 🟡 中 | wazuh/tplink/opensearch 同步失败不标红；task decorator 仅记录成功不记录失败 | `SourceHealthRecorder`、browsing scheduler 样例 | 其他同步源未上报；decorator 失败路径缺失 |
| ~~GAP A.2 源健康主动告警未触发~~ | ~~🔴 高~~ | v1.1 **撤销**：push_scheduler 30 分钟巡检已覆盖且生产实测发过通知（§0 留痕）。若需更密集频率，改 `PUSH_SCHEDULER_INTERVAL_MINUTES` 即可，不立工单 | — | — |
| **GAP A.3** source_key 重复 | 🟢 低 | 同一逻辑源 `loki:browsing`（decorator）与 `loki:browsing_detection`（scheduler 显式）产生两行，dashboard 显示混乱 | — | 统一 source_key |
| **GAP B.1** 调度检测 Loki 截断（**critical**） | 🔴 高 | `scheduler.py:79` 用 `query_range(limit=10000)` 静默截断；窗口日志 >1 万行时行为事件**少算**，闭环被污染 | `query_range_paginated`（时间分片+硬上限+`LokiTruncationError`）已实现+单测，位于 `app/services/browsing_detection/loki_client.py:106` | 调度检测未改用 |
| **GAP B.2** API 层 Loki 截断 | 🟡 中 | `api/browsing.py` 多个端点用截断版，统计/导出可能不全 | 同上 | 5 处调用未改用 |
| **GAP B.3** MCP 工具 Loki 查询 | 🟢 可选 | `mcp/tools/loki_tools.py:49` 直连 HTTP（独立实现），无分页 | — | 可选补充分页 |
| **GAP C** 行为事件 FK 漂移 | — | — | 已核实模型正确声明 | **已关闭，不立工单** |
| **GAP D** Loki 7 天保留 | — | 基础设施现实，应用层改不了 | P3 F2.2 已用 `data_coverage` 限定窗口缓解 | **已接受约束，文档化** |
| **GAP E** alembic 文件名/修订号不一致 | 🟢 低 | `versions/` 下有**两个** `a1b2c3d4e5f6_` 前缀文件：`..._add_asset_data_classification_and_owner_contact.py`（内部 revision 真为 `a1b2c3d4e5f6`）与 `..._add_vulnerability_management_tables.py`（内部 revision 为 `a1b2c3d4e5f7`，仅文件名错位）。v1.0 只提及后者，未注明同前缀双文件存在（v1.1 补）；WO-5 重命名后前缀唯一化，歧义消除 | — | 改名对齐 |
| **GAP F** 遗留壳 `wazuh_scap_sync.py` | 🟢 信息 | 活入口已用 `os_field_map`，此文件仅命名问题 | — | 仅文档说明，不改逻辑 |

---

## 3. 详细设计

### 3.1 GAP A：数据源健康可观测性闭环

**目标**：让"采集中断"从"表标红无人知"变为"表标红 + 主动推送 + 多源覆盖"。

#### 3.1.1 A.1 采集源健康上报覆盖补全

**现状**：
- 已接线：`browsing_detection/scheduler.py:140-165`（显式 record_success/record_failure，`source_key="loki:browsing_detection"`）。
- task decorator `decorator.py:337`：`if source_key and status == TaskRunStatus.SUCCESS:` → 仅成功记录；**失败不记录 source_health**。
- 其他同步源（wazuh / tplink / opensearch）未被 `@track_task(source_key=...)` 包装，也无显式上报。

**设计**：
1. **集中化失败上报**：在 `decorator.py:353` 附近（`if status in (FAILED, TIMEOUT, ZOMBIE):` 分支）补一段：当 `source_key` 存在时调用 `SourceHealthRecorder(db).record_failure(source_key=source_key, source_type=..., error=error_text)`，与既有的成功上报对称。
2. **wazuh/tplink/opensearch 同步源显式上报**：在各自同步服务的 `except` 分支（采集/解析异常处）调用 `SourceHealthRecorder.record_failure`，成功路径调用 `record_success`。若这些服务已被 `@track_task(source_key=...)` 包装，则靠 3.1.1-① 即可覆盖，无需额外改动——实施前先确认注册情况（见 WO-2 验收）。
3. **source_key 规范**：为 wazuh/tplink/opensearch 各定义稳定 `source_key`（如 `wazuh:alerts`、`tplink:collector`、`opensearch:vuln`），与 `SourceHealth` 主键语义一致。

**不破坏既有**：browsing scheduler 的显式上报保留（与 decorator 双写无副作用，幂等 upsert）。
（v1.1 注：A.1 的告警出口已确认存在——decorator :353 后的失败分支本就会入通知队列由
notification drain 发送，加上 push_scheduler 30 分钟源健康巡检，WO-2 修复后中断告警
即刻生效，无需任何 watchdog 前置。）

#### 3.1.2 ~~A.2 源健康主动告警 watchdog~~（v1.1 撤销）

v1.0 断言 `check_source_health()` 无周期调度调用，拟新建 watchdog。评审证伪：

- 调用链实测：`main.py:71 start_push_scheduler()` → `_loop()`（默认 30 分钟，
  `PUSH_SCHEDULER_INTERVAL_MINUTES`，生产 .env 未覆盖）→ `run_push_once()` →
  `PushNotificationService.run_all()`（:430）→ `check_source_health()`（:198）。
- 生产实证（/var/log/aisoc/backend.log）：`2026-08-22 08:20:09 push scheduler
  round: {'source_health': 2, ...}` ——当天实际发出 2 条 critical 通知。
- **若照 v1.0 实施后果**：产生两个并行 watchdog（15min 新建 + 30min 既有）调
  同一检查，靠 dedup_title 24h 去重掩盖重复——不是修 bug，是造 bug。
- **唯一可能的真实诉求**（更密集的巡检频率）：改 `PUSH_SCHEDULER_INTERVAL_MINUTES`
  环境变量即可，一行配置，不立工单。

原验收锚点"把已造好的零件装到运转的机器上"不成立——零件早已装好且在运转。

#### 3.1.3 A.3 source_key 去重

- 统一为 `loki:browsing_detection`：将 `scheduler.py:52` 的 `@track_task(..., source_key="loki:browsing")` 改为 `source_key="loki:browsing_detection"`，与 :142/:166 显式上报一致。
- 注意：去重后历史 `loki:browsing` 行可保留（只读），新写入统一新 key；dashboard 按 `source_key` 聚合天然去重。

### 3.2 GAP B：Loki 全量拉取接线

**目标**：让"已写好但未接线"的 `query_range_paginated` 真正用于生产拉取，消除静默截断。

#### 3.2.1 B.1 调度检测 Loki 分页接线（**critical**）

**现状**：`scheduler.py:76-84` 调用 `client.query_range('{exporter="OTLP"}', start_ns, end_ns, 10000)`——单次、limit=10000、无分页。窗口内日志 >1 万行时静默截断。

**设计**：
1. 将 `:79` 的 `client.query_range(...)` 改为 `client.query_range_paginated(query, start_ns, end_ns)`（默认 `page_step`=1h、`page_limit`=10000、`hard_limit`=`HARD_RESULT_LIMIT`）。
2. `query_range_paginated` 返回 `(results, total_values, truncated)` 并在超 `hard_limit` 时抛 `LokiTruncationError`（见 `browsing_detection/loki_client.py:106-174`）。调度检测需 `try/except LokiTruncationError`：
   - 捕获后：记录 `logger.warning`（已内置）；**截断信号落点（v1.1 定案，不再犹疑）**：
     写入 `run_detection_once` 返回的 stats dict（新增 `loki_truncated: true` /
     `loki_total_values: N` 字段）——`@track_task` 已持久化 stats 到 `soc_task_runs`，
     零接口改动即可观测。**不走 `SourceHealthRecorder.record_failure`**（截断≠采集中断，
     写 failure 会误使 `is_healthy()` 标红）；也不给 `record_success` 加 `warning` 参数
     （实测签名无此参数，改共享接口影响面不必要）。
   - 不因截断中断检测：截断时仍用已拉取的部分流继续解析（保证可用性，但 stats 标记数据不全）。
3. 不破坏既有：调用方 `sum(len(s.get("values", [])) for s in streams)` 对 `results` 列表同样适用（结构一致）。

#### 3.2.2 B.2 API 层 Loki 分页接线（中）

**现状**：`api/browsing.py` 中以下调用使用截断版 `query_range`：
- `:391` `query_range('{exporter="OTLP"}', start_ns, end_ns, limit=10000)`
- `:487` `query_range(query, start_ns, end_ns, limit)`
- `:546` `query_range(q, start_ns, end_ns, 10000, "forward", step)`
- `:568` `query_range(q, hm_start_ns, end_ns, 200, "forward", step)`
- `:683` `query_range(query, start_ns, end_ns, limit)`

**设计**：对统计/导出类端点（:391/:487/:546/:683）改用 `query_range_paginated` 并消费 `truncated`；纯 UI 小窗口预览（:568 limit=200）可保持原样（截断风险低）。所有 `query_range_paginated` 调用需用 `asyncio.to_thread` 包裹（与 :487/:546 现有范式一致）。

#### 3.2.3 B.3 MCP 工具 Loki 查询（可选）

`mcp/tools/loki_tools.py:49` 是独立直连 HTTP 实现（不走 `LokiClient`）。可选增强：在 `loki_query_range` 工具内加分页或至少返回 `truncated` 提示。优先级最低，不阻塞 P4 验收。

### 3.3 GAP C：已复核关闭（留痕，不立工单）

`browsing_event.py:57-59`：`ai_analysis_id = Column(ForeignKey("soc_ai_analyses.id", ondelete="SET NULL"))`，与 `incident_id`(:50-52) 语义一致；迁移 `b5c6d7e8f9a0` 加同语义 FK。`create_all` 与迁移均复现该 FK，**无模型漂移**。无需修改。

### 3.4 GAP D：Loki 7 天保留（已接受约束）

基础设施现实（Loki 默认 7 天保留），应用层无法修改。已在 P3 F2.2 用 `data_coverage` 限定查询窗口缓解报告不完整风险。**本计划不立项**，仅在此留痕，避免重复误判为"待修复"。

### 3.5 GAP E/F：命名卫生（低优先级）

- **GAP E**：将 `src/backend/alembic/versions/a1b2c3d4e5f6_add_vulnerability_management_tables.py` 重命名为 `a1b2c3d4e5f7_add_vulnerability_management_tables.py`（使其文件名前缀与文件内 `revision = a1b2c3d4e5f7` 一致）。**v1.1 补注**：`versions/` 下存在另一个同前缀文件 `a1b2c3d4e5f6_add_asset_data_classification_and_owner_contact.py`（其内部 revision 真为 `a1b2c3d4e5f6`，**不可动**）；本重命名恰好使前缀唯一化，彻底消除歧义。**注意**：重命名不影响 alembic 链（链靠 revision 变量，不靠文件名），但需确保 `git mv` 而非新建，避免重复修订。
- **GAP F**：`wazuh_scap_sync.py` 为遗留兼容壳（被 `opensearch_scap_sync.py` 复用落库逻辑），活入口已用 `os_field_map`。**仅文档说明，不改逻辑**，避免引入回归。

---

## 4. 可执行工单（Work Orders）

> 每张工单按"目标 / 修改文件 / 具体改法 / 验收标准 / 依赖 / 估时"组织，可直接交 agent 实施。

### WO-1 🔴 调度检测 Loki 分页接线（GAP B.1，critical）【v1.1：原 WO-2 升位】

> v1.1 修订：v1.0 的 WO-1（新建 source_health_watchdog）整张撤销——其前提被
> 生产日志证伪（见 §3.1.2）。原 WO-2 是剩余缺口中唯一真 🔴，升为第一优先。

- **目标**：消除调度检测对 Loki 的静默截断。
- **修改文件**：`src/backend/app/services/browsing_detection/scheduler.py`（:76-84）。
- **具体改法**：
  - `:79` 改 `client.query_range_paginated('{exporter="OTLP"}', start_ns, end_ns)`（位于 `app/services/browsing_detection/loki_client.py:106`）。
  - `try/except LokiTruncationError`：捕获后 `logger.warning` + 在返回 stats dict 写 `loki_truncated: true` / `loki_total_values: N`（落点定案理由见 §3.2.1：不写 SourceHealthRecorder failure，避免误标红；不改 record_success 签名）；仍用已拉取 `results` 继续解析。
  - `streams` 变量名不变（paginated 返回 `results` 同为流列表）。
- **验收标准**：
  1. 单测：mock `query_range` 返回超 `hard_limit` 的分片 → 断言抛 `LokiTruncationError` 且 `truncated=True`（扩展 `test_loki_client_pagination.py`）。
  2. 集成：小数据窗口行为不变（`fetched` 计数一致）；超大数据窗口不再静默丢行（`soc_task_runs.stats` 出现 `loki_truncated`）。
  3. 调度检测端到端跑通，无回归。
- **依赖**：无。
- **估时**：0.5 天。

### WO-2 🟡 采集源健康上报覆盖补全（GAP A.1）【v1.1：原 WO-3，依赖解除】

- **目标**：wazuh/tplink/opensearch 同步失败标红；decorator 失败路径补上报。
- **修改文件**：
  - `src/backend/app/services/task_observability/decorator.py`（:353 附近 FAILED/TIMEOUT/ZOMBIE 分支）。
  - wazuh / tplink / opensearch 同步服务（实施前先 `grep @track_task` 确认是否已包装 source_key；若已包装则仅靠 decorator 修复即可覆盖）。
- **具体改法**：
  - decorator 失败分支：`if source_key: SourceHealthRecorder(db).record_failure(source_key=source_key, source_type=source_key.split(":",1)[0], error=error_text)`。
  - 未包装的同步源：在 `except` 块加 `record_failure`、成功路径加 `record_success`，`source_key` 用规范命名（`wazuh:alerts` / `tplink:collector` / `opensearch:vuln`）。
- **验收标准**：
  1. 单元：mock 某同步源抛异常 → 断言 `soc_source_health` 对应 `source_key` 行 `failure_count` 增、且 dashboard `is_healthy()` 返回 False。
  2. 手动：停掉 wazuh 同步 → 跑一次 → `GET /api/v1/data-health` 该源标红。
- **依赖**：~~WO-1~~ 无（v1.1：原依赖 "WO-1 watchdog 触发后才有人收到告警" 不成立——告警出口已由 push_scheduler 30 分钟巡检 + decorator 失败入通知队列双路覆盖，本工单可独立实施且即刻生效）。
- **估时**：1 天。

### WO-3 🟡 API 层 Loki 分页接线（GAP B.2）【v1.1：原 WO-4 顺移】

- **目标**：统计/导出端点不再静默截断。
- **修改文件**：`src/backend/app/api/browsing.py`（:391 / :487 / :546 / :683）。
- **具体改法**：统计/导出类改用 `query_range_paginated` 并用 `asyncio.to_thread` 包裹（:568 小窗口保持原样）；消费 `truncated` 信号（前端可提示"数据可能不全"）。
- **验收标准**：
  1. 现有 `browsing` API 测试无回归。
  2. 大数据窗口下 `truncated` 被记录/透出。
- **依赖**：无。
- **估时**：0.5 天。

### WO-4 🟢 source_key 去重（GAP A.3）【v1.1：原 WO-5 顺移】

- **目标**：同一逻辑源不产生两行。
- **修改文件**：`src/backend/app/services/browsing_detection/scheduler.py`（:52 `@track_task(source_key="loki:browsing")` → `"loki:browsing_detection"`）。
- **验收标准**：`GET /api/v1/data-health` 中 Loki 上网行为检测仅一行；既有 `loki:browsing` 历史行不影响（只读）。
- **依赖**：无。
- **估时**：0.1 天。

### WO-5 🟢 alembic 文件名对齐（GAP E）【v1.1：原 WO-6 顺移】

- **目标**：消除文件名/修订号不一致陷阱。
- **修改文件**：`git mv src/backend/alembic/versions/a1b2c3d4e5f6_add_vulnerability_management_tables.py src/backend/alembic/versions/a1b2c3d4e5f7_add_vulnerability_management_tables.py`。
- **验收标准**：`alembic history` 链不变（仍单链到 `i3j4k5l6m7n8`）；无重复 revision。
- **依赖**：无。
- **估时**：0.1 天。

---

## 5. 验收总口径

P4 视为"真正完成"的签字条件：

1. **A 闭环**：任意采集源（含 wazuh/tplink/opensearch）中断 ≥ 阈值（默认 2× 周期或配置 down_hours）→ `soc_source_health` 标红 **且** 主动推送 critical 通知（WO-2 单工单即可验证；v1.1 注：告警出口本身已在运转，无需联调新 watchdog）。
2. **B 无截断**：调度检测在 >1 万行/窗口场景下不再静默丢数据，截断信号进入可观测（WO-1，`soc_task_runs.stats.loki_truncated`）。
3. **无回归**：v1.1 修正：~~26 个 P3 文件 `py_compile`~~（本文档是 P4，且 py_compile 过弱、覆盖不了调度逻辑）→ 改为：**P4 涉及文件跑对应测试套件**（WO-1 跑 `test_loki_client_pagination.py` + browsing_detection 相关；WO-2 跑 `test_source_health.py`），加上受影响模块的 `python -c import` 冒烟；现有 `test_push_notifications.py` 全绿。
4. **文档化**：GAP C（已关闭）、GAP D（已接受）在 `CLAUDE.md` 或本方案 §3.3/§3.4 留痕，避免后续误判为待修复。

**建议实施顺序**（v1.1 重排）：WO-1（调度检测分页，唯一 🔴）→ WO-2（上报覆盖补全，无依赖可并行）→ WO-3（API 层分页）→ WO-4（source_key 去重）→ WO-5（alembic 改名）。WO-1/WO-2 收益最大、改动最小，建议优先。

---

## 6. 修订记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-08-22 | 初版：基于代码级核实收敛剩余缺口。修正上一轮两处误判（GAP C 模型 FK 实际已声明、GAP A 的 SourceHealthRecorder 已在 browsing scheduler 接线）；将"真正的剩余缺口"定为 GAP A（A.1/A.2/A.3）+ GAP B（B.1/B.2/B.3）+ GAP E/F 卫生项，GAP C/D 留痕关闭；拆 6 张可执行工单（WO-1~WO-6），含精确文件/行号与验收口径 |
| v1.1 | 2026-08-22 | pi agent 评审后修订：①撤销 GAP A.2 / 原 WO-1（新建 watchdog）——`check_source_health` 已被 `push_scheduler` 30 分钟巡检周期调用，生产日志 2026-08-22 08:20:09 实锤发出过 2 条 critical 通知，原断言"无周期调度"误报；工单编号顺移（原 WO-2 升为 WO-1）；②原 WO-3 依赖行解除（告警出口已存在，可独立实施）；③GAP E 补注同前缀双文件（另一个 `a1b2c3d4e5f6_*.py` 内部 revision 真为 e5f6，不可动）；④WO-1（原 WO-2）截断信号落点定案为 `soc_task_runs.stats.loki_truncated`——`record_success` 实测无 warning 参数，且截断写 failure 会误标红 `is_healthy()`；⑤§5.3 验收修正："P3 py_compile"→P4 对应测试套件（py_compile 覆盖不了调度逻辑）；⑥`loki_client.py` 引用补目录前缀 `browsing_detection/`。核心教训（写入 §0）：结论置信度必须与验证深度成正比，severity 最高的断言尤需生产实据背书 |
