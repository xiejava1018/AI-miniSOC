# 告警治理（Alert Governance）详细设计方案与实施计划

> 版本：v0.1 · 日期：2026-08-09 · 作者：AI-miniSOC 建设讨论
> 目标：把"百万条原始告警"收敛为"少量可处理的告警簇 + AI 研判 + 每日摘要"，让系统从"SIEM 外壳"变成"会替你挑重点的 AI-SOC"。

---

## 9.5 实现记录（Phase 0 已落地，2026-08-09）

Phase 0（聚合+摘要+查询地基）已完整实现并**在真实数据上端到端验证通过**：

- **新增/改动文件**
  - `services/alert_query.py`：新增 `get_alert_groups()`（OpenSearch `composite` 聚合，按 `rule.id|agent.id` 分桶）、`get_alert_group_detail()`（单簇明细+样本+`data.srcip` 源 IP+资产关联）、`data.srcip` 做成尽力而为（已验证该字段可用，自动降级以防映射差异）。
  - `models/alert_digest.py`：新增 `soc_alert_digests` 表（JSONB 存 by_level/top_groups/top_assets/trend）。
  - `services/alert_digest_service.py`：组合聚合+资产关联+模板摘要，`Base.metadata.create_all` 建表（避开失效 Alembic）。
  - `api/alert_digests.py` + `api/__init__.py`：REST `GET /alerts/groups`、`GET /alerts/groups/{fingerprint}`、`POST /alerts/digest/generate`、`GET /alerts/digest/latest`、`GET /alerts/digest?date=`。
  - `mcp/tools/alert_tools.py`：MCP 工具 `list_alert_groups` / `get_alert_group` / `get_alert_digest`（包一层 REST）。
- **实现偏差（相对原设计）**
  - 指纹用**可逆自然键** `f"{rule_id}|{agent_id}"`（非 md5 哈希），便于单簇查询解析；簇级研判缓存后续可用 `grp:<fingerprint>` 落 `soc_ai_analyses`。
  - 路由顺序坑：`/alerts/groups` 曾被 `alerts.py` 的 catch-all `GET /{alert_id}` 抢匹配，已将 `alert_digests` 路由**在 alerts 之前注册**修复。
- **验证结果（真实数据）**：24h 共 5176 条告警，归并为 **45 个告警簇**；Top 簇 `rule 31120 Web 500错误 @ aliCloudECS ×1016`；详情正确关联资产并列出 141 个不同攻击源 IP；摘要生成成功。MCP 工具随后端重启（30 个工具）已注册，用户侧连接器重连后即可直接调用。

---

## 0. 现状盘点（基于代码事实）

### 0.1 已具备、可直接复用的能力（"积木"）
| 能力 | 位置 | 说明 |
|---|---|---|
| 告警列表 / 详情 / 按 IP 查询 | `services/alert_query.py::AlertQueryService` | 直连 OpenSearch `wazuh-alerts-4.x-*` |
| **告警统计聚合** | `get_alert_statistics()` | `by_level` / `by_agent` / `by_description` Terms 聚合 |
| **告警趋势** | `get_alert_trend()` | `date_histogram` + 高危子聚合 |
| **Top 告警资产** | `get_top_alert_assets()` | 按 `agent.ip` 聚合 + 高危数 + 最后告警时间 |
| **单条告警 AI 研判** | `services/ai_analysis.py::AIAnalysisService.analyze_alert()` | Agent→智谱降级，结构化输出，带缓存+指纹 |
| **AI 分析落库表** | `models/ai_analysis.py::soc_ai_analyses` | 已有 `alert_fingerprint` 字段 |
| **通知 + WS 实时推送** | `services/notification_service.py` + `ws_manager` | `NotificationService.create()` 单一入口 |
| **后台调度范式** | `services/browsing_detection/scheduler.py` | `start/stop` 幂等 + lifespan 启停 + `create_all` 建表 |
| **资产关联字段** | `models/asset.py::soc_assets` | `asset_ip` + `wazuh_agent_id`（可做 IP→资产映射） |
| REST 路由骨架 | `api/alerts.py` | 已含 `/statistics` `/trend` `/top-assets`，及 `/{alert_id}/create-incident` 空 stub |
| MCP 调用范式 | `mcp/tools/base.py::call_api` | 工具包一层 REST，自动注入 Token、解开 `{code,data}` |

### 0.2 缺失的环节（要补的"编排层"）
1. **告警指纹 / 去重组**：没有把 103 万条原始告警按"同规则+同资产+同源"合并成有限个簇的概念。现有统计只是维度计数，不是"可点开处理的事件簇"。
2. **每日/周期摘要实体**：没有把聚合结果固化成可查询的"摘要"记录（只有实时统计，无历史）。
3. **簇级 AI 研判**：现有 AI 只解释"单条告警"；缺少对"一个告警簇（N 条同类）"做优先级/噪声/处置建议的研判。
4. **定时调度**：后端没有针对告警的定时任务（browsing 有，告警没有）。
5. **MCP 可查询入口**：缺 `list_alert_groups` / `get_alert_digest` / `ai_triage_alert_group` 这类让 Agent/用户一句问出"今天最该处理什么"的工具。
6. **噪声抑制**：无规则/指纹级抑制名单，无法把已知良性噪声排除出"必处理"清单。

---

## 1. 目标与原则

**核心目标**：将告警量从"百万级原始"降维到"每日 ≤20 个可处理簇"，每个簇带 AI 优先级、是否噪声、关联资产、建议动作。

**前期原则（用户强调"先把前期工作做好"）**：
- **地基优先、AI 后置**：Phase 0 先把"聚合 + 摘要 + 查询"做扎实——**此时完全不调 AI，也能显著提效**（人/ Agent 能直接看到"过去24h 有哪些告警簇、各多少条、涉及哪些资产"）。
- **复用优先于新建**：严格复用 `AlertQueryService`、`browsing_detection/scheduler` 范式、`NotificationService`、`soc_ai_analyses` 缓存，不另起炉灶。
- **先无界面、后轻界面**：v0 以 MCP + 通知 + WS 为主通道，重前端延后（与"前期工作"一致）。
- **成本可控**：AI 只研判 TopN 簇（默认 ≤20/天），非全量。

---

## 2. 总体架构

