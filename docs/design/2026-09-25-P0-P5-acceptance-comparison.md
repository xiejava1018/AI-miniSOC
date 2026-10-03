# AI-miniSOC P0–P5 验收对照报告（代码级独立核验）

> 核验日期：2026-09-25
> 核验人：主 Agent（独立代码级核验，不采信任何自述/历史报告结论）
> 核验方法：`git log` + 目录/接口/函数级 grep + 静态读码；必要时标注"需运行时确认"
> 路线图框架：**采用用户维护的 P0–P5 战略路线图**（见 §0 说明，与 08-16 路线盘点的相位号不完全一致）

---

## 0. 路线图相位说明（先对齐口径，避免混淆）

本项目存在两套相位命名，本次统一用**用户战略路线图**口径：

| 本报告的 P 阶段 | 目标 | 08-16《路线图盘点》中的对应相位 |
|---|---|---|
| **P0** | 告警降噪聚合 | P0（降噪+关联+研判）的一部分 |
| **P1** | 告警-资产自动关联 | P0 的一部分 |
| **P2** | AI 研判 | P0 的一部分 + 原"上网行为检测" |
| **P3** | 事件闭环 | P1 的一部分 |
| **P4** | 脆弱性管理 + 数据可靠性 | P1（脆弱性）+ P4（数据可靠性） |
| **P5** | 威胁情报 / SOAR / 知识库 | P5（情报+SOAR+报告+知识库） |

> 额外已落地能力（不在 P0–P5 主线，但需记录）：概览仪表板、AI 资产增强（风险/对账/生命周期/业务系统/三维度重要性）、配置中心、数据源管理、合规、行为画像。这些在 08-16 文档里属"P3 AI 资产增强 / 未启动"，但当前代码已大量实现。

---

## 1. 总览对照表

| 阶段 | 目标 | 文档自述（历史报告） | 代码级核验结论 | 关键证据（file:line / 目录） | 主要缺口 / 风险 |
|---|---|---|---|---|---|
| **P0** | 告警降噪聚合 | ✅ 已完成（08-16） | ✅ 完成且**已扩张为告警治理子系统** | `alert_query.py:483 get_alert_groups`；`api/alert_digests.py` 路由 `/groups` `/groups/trend` `/groups/triage-top` `/snapshot/generate` `/groups/{fp}/create-incident`；`alert_group_snapshot_service.py` `alert_group_triage_service.py` `alert_group_snapshot_scheduler.py` | 个警 AI 研判覆盖极低（08-16 盘点：仅 1 条）；真实簇数需运行时确认 |
| **P1** | 告警-资产自动关联 | ✅ 已完成（08-16） | ✅ 关联逻辑存活且强化 | `asset_enrichment.py:24-32` 按 `wazuh_agent_id` 取资产；`models/asset.py` 含 `wazuh_agent_id`；多模块引用 | 无重大缺口 |
| **P2** | AI 研判 | ✅ 落库完成（08-16）；"上网行为"判 95%（菜单缺口） | ✅ AI 研判能力大幅扩张；**上网行为功能完整但导航挂载待确认** | `ai_agent.py`(PI Agent SSE) `ai_providers.py`(多模型) `ai_analysis.py` `mcp/tools/alert_tools.py`(ai_analyze_alert)；`browsing.py` + `views/browsing/` 5 页 | ①个警研判覆盖低 ②**上网行为菜单**：`scripts/` 已无 `init_browsing_menu`，需运行时确认是否已挂菜单 |
| **P3** | 事件闭环 | ✅ 已完成（08-16） | ✅ 完好，且新增影响面分析/告警建事件链路 | `api/incidents.py` `alert_incident_service.py` `impact_analysis.py` `alert_digests.py:152 create-incident` `views/incidents/` | **闭环率极低**（08-16：~8%，仅 1 closed/13）——系统能力在，流程/人未转起来，指向 P5 SOAR |
| **P4** | 脆弱性管理 + 数据可靠性 | 脆弱性 ✅（08-16）；数据可靠性 08-16 判"未启动"、08-22 判"✅完成"、用户记忆写"WO-2 返工中" | ✅ **脆弱性大幅实现**；✅ **数据可靠性 WO-2 返工确已落地**（用户记忆已过时） | `api/vulnerabilities.py` `views/vulnerability/` `sca.py` `scan_tasks.py` `wazuh_sca_sync*.py`；`record_failure` 现存在于 `asset_sync_handler.py`(4处) `wazuh_agent_sync.py`(5处) `source_health.py` `asset_sync.py`(6处) | ①`ENCRYPTION_KEY` 非法 Fernet 密钥——08-16 列 P0 级阻断，需确认是否已修 ②资产纳管率仅 ~30%（08-16：22/74），数据可靠性根因 |
| **P5** | 威胁情报 / SOAR / 知识库 | ⏳ 未启动（08-16） | 🟡 **知识库 + 资产知识图谱已实装**；🟡 威胁情报仅部分；❌ **SOAR 完全空白** | **知识库**：`api/knowledge.py`(NL搜索+GLM rerank/增删改/验证/从事件提取) `knowledge_service.py` `views/knowledge/` `api/__init__.py:153` 已注册 `/knowledge`；**知识图谱**：`api/graph.py`(N跳邻居/最短攻击路径/影响面/漏洞阻塞点/人工关系/重建边) `services/graph/builders.py` `query.py`；**威胁情报**：仅 `browsing_detection/threat_intel.py` + `scripts/sync_threat_intel.py`；**SOAR**：无 playbook/soar/misp/opencti 代码 | SOAR 完全未启动（直接拖累 P3 闭环率）；SOC 级情报平台（MISP/OpenCTI）未接入；知识库需确认数据填充与检索效果 |