```
┌──────────────────────────────────────────────────────────────────┐
│  OpenSearch: wazuh-alerts-4.x-* (百万级原始告警)                    │
└───────────────────────────┬──────────────────────────────────────┘
                            │  composite agg (按指纹分桶)
                            ▼
              AlertQueryService.get_alert_groups()   ← 新增
                            │  {fingerprint,count,level分布,首末出现,样本告警}
                            ▼
        ┌───────────────────────────────────────────────┐
        │  AlertDigestService.generate(hours)             │  ← 新增
        │   · 聚合簇 + Top资产 + 趋势 + 统计              │
        │   · [Phase1] 对 TopN 簇调 AI 簇级研判           │
        │   · 组装 digest JSON                            │
        └───────┬───────────────────────┬─────────────────┘
                │ 落库                   │ 推送
                ▼                        ▼
        soc_alert_digests         NotificationService.create()
        (新表)                    + ws_manager.send_to_user()
                │                        │
                ▼                        ▼
        REST /alerts/digest/*    →  前端红点 / Agent 询问
                │
                ▼
        MCP: get_alert_digest / list_alert_groups / ai_triage_alert_group
                │
   [Phase2] 定时：alert_digest/scheduler.py (lifespan 启停, 每日 08:00)
```

---

## 3. 数据模型与接口设计

### 3.1 新增表 `soc_alert_digests`（摘要落库，便于历史查询）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| period_type | String(10) | `daily` / `weekly` |
| period_start / period_end | DateTime | 统计窗口 |
| total_alerts | Integer | 窗口内原始告警总数 |
| by_level | JSONB | 等级分布 |
| top_groups | JSONB | Top 簇列表（见 3.3） |
| top_assets | JSONB | 高频资产（含关联资产名/重要度） |
| trend | JSONB | 时间序列 |
| summary_text | Text | 自然语言摘要（Phase1 由 AI 生成，Phase0 由模板生成） |
| ai_model | String | 生成摘要用的模型（Phase0 为 `template`） |
| created_at | DateTime | |

建表方式：复用 browsing 的 `Base.metadata.create_all(bind=engine, tables=[...])`（`checkfirst` 幂等），**不依赖 Alembic**（当前 Alembic 版本引用已失效，见 §7）。

### 3.2 簇级 AI 研判的落库（复用 `soc_ai_analyses`）

为不新建表，`soc_ai_analyses.alert_id` 存 **`grp:<fingerprint>`**（其 `unique=True` 约束天然保证每簇一条），`alert_fingerprint` 存指纹，`explanation/risk_assessment/recommendations` 存簇级研判。
- 取舍：复用省一张表，但语义上 `alert_id` 混用了 alert 与 group。MVP 可接受；若后续多源研判增多，再抽 `soc_ai_analyses` 加 `source` 列或独立 `soc_alert_group_analyses`。

### 3.3 `top_groups` 中单个簇的结构（JSONB）
```json
{
  "fingerprint": "r:1002|a:001|s:8.8.8.8",
  "rule_id": 1002,
  "rule_description": "SSH brute force attempt",
  "level_min": 5, "level_max": 10,
  "count": 1823,
  "first_seen": "2026-08-08T00:12:00Z",
  "last_seen":  "2026-08-09T07:55:00Z",
  "distinct_assets": 3,
  "linked_assets": [                       // IP→资产关联结果
    {"ip":"192.168.0.5","asset_id":"...","name":"web-01","criticality":"high"}
  ],
  "sample_alert_id": "abc123",
  "ai_priority": "P1",                      // Phase1 填充
  "ai_is_noise": false,
  "ai_rationale": "...",
  "ai_action": "封禁源IP / 检查失败登录",
  "suggest_incident": true
}
```

### 3.4 新增 REST 端点（挂在 `api/alerts.py` 或新建 `api/alert_digests.py`）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/alerts/groups` | 分桶聚合结果，支持 `hours`/`min_count`/`level`/`skip`/`limit` |
| GET | `/api/v1/alerts/groups/{fingerprint}` | 单簇明细 + 样本日志 + 关联资产 |
| POST | `/api/v1/alerts/digest/generate` | 手动触发生成（立即返回 digest） |
| GET | `/api/v1/alerts/digest/latest` | 最近一条摘要 |
| GET | `/api/v1/alerts/digest?date=YYYY-MM-DD` | 按日期取摘要 |
| POST | `/api/v1/alerts/groups/{fingerprint}/triage` | 触发簇级 AI 研判（Phase1） |

### 3.5 新增 MCP 工具（包一层上面的 REST）
| 工具 | 对应 REST | 价值 |
|---|---|---|
| `list_alert_groups(hours, min_count, level)` | `/alerts/groups` | "过去24h 有哪些告警簇？" |
| `get_alert_group(fingerprint, hours)` | `/alerts/groups/{fp}` | "这个簇具体是什么、影响谁？" |
| `get_alert_digest(date?)` | `/alerts/digest/latest` | "今天最该处理什么？" |
| `ai_triage_alert_group(fingerprint, hours, force_refresh)` | `/groups/{fp}/triage` | "这一簇要不要管、怎么管？" |

---

## 4. 核心算法：告警指纹与去重聚合

**指纹定义**（在 OpenSearch 用 `composite` 聚合一次算完，避免拉全量）：
```
fingerprint = hash( rule.id + "|" + agent.id + "|" + src_ip )
```
- `rule.id`：同类威胁；`agent.id`：受影响资产（Wazuh 主机）；`src_ip`：攻击源（从 `data.srcip` / `full_log` 解析，缺失则置 `0`）。
- 用 OpenSearch `composite` aggregation 的 `after_key` 做**深度分页**，天然支持百万级且不触发 1 万条上限（现有 `Loki` 才有 1 万限制，OpenSearch 用 `composite` 不受此限）。

**聚合返回**：每桶 = 一个簇：`doc_count`、首/末 `@timestamp`（`min`/`max`）、`rule.level` 的 `min`/`max`、样本 `_id`（取 `top_hits` size=1）。

**噪声抑制（Phase2）**：
- 阈值过滤：`min_count`（默认如 5）以下不进"必处理"。
- 抑制名单：`soc_system_config` 键 `alert_digest.suppress_rule_ids`（如已知良性扫描规则），命中的簇标 `ai_is_noise=true` 并移出 Top 必处理。

---

## 5. AI 簇级研判设计（Phase1 的核心跃迁）

从"解释 1 条告警"升级为"对 1 个告警簇下研判结论"。

**输入（group_signature）**：`rule_id`/`rule_description`/`level_min/max`/`count`/`first_seen`/`last_seen`/`distinct_assets`(含 criticality)/`sample_full_log`。

**输出（JSON）**：
```json
{
  "priority": "P0|P1|P2|P3",
  "is_noise": true|false,
  "confidence": 0.0-1.0,
  "rationale": "为什么是这个优先级",
  "recommended_action": "具体处置步骤",
  "suggest_incident": true|false
}
```

**Prompt 与降级**：复用 `AIAnalysisService` 的 Agent→智谱降级路径；新增 `_build_group_triage_prompt()`，强调"这是 N 条同类告警的聚合，请综合量级、等级跨度、受影响资产重要度给优先级"。

**缓存与成本**：按 `grp:<fingerprint>` + 7 天过期缓存（同 `soc_ai_analyses.expires_at` 机制）。每日仅对 TopN（≤20）簇研判，智谱 `glm-4-flash` 成本可忽略。

---

## 6. 分阶段实施计划

> 每阶段可独立交付、独立验收；Phase 0 不依赖任何 AI 配额即可见效。

### Phase 0 —— 聚合 + 摘要 + 查询地基（无 AI，先让"看得见"）
- [ ] **P0.1** `AlertQueryService.get_alert_groups(hours, min_count, level, after_key)`：OpenSearch `composite` 聚合实现指纹分桶，返回簇列表（含分页 `after_key`）。
- [ ] **P0.2** REST `GET /alerts/groups` + `GET /alerts/groups/{fingerprint}`（后者调 `get_alert_by_id` 取样本 + 查 `soc_assets` 做 IP→资产关联）。
- [ ] **P0.3** `models/.../alert_digest.py` 建 `AlertDigest` 模型；`services/alert_digest_service.py::AlertDigestService.generate(hours)` 组合 `get_alert_groups`+`get_top_alert_assets`+`get_alert_trend`+`get_alert_statistics` 产出 digest（Phase0 用模板生成 `summary_text`）；`create_all` 建表。
- [ ] **P0.4** REST `POST /alerts/digest/generate` + `GET /alerts/digest/latest` + `GET /alerts/digest?date=`。
- [ ] **P0.5** MCP `list_alert_groups` + `get_alert_digest` + `get_alert_group`。
- ✅ **验收**：Agent 一句"过去 24h 有哪些告警簇、各多少条、涉及哪些资产"能直接答出；可手动生成摘要。

### Phase 1 —— AI 簇级研判（真正的"AI-SOC"跃迁）
> 详细设计见 **§11**。一句话：在 Phase0/A/B 积累的"告警簇"之上，对每个簇做一次**结构化 AI 研判**（优先级 P0–P3 / 是否噪声 / 置信度 / 理由 / 处置动作 / 是否建事件），缓存并重用，让"今天最该处理什么"由 AI 自动排好队。
- [ ] **P1.1** 新增 `soc_alert_group_analyses` 表 + `AlertGroupAnalysis` 模型（按 `fingerprint` 唯一缓存，7 天 TTL）。
- [ ] **P1.2** `AIAnalysisService.triage_alert_group(signature)`：新增簇级 prompt，复用 Agent→智谱降级链与 JSON 解析，落 `soc_alert_group_analyses`；AI 不可用时降级为**启发式 verdict**（不阻塞主流程）。
- [ ] **P1.3** 新增 `AlertGroupTriageService.triage_top_groups(hours, top_n=20)`：聚合 TopN 簇→逐个研判→按优先级/数量排序，返回"今日必处理"清单。
- [ ] **P1.4** `AlertDigestService` 升级：生成摘要时对 TopN 簇调 `triage_top_groups`，把 `ai_*` 字段写回 `top_groups`，`summary_text` 改为 AI 综述；`ai_model` 写实模型名。
- [ ] **P1.5** 历史快照增强（增量）：快照时为每簇回填最新 AI verdict（`soc_alert_groups` 加 `ai_priority/ai_is_noise/ai_suggest_incident/ai_verdict_at`），历史页与趋势图可显示 AI 结论且不额外消耗 AI 配额。
- [ ] **P1.6** REST：`POST /alerts/groups/{fp}/triage`（单簇研判）、`GET /alerts/groups/{fp}/triage`（取缓存）、`GET /alerts/groups/triage-top`（批量"必处理"清单）。
- [ ] **P1.7** MCP：`ai_triage_alert_group(fp,hours,force_refresh)` + `list_alert_triage_top(hours,top_n)`；`get_alert_digest` 已天然含 AI 字段。
- [ ] **P1.8** 前端：实时页加"AI 研判"列（优先级徽标 + 噪声标签）+ 详情抽屉加 AI 研判块（理由/动作/建事件）；摘要面板展示 AI 综述。
- ✅ **验收**："今天最该处理的 Top5"每条带 AI 优先级 + 理由 + 动作 + 是否噪声；单簇可手动触发研判；离线（无 AI 配额）时仍有启发式 verdict 兜底，不影响界面与 MCP。

### Phase 2 —— 定时调度 + 通知闭环（自动化）— ✅ 已完成（2026-08-13）
- [x] **P2.1** 新建调度器（**实现偏差**：放 `services/alert_digest_scheduler.py` 而非子目录，与 `alert_group_snapshot_scheduler.py` 并列，风格统一）。严格复用 snapshot scheduler 范式：`start/stop` 幂等、`run_digest_once()` 可手动触发、受进程级 `ALERT_DIGEST_SCHEDULER_ENABLED` + `ALERT_DIGEST_SCHEDULER_HOUR`（默认 8）控制、每日定点（计算到下一个目标整点的秒数 sleep）；在 `main.py` lifespan 与其余后台任务并列启停。
- [x] **P2.2** `AlertDigestService.generate()` 末尾调用 `NotificationService.create(type="alert_digest", ...)` 向 admin/超管（`is_superuser` 或 `role.code='admin'` 且 active）推送站内通知 + WS，失败不阻断主流程。
- [x] **P2.3** 噪声抑制（**实现偏差**：配置 category 用 `alert_governance`、键名 `suppress_rule_ids` / `min_group_count`，与 `triage_top_n` 同类统一管理）。`alert_governance_config` 扩展为多键缓存（首次读取自动建全 3 项默认行）+ `filter_noise_groups()` 统一过滤；digest 降级分支与 triage 研判前共用，研判前过滤省 AI 配额。
- ✅ **验收**：每日 08:00 自动产出摘要并推送；`run_digest_once` 手动触发链路已端到端验证（见 §10.6）。

### Phase 3 —— 事件交接 + 轻量 UI（收口闭环）— ✅ 已完成（2026-08-13）
- [x] **P3.1** 实现原空 stub `POST /alerts/{alert_id}/create-incident`（新增 `services/alert_incident_service.py::build_incident_from_alert`）+ 新增 `POST /alerts/groups/{fingerprint}/create-incident`（`build_incident_from_group`，优先用缓存 AI verdict 推导 severity）。顺带修复 pre-existing：`get_alert_by_id` 原只用 `_id` 查询、与 list 暴露的 `_source.id` 不一致导致长期 404，改为 `bool.should(term.id, ids._id)` 合并查询。
- [x] **P3.2** 轻量 UI（未做独立摘要页，选了更轻的形式）：告警簇下钻抽屉新增"事件处置"区 + "一键建事件 / 按 AI 建议建事件"按钮（文案随 `suggest_incident` 切换），成功后提示事件标题与 severity。
- ✅ **验收**：从"告警簇 / 单条告警 → 研判 → 建事件"全链路端到端打通（见 §10.7）。