---

## 2. 逐阶段核验记录

### P0 告警降噪聚合 — ✅ 完成（且已扩张）
- **验收标准**：海量原始告警按指纹（`rule_id|agent_id`）聚成告警簇，降噪并可回溯。
- **文档自述**：08-16 核查报告实测 `GET /api/v1/alerts/groups` 返回 `total_groups=31`，快照表 `soc_alert_groups` 1462 行。
- **代码核验**：接口已从 `alerts.py` 演进到独立的 `alert_digests.py` 告警治理子系统（含趋势、快照、Triage Top、建事件）。能力**未退化、已增强**。
- **证据**：`alert_query.py:483 get_alert_groups`；`alert_digests.py:24/42/59/72/85/103` 等路由；`alert_group_triage_service.py` `alert_group_snapshot_scheduler.py`。
- **缺口**：单告警 AI 研判覆盖极低（08-16 盘点仅 1 条），属"能力在、没用起来"。

### P1 告警-资产自动关联 — ✅ 完成
- **验收标准**：告警按 `agent.id → asset.wazuh_agent_id` 查询期自动关联。
- **文档自述**：08-16 报告 `alert_query._find_asset` 关联，返回 `linked_asset.asset_id`。
- **代码核验**：原函数名已重构进 `asset_enrichment.py`，但 `wazuh_agent_id` 关联链路完整存活并强化（资产富集、风险、同步多处引用）。
- **证据**：`asset_enrichment.py:24-32,65`；`models/asset.py` 字段；`asset_sync_handler.py` 同步时回填。
- **缺口**：无。

### P2 AI 研判 — ✅ 完成（能力扩张）；⚠️ 上网行为导航待确认
- **验收标准**：AI 对告警/告警簇研判并落库；多模型可切换。
- **文档自述**：08-16 报告 `AIAnalysisService.analyze_alert` 写 `soc_ai_analyses`，群体研判 37→39 行；"上网行为检测"判 95%（仅缺菜单挂载）。
- **代码核验**：AI 层大幅扩张——`ai_agent.py`(PI Agent JSON-RPC SSE)、`ai_providers.py`(多模型独立管理+场景路由+回落)、`ai_feedback.py`、`reconcile_ai.py`、`compliance_ai.py`、`behavior_profile/ai_summary.py`。研判落库与 `mcp ai_analyze_alert` 均在。
- **证据**：上述模块；`mcp/tools/alert_tools.py` 含 `ai_analyze_alert`。
- **缺口**：①个警研判覆盖低；②**上网行为菜单**：当前 `scripts/` 已无 `init_browsing_menu.py`，08-16 报告称其为"差最后一公里"的菜单挂载缺口——**是否已在某次提交中补菜单需运行时确认**（页面 `views/browsing/` 5 页存在，但后端驱动菜单若未插记录则 UI 不可见）。