---

## 7. 已知风险与前置确认

| 风险 | 影响 | 处理 |
|---|---|---|
| `ENCRYPTRY_KEY` 非合法 Fernet 密钥 | digest 若存敏感字段则重启丢失 | MVP digest 只存计数/元数据，不存密文；**生产前必修密钥**（独立任务） |
| OpenSearch `wazuh-alerts-*` 保留期未知 | 决定 digest 窗口上限（24–168h） | 实施 P0.1 前先查索引 ILM/保留策略确认 |
| `192.168.0.2` 路由器日志中断 | 该资产告警被低估 | 已知盲区，digest 中标注"数据可能不完整" |
| Alembic 版本引用失效 | 新表无法靠迁移建 | 复用 `create_all(checkfirst)`（同 browsing 模式），不碰 Alembic |
| AI 配额/网络 | Phase1 依赖智谱 | 已有降级链；Phase0 不依赖 |

---

## 8. 成功度量（Before → After）
- **Before**：人面对 1,030,000 条原始告警；AI 一次只能解释其中 1 条。
- **After（Phase0）**：一句话查到"过去 24h 共 12 个告警簇，Top3 是 X/Y/Z，分别 N 条，涉及资产 A/B/C"。
- **After（Phase1）**：每日摘要 Top5 每条带 AI 优先级（P0–P3）、是否噪声、关联资产、处置建议。
- **After（Phase2）**：每日 08:00 自动推送，无需人工触发。

---

## 9. 待确认事项（开工前）
1. **调度模式**：Phase2 是否每日自动运行（推荐 08:00），还是 v0 仅手动触发？
2. **UI 投入**：v0 是否只走 MCP + 通知（推荐，符合"前期工作"），前端摘要页放到 Phase3？
3. **AI 研判范围**：仅 TopN（≤20）簇（推荐，成本可控）还是全量？
4. **OpenSearch 保留期**：需先确认 `wazuh-alerts-*` 的 ILM 保留天数，以定 digest 默认窗口。

---

## 10. 实现记录（Phase 0 → Phase A 实时界面 → 方案 B 历史快照）

> 本文档随实现推进持续追加。所有端点均经端到端验证（自签 JWT / 真实 OpenSearch 数据）。

### 10.1 Phase 0（聚合 + 摘要 + 查询，无 AI）— 已完成
- `AlertQueryService.get_alert_groups()`：OpenSearch `composite` 按 `rule.id|agent.id` 分桶成"告警簇"。
- `get_alert_group_detail()`：单簇明细 + `data.srcip` 攻击源 IP + 按 IP 关联 `soc_assets`。
- `soc_alert_digests` 表 + `AlertDigestService`（`create_all` 建表，绕过失效 Alembic）。
- REST：`GET /alerts/groups`、`GET /alerts/groups/{fp}`、`POST /alerts/digest/generate`、`GET /alerts/digest/latest`、`GET /alerts/digest?date=`。
- MCP 工具：`list_alert_groups` / `get_alert_group` / `get_alert_digest`（后端现 30 个工具）。
- 验证：24h 5176+ 条 → 45 簇，Top 簇 `rule 31120 Web 500 ×1016`，资产关联正常。

### 10.2 Phase A（实时查询界面）— 已完成
- 用户决策：**先做实时界面（方案 A）挂"告警管理"下**，随后再补落库（方案 B）。
- 新增 `views/alert/governance/index.vue` + `api/alert.ts` 4 个函数 + 路由/别名 + **`soc_menus` 菜单记录（id=28，挂父菜单 id=4）**（后端菜单模式，必须加菜单记录否则侧边栏不显示）。
- 能力：统计卡 / 摘要面板 / 过滤栏 / 告警簇表格 / 单簇下钻抽屉。
- 关键认知：45 簇**未落库**，每次 OpenSearch 实时算；`soc_alert_digests` 仅存摘要快照（且只 Top20）。

### 10.3 方案 B（历史快照 + 趋势）— 已完成
- **对方案 A 的影响**：增量、向后兼容。A 的端点/页面不变；B 新增独立端点与一张表，互不干扰（实时永远新鲜，历史作次级视图）。
- 用户决策：**每 6 小时快照 + 加 ECharts 趋势图 + 实时优先**。
- 新增：
  - `soc_alert_groups` 表（`models/alert_group_snapshot.py`）：`snapshot_at`(索引)、`fingerprint`、`rule_*`、`agent_*`、`count`、`level_min/max`、`first/last_seen`、`distinct_srcips`、`top_srcips`(JSONB)、`linked_asset_id`(FK→soc_assets，按 agent_ip 关联)。
  - `AlertGroupSnapshotService`：`snapshot()`（全量簇 + 资产关联批量写）、`query_history(date/asset_ip/level)`、`get_trend(days)`（按快照日聚合 clusters/alerts/linked）、`cleanup_retention(90天)`。
  - REST：`GET /alerts/groups/history`、`GET /alerts/groups/trend?days=`、`POST /alerts/snapshot/generate`。
  - `alert_group_snapshot_scheduler.py`：lifespan 启停、每 **6h** 跑一次、启动 60s 后首跑（复用 `browsing_detection/scheduler.py` 范式）；`main.py` 已 start/stop。
  - 前端： governance 页加 **实时/历史 切换 Tab**，历史 Tab 含过滤 + **ECharts 趋势图** + 历史簇表格；实时优先。
- 路由顺序坑：`/alerts/groups/history` 与 `/alerts/groups/trend` 须注册在 `/alerts/groups/{fingerprint}` 之前，否则被 catch-all 抢匹配。
- 验证（重启后端新进程后）：
  - A 实时：`GET /alerts/groups` → 200（不受影响）
  - B 快照：`POST /alerts/snapshot/generate` → 33 簇落库，32 关联资产
  - B 历史：`GET /alerts/groups/history` → 返回快照，首条已关联资产
  - B 趋势：`GET /alerts/groups/trend?days=14` → `{date:'2026-08-09', clusters:33, alerts:2885, linked_assets:32}`
- 前端 `vue-tsc` 类型检查通过（仅 `login` 页有 pre-existing 报错，与本次无关）。

### 10.4 运维提示
- 后端进程重启会：① 切断 MCP SSE 长连接；② 清空 TokenManager 内存态凭据；③ 清空定时快照的"已跑状态"（调度在 lifespan 重启后重新启动，60s 后首跑）。
- 重启后端后：若用 MCP 工具，需重连 SSE + `set_mcp_credentials(admin/admin123)`；纯前端界面经 vite 代理 8000，后端起来即恢复。

### 10.5 Phase 1（AI 结构化研判 + 缓存 + 落库）— 已完成（2026-08-09）
用户 4 项决策：**① AI verdict 落独立表；② 历史页也显示 AI 结论（快照回填）；③ 默认研判 TopN=20 且可在系统配置 UI 修改；④ 无 AI 时启发式兜底对外标注 `source=heuristic`。**

落地内容：
- **独立缓存表** `soc_alert_group_analyses`（`models/alert_group_analysis.py`）：`fingerprint` 唯一索引 + 7 天 TTL（服务层写 `expires_at`）。`AlertGroupAnalysis` 已注册进 `models/__init__.py`。
- **三级降级链**（`services/ai_analysis.py::triage_alert_group`）：缓存 → Pi Agent（`manager.call`）→ 智谱 `glm-4-flash` → 启发式兜底（`source="heuristic"/model_name="heuristic"`）。ZhipuAI 客户端 `try/except` 容错初始化，缺密钥不阻断服务。
- **`AlertGroupTriageService.triage_top_groups`**（`top_n` 取自 `get_triage_top_n`，信号量=5，按 `PRIORITY_RANK` 再 `-count` 排序）+ `triage_one` + `get_cached_verdict`。
- **系统配置** `alert_governance.triage_top_n`（默认 "20"，`number`），`services/alert_governance_config.py` 60s 缓存 + 首次读自动建行；UI 系统配置页可改。
- **历史快照回填**：`soc_alert_groups` 加 4 列 `ai_priority/ai_is_noise/ai_suggest_incident/ai_verdict_at`，`AlertGroupSnapshotService.snapshot()` 零额外 AI 成本回填；`_ensure_schema()` 用 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 兜底（因 `create_all` 不给既有表加列）。
- **REST**（全部挂在 `/alerts` 前缀下）：`GET /alerts/groups/triage-top`、`GET/POST /alerts/groups/{fp}/triage`、`POST /alerts/digest/generate`（改 async，接入 `triage_top_groups` + AI 综述）、`POST /alerts/snapshot/generate`。路由顺序坑：`triage-top` 须在 `{fingerprint}` catch-all 前注册。
- **MCP**：新增 `list_alert_triage_top` / `ai_triage_alert_group`（后端现 **32** 个工具）。
- **前端**：`api/alert.ts` 加 3 函数 + `AlertGroupTriage` 类型；governance 页加「加载 AI 研判」按钮、实时/历史「AI 研判」列、下钻抽屉「AI 研判」块（优先级/置信度/噪声/建议建单/来源/模型/理由）+ 重新研判。

端到端验证（自签 JWT + httpx，全部 200）：
- `GET /alerts/system-configs/by-category/alert_governance` → 自动建行 `triage_top_n=20`（id=35）。
- `POST /alerts/groups/31120|008/triage` → verdict 落库；`GET .../triage` 命中缓存。
- `GET /alerts/groups/triage-top?top_n=10` → 10 簇，优先级 P2→P3 非降序排列 **True**。
- `POST /alerts/digest/generate?hours=24` → 200，top_groups=20 全部带 `ai_priority`，`ai_model=heuristic`，综述标注"AI 不可用，以下为启发式兜底研判"。
- `POST /alerts/snapshot/generate` → 200，`groups_snapshotted=33`，`ai_triaged=20`。
- `GET /alerts/groups/history` → 历史行回显 `ai_priority`。

**关于 `source=heuristic`**：本环境 `.env` 的 `GLM_API_KEY` 原为占位符 `your_glm_api_key_here`（调用返回 `401 令牌已过期或验证不正确`），Pi Agent 亦不可用，故全部簇研判走启发式兜底并如实标注 `source=heuristic`。降级链路本身正确、无报错。配置有效 `GLM_API_KEY`（或启用 Pi Agent）后**无需改代码**即自动切换为真实 AI verdict（`source=agent`/`zhipu`）。
- **2026-08-09 实测确认**：填入有效智谱密钥后，`force_refresh` 单簇与 `triage-top?force_refresh=true` 均返回 `source=zhipu` / `model_name=glm-4-flash`（如 `31101|008×946→P1`、`554|022×300→P1`），`digest/generate` 的 `ai_model=glm-4-flash`、`top_groups` 全为真实研判，快照回填 `ai_triaged=20`。真实 AI 路径完全打通。

---

## 10.6 Phase 2（定时调度 + 通知闭环 + 噪声抑制）— 已完成（2026-08-13）

Phase 2 三项一次性落地，补齐"每日自动产出摘要并推送"的自动化闭环。

**落地内容**
- **P2.3 噪声抑制（config 层）**：`alert_governance_config.py` 由单键缓存重构为整个 `alert_governance` category 的多键缓存（60s TTL）。新增 `get_min_group_count` / `get_suppress_rule_ids` 及 setter；首次读取任一项即 `_load_all()` 一次性补全 `triage_top_n`/`suppress_rule_ids`/`min_group_count` 三项默认行（系统配置界面立即可见可改）。新增统一 helper `filter_noise_groups(groups, db) -> (kept, suppressed_count)`。
- **P2.1 摘要自动调度器**：新建 `services/alert_digest_scheduler.py`，复用 `alert_group_snapshot_scheduler` 范式。`_seconds_until_next(hour)` 计算到下一个目标整点的秒数作为 sleep（错过则推到次日，不错过定点）；受 `ALERT_DIGEST_SCHEDULER_ENABLED`（默认 True）+ `ALERT_DIGEST_SCHEDULER_HOUR`（默认 8）进程级开关控制；`run_digest_once(hours)` 可手动触发；`main.py` lifespan 与 browsing/snapshot 并列启停。
- **P2.2 通知推送**：`AlertDigestService._push_notification(digest)` 在 `generate()` commit 后调用，查收件人（`is_superuser` 或 `role.code='admin'` 且 `status=active`）逐个 `NotificationService.create(type='alert_digest', title, content=summary[:500], link)`，WS 实时推送由 `NotificationService` 内部完成；`try/except` 包裹，失败只 warning 不阻断。
- **config.py**：新增 `ALERT_DIGEST_SCHEDULER_ENABLED: bool = True` / `ALERT_DIGEST_SCHEDULER_HOUR: int = 8`。
- **过滤接入点**：`AlertDigestService.generate()` 主路径走 `triage_top_groups`（内部已过滤），降级分支手动 `filter_noise_groups`；`AlertGroupTriageService.triage_top_groups()` 取簇后、研判前过滤（`get_min_group_count` 传给 `get_alert_groups(min_count=)`，suppress 命中的簇移除），省 AI 配额。