### P3 事件闭环 — ✅ 完成（系统能力在，运营未转）
- **验收标准**：告警→事件→时间线→状态流转（open→in_progress→resolved→closed）闭环。
- **文档自述**：08-16 报告 `incidents.py` 全 CRUD + 前端状态流转 + 13 条数据 + 菜单挂载。
- **代码核验**：完好，并新增 `impact_analysis.py`(影响面分析)、`alert_digests.py:152` 告警簇一键建事件。
- **证据**：`api/incidents.py` `alert_incident_service.py` `impact_analysis.py` `views/incidents/`。
- **缺口**：闭环率 ~8%（08-16 盘点），瓶颈在流程/人，系统侧已就绪——**这是 P5 SOAR 的核心驱动理由**。

### P4 脆弱性管理 + 数据可靠性 — ✅ 完成（含 WO-2 返工）
- **验收标准**：漏洞落库可管理；任意采集源（wazuh/tplink/opensearch）中断→标红+推送。
- **文档自述矛盾链**：
  - 08-16 路线图盘点：脆弱性归 P1（✅）；数据可靠性(P4)判 **⏳ 未启动**。
  - 08-22 P4 验收报告：WO-1~WO-5 全部通过、WO-2 复验通过，**P4 ✅ 完成**。
  - 用户记忆（近期）："**P4 数据可靠性部分完成（WO-2 返工中）**"——**此记忆已过时**。
- **代码核验（独立）**：
  - 脆弱性：大幅实现，`api/vulnerabilities.py` `views/vulnerability/` `sca.py` `scan_tasks.py` `wazuh_sca_sync*.py` + `docs/design/v1.0-脆弱性管理/` 全套文档。
  - 数据可靠性 WO-2：`record_failure` 现确实存在于 `asset_sync_handler.py`(4)、`wazuh_agent_sync.py`(5)、`source_health.py`(2)、`asset_sync.py`(6)——**返工已落地，与 08-22 复验结论一致**。用户记忆的"返工中"是旧状态残留。
- **缺口**：①`ENCRYPTION_KEY` 是否仍为非法 Fernet 密钥（08-16 列 P0 级生产阻断）需确认；②资产纳管率 ~30% 是数据可靠性的根因敞口。

### P5 威胁情报 / SOAR / 知识库 — 🟡 知识库+图谱已启动；❌ SOAR 空白
- **验收标准**：情报 feed 接入；SOAR 自动处置；知识库可检索。
- **文档自述**：08-16 路线图盘点判 **⏳ 未启动**。
- **代码核验（重大更新）**：
  - **知识库 ✅ 已实装且真实可用**：`api/knowledge.py` 提供 NL 搜索（召回+GLM rerank）、列表、增删改、人工验证、从已解决事件批量提取；`knowledge_service.py`；前端 `views/knowledge/`；`api/__init__.py:153` 已挂 `/knowledge`。非空壳。
  - **资产知识图谱 ✅ 已实装**：`api/graph.py` 含 N 跳邻居、最短攻击路径、影响面分析、漏洞阻塞点、人工登记关系、重建边；`services/graph/builders.py` `query.py`。正是此前讨论的"KG 赋能安全运营"落地。
  - **威胁情报 🟡 仅部分**：仅 `browsing_detection/threat_intel.py`（上网黑名单用）+ `scripts/sync_threat_intel.py`；**无 SOC 级情报平台（MISP/OpenCTI 未接入）**。
  - **SOAR ❌ 完全空白**：全局无 playbook/soar/misp/opencti 代码；事件处置仍纯人工。