**端到端验证**（自签 admin JWT + httpx，全部通过）
1. `GET` 触发配置自动建行 → DB 出现 3 行：`triage_top_n=20/number`、`suppress_rule_ids=''/string`、`min_group_count=1/number`。
2. `POST /alerts/digest/generate?hours=24` → 200，`total_alerts=2360`、`groups=20`、`ai_model=glm-4-flash`（真实 AI），summary 首行"…已 AI 研判 Top20"。
3. 查 `soc_notifications` → 新增 `type=alert_digest` 通知 1 条，`user_id=1`（admin），title="告警治理日报已生成（2360 条 / 20 簇）"。
4. 写库设 `suppress_rule_ids='31120'` → 重启后端清缓存 → 重生成：**20 簇 → 19 簇，规则 31120 已移出必处理清单**（`✓ True`）→ 还原 suppress 为空。

**说明**
- `alert_governance` 配置 60s 缓存：系统配置 UI 改 suppress/min_count 后最长 60s 生效（与 `triage_top_n` 既有行为一致）。进程级开关（`ALERT_DIGEST_SCHEDULER_*`）改 `.env` 后需重启。
- 调度器每日定点跑：若启动时已过当日 08:00，则等到次日 08:00；急需可 `POST /alerts/digest/generate` 手动触发或调 `run_digest_once`。
- 摘要内部已含 AI 研判 + 通知推送，调度器只负责"定时触发"，不重复编排。

---

## 10.7 Phase 3（告警/簇 → 事件一键交接）— 已完成（2026-08-13）

打通"告警簇/单条告警 → AI 研判 → 一键建事件"的收口闭环。

**落地内容**
- **告警→事件转换服务** `services/alert_incident_service.py`（新建）：
  - `build_incident_from_alert(alert_id)`：单条告警 → 事件，severity 由 rule.level 推导（>=12 critical / >=9 high / >=6 medium / else low），按 agent.ip 关联 soc_assets。
  - `build_incident_from_group(fingerprint, hours)`：告警簇 → 事件，**优先用缓存 AI verdict**（priority P0-P3 → severity）推导 severity/description；无 verdict 时告警等级启发式。description 含簇指纹/规则/数量/首末出现/源 IP 数 + AI 研判理由/处置建议 + 样本日志。按 linked_asset 或 agent_ip 关联资产。
  - created_by 默认 "system"（告警 API 当前无鉴权，pre-existing），可由 body 覆盖。
- **REST**：`POST /alerts/{alert_id}/create-incident`（原空 stub 已实现）+ `POST /alerts/groups/{fingerprint}/create-incident`（新增，挂在 alert_digests.py，两层路径在 /groups/{fingerprint} catch-all 之后注册）。
- **修复 pre-existing bug**：`AlertQueryService.get_alert_by_id` 原只用 OpenSearch `_id` 查询，但 list/_normalize 对外暴露的 id 是 `_source.id`（Wazuh 逻辑 epoch id，如 `1786630604.1078547`），两者不一致 → `GET /alerts/{alert_id}`、MCP `get_alert_detail`、单条建事件长期 404。改为 `bool.should(term.id, ids._id)` 合并查询，两种 id 均可命中。
- **前端**：`api/alert.ts` 新增 `createIncidentFromGroup` / `createIncidentFromAlert` + `AlertIncident` 类型；`governance/index.vue` 单簇下钻抽屉新增"事件处置"区 + "一键建事件 / 按 AI 建议建事件"按钮（文案随 `triageVerdict.suggest_incident` 切换），成功后 ElMessage 提示事件标题与 severity。

**端到端验证**（自签 admin JWT + httpx，全绿）
- 簇→事件：`POST /alerts/groups/31101|008/create-incident` → 200，事件落库（severity=low，title "[告警簇] Web server 400 error code. ×939"），`soc_incidents` +1、`soc_asset_incidents` 关联 1、created_by=system。
- 单条→事件：`POST /alerts/1786630604.1078547/create-incident` → 200，事件落库（title "[告警] Web server 400 error code."，wazuh_alert_id 正确记录）。
- GET triage 端点恢复（修复调试中误删）：200。
- 前端 `vue-tsc`：governance/alert 无新增报错。

**说明**
- 单条/簇建事件均不触发新的 AI 调用（簇用缓存 verdict；无缓存则等级启发式）。如需 AI 结论，先点"研判"再"建事件"。
- `incidents.py` 通用 CRUD 的 `created_by` 仍为 pre-existing 未填（本次未改 incidents API，避免越界）；本服务建事件端点已正确填 created_by。

**补充：事件管理前端页（2026-08-13）**

建事件落地后，前端原"事件管理"为占位（`Incidents='/placeholder'`），界面上无处可查。补齐轻量事件管理页让闭环可见：
- **修复 pre-existing**：`GET /api/v1/incidents/` 原 500（`IncidentResponse.id:str` 与模型 `UUID` 不匹配，事件页从未用过未暴露）。按项目惯例（browsing/notification）改 `id/ai_analysis_id: UUID`，list/get/create/update 四端点全恢复。
- **前端**：新建 `api/incident.ts`（列表/详情/更新 + 状态·严重度选项与配色）+ `views/incident/index.vue`（筛选 + 表格 + 详情抽屉 + 状态流转 open→in_progress→resolved→closed + 处理说明）。路由别名 `Incidents='/incidents/list'`。
- **菜单**：激活占位菜单 id=21（`incident-list`，component `/placeholder`→`/incident/index`，挂父菜单"事件管理" id=3）。
- **闭环跳转**：告警治理页"一键建事件"成功后 `router.push` 跳事件列表。
- 验证：列表/详情/状态流转（open→in_progress）端到端 200；vue-tsc 零新增报错。
- 注：菜单持久化在 pinia/localStorage，需重新登录触发菜单树重拉后侧边栏才出现"事件管理 > 事件列表"。

---

## 11. Phase 1 详细设计：AI 簇级研判（AI Cluster Triage）

> 在 Phase0（聚合）/方案 A（实时）/方案 B（历史快照）已落地的基础上，Phase 1 补齐"**AI 对告警簇下研判结论**"这一真正的 AI-SOC 跃迁：把"一簇 N 条同类告警"当作一个整体，输出可排序、可解释的处置建议，而非逐条解释。