- **缺口**：SOAR 是 P5 最大空白，直接拖累 P3 闭环率；情报平台未建；知识库需确认检索效果与数据填充。

---

## 3. 文档自述 vs 代码核验 —— 重大出入（诚实留痕）

| # | 出入点 | 文档/记忆怎么说 | 代码实测 | 结论 |
|---|---|---|---|---|
| 1 | WO-2 返工状态 | 用户记忆："WO-2 返工中" | `record_failure` 已存在于 asset_sync_handler/wazuh_agent_sync 等多处 | **记忆过时**——08-22 已复验通过 |
| 2 | P4 数据可靠性启动时点 | 08-16 盘点："未启动"；用户记忆："部分完成" | 08-22 验收完成 + 代码已落地 | 以 08-22 + 代码为准，**P4 已完成** |
| 3 | P5 是否启动 | 08-16 盘点："未启动" | `knowledge.py` + `graph.py` 已实装并注册 | **P5 知识库/知识图谱已启动**，自述过时 |
| 4 | 上网行为菜单缺口 | 08-16：仅缺菜单挂载（差最后一公里） | 当前 `scripts/` 无 `init_browsing_menu`；需运行时确认 | **状态待运行时核实**（页面存在，菜单未知） |
| 5 | 关键函数名 | 08-16 报告引 `alert_query.get_alert_groups()`、`_find_asset()` | 函数仍在但 `_find_asset` 重构进 `asset_enrichment.py`；groups 接口迁至 `alert_digests.py` | 能力存活+扩张，仅命名/位置变化 |

> 第 1–3 条说明：**历史报告与用户记忆均已落后于当前代码**，本次以代码实测为准。第 4 条是唯一需运行时（连库/起服务）才能彻底关闭的项。

---

## 4. 结论与建议下一步

**总体判定**：P0–P4 主线能力**均已落地且普遍超出 08 月报告描述**；P5 中**知识库 + 资产知识图谱已实装（超预期）**，但 **SOAR 与 SOC 级威胁情报平台仍是空白**。

**建议优先级**（与 08-16"先治地基→差异化→规模化"原则一致，但需更新）：

1. 🔴 **关闭 P5 SOAR 空白**：当前事件闭环率 ~8% 的根因是"无自动处置"。哪怕先做最小 playbook（隔离/封禁前的下游影响 BFS 判定），也能直接拉升 P3 闭环率。这是 ROI 最高的一项。
2. 🔴 **确认并修复 `ENCRYPTION_KEY`**：若仍非法 Fernet 密钥，属生产阻断（重启丢加密数据），优先级最高。
3. 🟡 **提升资产纳管率（~30%→目标）**：数据可靠性的根因敞口，影响所有依赖资产关联的能力（P1/P3/知识图谱）。
4. 🟡 **补齐 P2 上网行为菜单挂载**：若运行时确认仍缺失，执行菜单种子脚本即可闭合（极低成本）。
5. 🟢 **激活已建能力**：个警 AI 研判（仅 1 条）、知识库检索效果、图谱 attack-path 的运营使用——"建好但没用起来"是当前主要浪费。

---

## 5. 核验方法与可信度声明

- 本次为**静态代码级核验**：`git log`（最近 40 提交）、目录枚举（`api/`、`views/`）、函数/接口级 grep（`record_failure`、`get_alert_groups`、`wazuh_agent_id`、`knowledge`、`soar`/`misp`/`opencti` 等）。
- **未跑运行时**：告警真实簇数、菜单挂载状态、知识库检索效果、ENCRYPTION_KEY 合法性需连库/起服务后二次确认（已在缺口中标注）。
- 历史报告（08-16 P0-P2 核查、08-22 P4 验收）本身已含独立核验，本次在其基础上复验并发现其结论已落后于 9 月代码演进。