### 11.1 目标与验收标准
- **核心目标**：对每个告警簇输出结构化研判 `{priority, is_noise, confidence, rationale, recommended_action, suggest_incident}`，每日仅对 TopN（默认 ≤20）簇研判，成本可忽略。
- **离线不降级体验**：AI 配额/网络不可用时，自动降级为**启发式 verdict**（按 `level_max` 与 `count` 给 P 级），界面与 MCP 照常工作——延续"Phase0 不依赖 AI 也见效"的原则。
- **验收**：
  1. 调 `POST /alerts/digest/generate` 或读 `GET /alerts/digest` → 每条 Top 簇带 `ai_priority/P0-P3`、`ai_rationale`、`ai_action`、`ai_is_noise`、`ai_suggest_incident`，`ai_model` 为真实模型名。
  2. `POST /alerts/groups/{fp}/triage` 可对单簇触发/刷新研判；`GET /alerts/groups/{fp}/triage` 取缓存。
  3. `GET /alerts/groups/triage-top` 返回按优先级排序的"今日必处理"清单。
  4. MCP `list_alert_triage_top` / `ai_triage_alert_group` 可直接问答"今天最该处理什么 / 这一簇要不要管"。
  5. 前端实时页出现 AI 研判列与详情块；无 AI 时显示启发式徽标。

### 11.2 数据模型：`soc_alert_group_analyses`（新表）
**决策点 1（建议采用）**：**新建独立表**，而非复用 `soc_ai_analyses`（alert_id=`grp:<fp>`）。理由：`soc_ai_analyses` 字段（`explanation/risk_assessment/recommendations`）语义为单条告警，且 `alert_id` 已 `unique`；簇研判需要 `priority/is_noise/confidence/suggest_incident` 等结构化字段，塞进文本会丢失可查询性。独立表字段干净、可按 `fingerprint` 唯一缓存、可被实时页与历史快照 JOIN 复用。原 §3.2 已将此列为"后续干净选项"。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| fingerprint | String(255) **unique**, index | 簇指纹 `rule_id\|agent_id`，缓存主键 |
| rule_id / agent_id | String | 研判时的快照（审计用） |
| rule_description | Text | 研判时的规则描述快照 |
| priority | String(4) | `P0`/`P1`/`P2`/`P3` |
| is_noise | Boolean | 是否判定为噪声/良性 |
| confidence | Float(0–1) | 模型置信度 |
| rationale | Text | 研判理由（为什么这个优先级） |
| recommended_action | Text | 具体处置步骤 |
| suggest_incident | Boolean | 是否建议一键建事件（接 Phase3） |
| source | String(16) | `agent` / `zhipu` / `heuristic`（降级来源，便于排障） |
| model_name | String(50) | 实际模型（如 `glm-4-flash`） |
| window_hours | Integer | 该簇聚合窗口 |
| linked_asset_id | UUID FK→soc_assets, nullable | 便于按资产重要度筛选 |
| created_at | DateTime | |
| expires_at | DateTime | **7 天 TTL**（同 `soc_ai_analyses` 缓存机制） |

建表：`Base.metadata.create_all(bind=engine, tables=[AlertGroupAnalysis.__table__], checkfirst=True)`（复用 browsing/digest 范式，**不碰失效 Alembic**）。

### 11.3 核心算法：簇签名 → Prompt → 结构化输出 → 降级
**簇签名（group_signature）**（来自 `get_alert_groups` + `get_alert_group_detail` 已有字段）：
```
{ rule_id, rule_description, level_min, level_max,
  count, first_seen, last_seen,
  distinct_srcips, top_srcips[:5],
  agent_name, agent_ip,
  linked_asset:{name, criticality, owner},   # 资产重要度是优先级关键输入
  sample_full_log }                            # 取 group.sample.full_log 或 detail.samples[0].full_log
```

**Prompt 要点**（`AIAnalysisService._build_group_triage_prompt`）：明确"这是 N 条同类告警的聚合，不是单条"，要求综合 **量级/等级跨度/受影响资产重要度/攻击源多样性/时间持续性** 给结论，并以严格 JSON 返回：
```json
{ "priority":"P0|P1|P2|P3", "is_noise":true|false, "confidence":0.0,
  "rationale":"...", "recommended_action":"步骤1\n步骤2", "suggest_incident":true|false }
```
**降级链**（完全复用 `ai_analysis.py` 现有机制）：
1. 先查缓存 `soc_alert_group_analyses`（按 fingerprint，未过期直接返回）。
2. 优先 `manager.call(session_id, "agent.prompt", {sessionId, userMessage:prompt, model, trace_id})`（Pi Agent）。
3. 失败/超时 → `ZhipuAI.chat.completions`（`glm-4-flash`, `temperature=0.3`）。
4. **AI 全不可用** → 启发式兜底：`level_max>=12→P1`，`>=8→P2`，否则 `P2/P3`；`is_noise=False`；`source="heuristic"`；理由写明"模型不可用，按等级启发式"。

JSON 解析失败同样回退启发式，保证不抛错。

### 11.4 服务编排：`AlertGroupTriageService`
```python
class AlertGroupTriageService:
    def __init__(self, db): self.db = db
    async def triage_top_groups(self, hours=24, top_n=20, force_refresh=False) -> List[dict]:
        # 1. svc.get_alert_groups(hours, limit=top_n) 取 TopN 簇
        # 2. 对每个簇：若非 force_refresh 先查缓存；否则构造 signature（必要时调 get_alert_group_detail 取 srcip/asset/sample）
        # 3. 调 AIAnalysisService.triage_alert_group(signature)
        # 4. 合并 verdict 回簇 dict（ai_priority/ai_is_noise/ai_confidence/ai_rationale/ai_action/ai_suggest_incident）
        # 5. 按 priority(P0>P1>P2>P3) 再 count 排序返回
    def get_cached_verdict(self, fingerprint) -> Optional[dict]: ...
```
- `triage_alert_group` 实现位置：复用 `AIAnalysisService`（加 `triage_alert_group` + `_build_group_triage_prompt` + `_save_group_analysis` + `_get_cached_group_analysis`），AI 逻辑集中一处。

### 11.5 与摘要 / 快照 / 前端 / MCP 的集成
- **摘要（P1.4）**：`AlertDigestService.generate(hours)` 在拿 TopN 簇后调 `triage_top_groups` 写回 `ai_*` 字段；`summary_text` 改为由 verdicts 合成"今日必处理 Top5"综述（模板兜底）；`ai_model` 写实模型名（不再 `template`）。
- **快照（P1.5，增量）**：`AlertGroupSnapshotService.snapshot()` 落库时为每簇按 `fingerprint` 回填最新缓存 verdict，并写入新增列 `ai_priority/ai_is_noise/ai_suggest_incident/ai_verdict_at`。**不重新调 AI**（零额外配额）。历史页与趋势图因此可展示 AI 结论；趋势图可加"P0/P1 簇数"系列。
- **前端（P1.8）**：实时页集群表格加"AI 研判"列（优先级 `ElTag` 配色 + 噪声标记）；详情抽屉加"AI 研判"块（理由/动作/`一键建事件`按钮，建事件接 Phase3）；摘要面板已显示 `summary_text`（现含 AI 综述）。历史页同理显示回填列。

### 11.6 REST + MCP 接口设计
**REST（挂在 `api/alert_digests.py`，注意路由顺序：静态优先于 `{fingerprint}` 动态）**
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/alerts/groups/{fingerprint}/triage` | 单簇研判（含 `force_refresh` Query）；先解析指纹取簇，组装 signature 调 `triage_alert_group` |
| GET | `/api/v1/alerts/groups/{fingerprint}/triage` | 取该簇缓存 verdict（无则返回 404） |
| GET | `/api/v1/alerts/groups/triage-top?hours=&top_n=` | 批量"今日必处理"清单（注册在 `/groups/{fingerprint}` 之前） |

**MCP（包一层 REST，`mcp/tools/alert_tools.py`，工具数 30→32）**
| 工具 | 对应 REST | 价值 |
|---|---|---|
| `list_alert_triage_top(hours, top_n)` | `/groups/triage-top` | "今天最该处理什么？"一句话答出排序清单 |
| `ai_triage_alert_group(fingerprint, hours, force_refresh)` | `/groups/{fp}/triage` | "这一簇要不要管、怎么管？" |

### 11.7 前端呈现（方案 A 实时页为主）
- 集群表格新增"AI 研判"列：`<ElTag>` 按 `ai_priority` 配色（P0 红/P1 橙/P2 黄/P3 蓝），噪声加 `is_noise` 灰标。
- 详情抽屉新增"AI 研判"块：优先级、置信度、理由、处置步骤、是否建议建事件（`建事件`按钮接 Phase3 的 `create_incident_from_group`）。
- 摘要面板：现 `summary_text` 由 AI 综述填充；`ai_model` 显示真实模型。
- `api/alert.ts` 新增 `triageAlertGroup` / `getAlertGroupTriage` / `getAlertTriageTop` 及 `AlertGroupTriage` 类型。

### 11.8 复用清单与风险
**复用（零新建基础设施）**
- `AIAnalysisService._analyze_with_agent` / `_call_ai_analysis` / `_parse_agent_response`（Agent→智谱降级与 JSON 解析直接复用，仅换 prompt 与结果落点）。
- `AlertQueryService.get_alert_groups` / `get_alert_group_detail`（簇签名来源，已含 srcip/asset/sample）。
- `AlertGroupSnapshotService`（P1.5 回填 verdict）。
- `NotificationService`（Phase 2 推送研判结论，Phase 1 仅产出）。

**风险与处理**
| 风险 | 处理 |
|---|---|
| AI 配额/网络（智谱限流） | 多级降级：Agent→智谱→启发式 verdict，`source` 字段标记，不阻塞主流程 |
| JSON 解析不稳定 | 严格解析失败→启发式；Prompt 强调只返回 JSON，去掉多余文本 |
| Agent 超时 | 复用现有 `asyncio.TimeoutError` 捕获后降级，单簇研判设合理超时（如 30s） |
| 缓存一致性 | 同 fingerprint 7 天 TTL；`force_refresh` 强制重算；快照回填取"最新未过期 verdict" |
| 成本 | 仅 TopN≤20/次，每日 ≤20 次调用，可忽略 |
| 历史页 verdict 滞后 | P1.5 回填的是"最近一次研判"，新簇首次出现需等下次摘要/研判才带结论（可接受） |

### 11.9 实施计划（勾选清单）
- [ ] **P1.1** `models/alert_group_analysis.py` 建 `AlertGroupAnalysis`；`create_all` 建表（同 digest 范式）。
- [ ] **P1.2** `AIAnalysisService` 增加 `triage_alert_group` + `_build_group_triage_prompt` + `_save_group_analysis` + `_get_cached_group_analysis`；实现 Agent→智谱→启发式三级降级。
- [ ] **P1.3** `services/alert_group_triage_service.py` 建 `AlertGroupTriageService.triage_top_groups` / `get_cached_verdict`。
- [ ] **P1.4** `AlertDigestService.generate` 调 `triage_top_groups` 写回 `ai_*` 字段；`summary_text` 改 AI 综述 + `ai_model` 写实名。
- [ ] **P1.5** `AlertGroupSnapshot` 模型加 4 个 AI 列；`snapshot()` 回填 verdict（按 fingerprint 查缓存，不调 AI）。
- [ ] **P1.6** `api/alert_digests.py` 加 `POST/GET /groups/{fp}/triage` + `GET /groups/triage-top`（**注意路由顺序**，静态在动态前）。
- [ ] **P1.7** `mcp/tools/alert_tools.py` 加 `list_alert_triage_top` + `ai_triage_alert_group`（30→32 工具）。
- [ ] **P1.8** 前端实时页：AI 研判列 + 详情块 + 摘要综述；`api/alert.ts` 新增 3 函数 + 类型。
- ✅ **联调验收**：自签 JWT + httpx 直打端点（同既有验证范式），跑通实时研判 / 摘要 AI 字段 / MCP 问答。

### 11.10 验证方法
复用既有"自签 JWT（admin id）+ httpx 直打端点"范式（`ai-minisoc-backend-feature-verify` 技能）：
1. 后端重启（会清 TokenManager）→ 用 `SECRET_KEY` 自签 admin JWT。
2. `POST /alerts/digest/generate?hours=24` → 校验 `top_groups[].ai_priority` 非空、`ai_model != template`、`summary_text` 含"必处理"语义。
3. `POST /alerts/groups/{fp}/triage` → 校验返回 verdict；`GET /alerts/groups/{fp}/triage` 取缓存。
4. `GET /alerts/groups/triage-top?hours=24&top_n=10` → 校验按 P0>P1>P2>P3 排序。
5. MCP：连接器重连 + `set_mcp_credentials(admin/admin123)` → `list_alert_triage_top` / `ai_triage_alert_group` 跑通。
6. 前端 `vue-tsc` 类型检查通过；实时页 AI 列与详情块渲染正常。

### 11.11 待确认决策点（开工前）
1. **决策点 1**：AI verdict 落库采用**独立表 `soc_alert_group_analyses`**（推荐）还是复用 `soc_ai_analyses`（`alert_id=grp:<fp>`）？——本文档推荐独立表。
2. **决策点 2**：P1.5「历史快照回填 verdict」是否纳入 Phase 1（推荐，零额外配额、让历史页也显示 AI 结论），还是留到后续？
3. **决策点 3**：默认研判 TopN 是否维持 **20**（成本≈20 次/天），还是按需调小？
4. **决策点 4**：启发式兜底在"无 AI"时是否对外标注 `source=heuristic`（推荐，透明可排障）？
