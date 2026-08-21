# AI-miniSOC AI化资产管理模块 — 产品需求文档 (PRD)

**文档版本**: v1.2.1.1
**创建日期**: 2026-06-01
**最后更新**: 2026-08-20
**状态**: Draft（基线已对齐至 P2 交付；v1.2 纳入评审修订，v1.2.1 已修正 3 处评审硬伤，待 P3 执行）

---

## 一、文档概述

### 1.1 编写目的

基于以下三份调研成果，为 AI-miniSOC 资产管理模块规划 AI 增强能力的完整需求：

1. **IT资产管理开源竞品分析** — Snipe-IT、GLPI、NetBox、Ralph、OCS Inventory 功能对比
2. **LLM/Agent 在 ITAM 中的 8 个应用场景** — 自然语言查询、变更分析、安全报告解读、自动对账等
3. **CMDB/ASM 开源推荐** — 维易CMDB 模型自定义、星环攻击面管理扫描链路

### 1.2 当前状态

| 能力 | 状态 | 说明 |
|------|------|------|
| 资产 CRUD | ✅ 已完成 | 手动创建/编辑/删除资产 |
| Wazuh 自动同步 | ✅ 已完成 | Agent 信息自动导入，含变更日志 |
| 资产信息丰富 | ✅ 已完成 | OS/硬件信息从 Wazuh 补全 |
| 端口管理 | ✅ 已完成 | 资产端口 CRUD |
| 标签管理 | ✅ 已完成 | Key-Value 标签体系 |
| 变更追踪 | ✅ 已完成 | AssetChangeLog 记录字段变更 |
| AI 告警分析 | ✅ 已完成 | GLM-4-flash 告警解释 + 缓存 |
| AI 日志解释 | ✅ 已完成 | 自然语言日志解读 |
| 资产-告警关联 | ✅ 已完成 | P0 已落地：资产详情页可查看关联告警（OpenSearch 聚合 + AI 研判落库 `soc_ai_analyses`） |
| 资产-事件关联 | ✅ 已完成 | P1 已落地：事件闭环 + `soc_incidents` + `soc_asset_incidents` 关联表 |

**P3（本 PRD）已交付能力**（2026-08-21 更新）：

| 能力 | 需求项 | 状态 | 落地说明 |
|------|--------|------|----------|
| 资产风险评分 | F1.1 | ✅ 已完成 | 规则引擎打分 + AI 摘要；权重外置 `soc_system_config(category='risk_rules')`（非 PRD 设想的 YAML） |
| 安全态势摘要 | F1.2 | ✅ 已完成 | 复用 P0/P1 关联数据做 AI 聚合，未新建关联机制 |
| L1 自然语言查询 | F2.1 | ✅ 已完成 | 查询历史复用 `soc_chat_sessions`（`model_name='asset-query-l1'`）；L2 复合查询未做 |
| 生命周期 / EOL | F3.2 | ✅ 已完成 | `soc_eol_reference` 种子 32 条 |
| 合规基线 | F3.3 | ✅ 已完成 | `configs/compliance_rules.yaml` 16 条规则；达标率与覆盖率同屏 |
| AI 知识库 | F2.3 | ✅ 已完成 | 未引入 pgvector，按关键词检索 |
| AI 反馈闭环 | F4.1 | ✅ 已完成 | 6 类 AI 产物通用 👍👎 + 修正文本 |
| 预算限流 | §4.4 | ✅ 已完成 | `ai_budget` 统一管控，超限降级模板 |
| **资产自动对账** | **F1.3** | **✅ 已完成** | 三类差异纯规则判定 + AI 解读；见下方实现偏差 |
| **数据健康聚合页** | **F1.3** | **✅ 已完成** | `GET /api/v1/data-health`，源健康/死信/对账三层统一入口 |
| AI 安全报告 | F2.2 | ✅ 已完成 | 周报/月报/按需/事件驱动四种触发；data_coverage JSONB 硬门槛；不引入消息队列，事件驱动走 cron 或前端按钮调 `POST /reports/check-incident-trigger` |
| 变更影响分析 | F3.1 | ❌ 未开始 | P3 优先级 |
| 推送场景 3/5 | F4.2 | ⚠️ 部分 | 影子资产发现（F1.3 已就绪可接）、报告生成完成（依赖 F2.2） |
| 权限矩阵（§6.5） | X1 | ⚠️ 未对齐 | 菜单已种 `view/reconcile/resolve/report` 按钮权限，但后端 `require_menu_permission` 使用数仍为 0 |

> **F1.3 实现偏差（已实测，2026-08-21 生产验证）**：
> - 表结构相对 §1.3 增加 `run_id`（批次）与 `resolve_note`。无批次标识无法查询「最近一次对账结果」；未采用 compliance 的 runs/findings 双表，避免为一张结果表再引一张表。
> - `resolved_by` 为 VARCHAR 存 username 快照（非 UUID 外键），与 `soc_ai_feedback.user_id` 为 INTEGER 同属既有惯例偏差。
> - 判定加了三条 PRD 未写的护栏，均为压制误报：排除 Wazuh manager（agent `000`，其 ip 恒 `127.0.0.1`、`lastKeepAlive` 恒为 `9999-12-31` 哨兵值）；断开不足 7 天不判下线；台账无 `wazuh_agent_id` 的资产不参与下线判定（否则 51 台采集来的路由器资产会被集体误判）。
> - Wazuh 不可达时 API 返回 503 并抛错，**绝不退化为「无差异」**——把采集故障伪装成台账干净比直接报错危险得多。
> - 生产实测（2026-08-21）：20 agent / 73 资产 / 9 项 offline 差异（7 个 disconnected 35–266 天、2 个 agent_deleted），shadow 与 mismatch 均为 0，无误报；AI 报告走通 GLM 且首行正确声明数据降级。

> **阶段基线（2026-08-20 刷新）**：本 PRD 编写时（v1.0, 2026-06-01）P0/P1/P2 尚未启动，故上表将关联、告警分析、对账前置等标为「未完成」。截至本修订，**P0（告警降噪聚合 + 资产关联 + AI 研判落库）、P1（事件闭环 + 脆弱性管理）、P2（上网行为异常检测）均已交付**。因此本 PRD（即 P3）应定位为**在已有能力之上的增值层**，而非从零建设：
> - F1.2（资产-告警-事件关联）改为**「复用已有关联数据 + AI 聚合摘要」**，不再新建关联机制；
> - F1.1 风险评分的「告警密度」维度可直接复用 P0 的 `soc_ai_analyses` / 告警聚合结果，无需重新对接 Wazuh；
> - F1.3 对账、F2.2 报告所依赖的同步/采集/日志链路，应先参考 **P4 数据可靠性** 的已知约束（见 §八-B）。

### 1.3 设计原则

1. **不重新发明轮子** — Wazuh 已有的能力直接复用，AI-miniSOC 专注于增值层
2. **AI 是增值层，不是重建层**（v1.2 修订措辞）— P0/P1/P2 已交付告警聚合、事件闭环、脆弱性、行为检测等能力，本 PRD 在其上叠加 AI 增强，不重复建设关联、聚合机制
3. **小规模优先** — 面向 200 台以内部署，不追求企业级复杂度（不引入 pgvector、消息队列等重型组件）
4. **渐进式实现** — 分阶段交付，每阶段有独立可用价值
5. **可解释、可反馈、可降级**（v1.2 新增）— 所有 AI 产物必须可解释（评分可拆解到维度与规则）、可溯源（记录数据窗口/Prompt 版本/token 用量，见横切需求 X2）、可反馈（F4.1 反馈闭环）、可降级（非 AI 兜底路径，见 §八-C）
6. **成本可控**（v1.2 新增）— 所有 GLM 调用纳入 §4.4 预算与限流框架，防止重试风暴放大成本
7. **判定交给规则，解读交给 AI**（v1.2 新增）— 合规判定、EOL 日期等确定性结论一律由规则引擎/预置数据产生，LLM 只负责解释与建议（见 F3.2/F3.3）

---

## 二、用户画像与使用场景

### 2.1 目标用户

**主要用户：个人安全运维者 / 小团队 IT 管理员**

- 管理一个不超过 200 台设备的网络
- 设备类型混合：物理主机、虚拟机、IoT、移动设备、云主机
- 既管安全也管运维，一人多岗
- 技术水平中等到高，但不一定精通 SQL 或安全工具

### 2.2 核心痛点

| 痛点 | 具体表现 | AI 如何解决 |
|------|---------|------------|
| 台账不准 | 不知道哪些设备在线、哪些已下线、哪些是影子资产 | 自动对账 + 差异报告 |
| 告警看不懂 | Wazuh 告警技术性强，大量规则难理解 | ✅ 已实现 AI 解释 |
| 资产关联模糊 | 不知道一个 IP 对应什么业务、出了问题影响谁 | AI 关联分析 + 影响评估 |
| 安全风险不透明 | 不知道哪些资产有高危端口、哪些系统过时未补丁 | AI 风险评估 + 报告解读 |
| 查询门槛高 | 想查"3楼机房哪些 Windows 没补丁"需要写 SQL 或点很多筛选 | 自然语言查询 |
| 知识无法积累 | 上次排查一个故障的过程下次又要重来 | 运维知识库 |
| 风险变化无感知（v1.2 新增） | 资产风险在悄悄上升（新开端口、评分上涨、源中断）没人盯 | 风险趋势对比（F1.1）+ 主动推送（F4.2） |

---

## 三、功能需求

### Phase 1：AI 资产感知与关联（核心增强）

#### F1.1 AI 资产风险评分

**优先级**: P0
**用户价值**: 一眼看出哪些资产最需要关注

**功能描述**：
- 对每个资产自动计算综合风险评分（0-100）
- 评分维度：
  - **暴露面风险** (30%)：开放高危端口数、公网可达性
  - **系统健康度** (25%)：OS 是否过时、是否 EOL、补丁状态
  - **告警密度** (25%)：近期关联告警数量和严重度
  - **资产重要性** (20%)：criticality 设置 × 业务权重

**评分规则：外置、可配置、可解释（v1.2 新增，废弃黑盒评分）**：

- 评分规则以配置形式外置（YAML 文件或 `soc_system_config` 中 `category='risk_rules'` 记录），**不硬编码**；权重与阈值支持运行时调整，调整后全量重算并落审计（谁在何时改了什么权重）
- 各维度子分数计算规则显式建模，示例：

```yaml
# configs/risk_rules.yaml（示意）
weights: { exposure: 0.30, health: 0.25, alerts: 0.25, importance: 0.20 }
exposure:
  high_risk_ports: [22, 23, 135, 139, 445, 3389, 5900, 6379, 27017]
  score_map: "min(100, high_risk_port_count * 25)"   # 0个=0分，≥4个=满分
  public_exposure_bonus: 20                           # 公网可达加分，总分封顶100
health:
  eol: 100
  major_version_behind: { ">=2": 70, "1": 40 }
  unknown: null       # null = 数据缺失 → 按降权处理（见 §4.5），不做静默满分/零分
alerts:
  window_days: 7
  score_map: "min(100, high*20 + medium*8 + low*2)"   # 复用 P0 告警聚合结果
importance:
  base: { critical: 100, high: 70, medium: 40, low: 20 }
  data_classification_bonus: 10                       # 复用 soc_assets.data_classification
```

- **每次评分落 `score_breakdown` JSONB**，记录各维度得分、权重、命中规则与理由，支撑"为什么这台是 85 分"的追问；前端风险详情页展示**雷达图 + 维度明细列表**
- **风险趋势（v1.2 新增）**：新增 `soc_asset_risk_history` 表记录每次评分快照；资产详情页展示近 90 天评分趋势折线图；评分较 7 天前上升 ≥20 分 → 触发站内通知（联动 F4.2），仪表盘增加"本周评分上升最快"列表
- **缺失维度降级（v1.2 新增）**：某维度数据缺失（如手动录入资产无 OS 信息）时，该维度按 50% 权重计入并在 breakdown 中标注 `data_gap: true`；全维度缺失时评分显示 N/A 而非 0（详见 §4.5）

**与已有漏洞评分体系的关系（v1.2.1 新增，避免双体系打架）**：

系统已存在**漏洞级**评分 `VulnerabilityAIService.calculate_risk_score`（P1 交付，CVSS 40% + 资产关键度 25% + 暴露面 20% + 在野利用 15%，含 `get_score_breakdown` API 与前端展示）。F1.1 是**资产级**评分，两者是「资产聚合 ← 漏洞明细」的上下层关系，**不是平行体系**：
- 「系统健康度」维度直接**消费漏洞评分输出**：取该资产活跃漏洞的 max risk_score 与高危漏洞计数加权（公式进 `risk_rules.yaml` 的 `health.from_vulnerabilities` 段）
- **口径共享**：`exposure_level`（public/internal/isolated）与 `criticality`（critical/high/medium/low）两字段在两套评分中语义一致，权重各自独立
- **前端命名区分**：漏洞级显示为「漏洞风险分」，资产级显示为「资产风险分」，避免用户混淆
- 本 PRD 不改动 `VulnerabilityAIService`，只读取其输出

**数据来源**：
- 端口数据：`soc_asset_ports` 表
- OS 信息：Wazuh 同步的 `os_name` + `os_version`
- 告警数据：复用 P0 告警聚合 / `soc_ai_analyses` 研判结果（避免绕过现有层直连 Wazuh API）
- 漏洞/健康数据：`VulnerabilityAIService.calculate_risk_score` 漏洞级评分输出（P1，作为「系统健康度」维度输入，见上方关系说明）
- 资产属性：`soc_assets` 表的 `criticality` 字段

**AI 增强**：
- 调用 GLM 对高风险资产生成一句话风险摘要
- 例："此服务器开放了 3389(RDP)、22(SSH)、445(SMB) 端口，运行已 EOL 的 CentOS 7，近 7 天有 23 条告警，风险评分 85/100"
- 风险摘要缓存 24 小时
- **调用门槛（v1.2 新增，控成本）**：仅对 `risk_score ≥ 60` 或"7 天内评分上升 ≥20 分"的资产生成/刷新 GLM 摘要，其余资产展示 breakdown 规则化文案（如"开放 2 个高危端口，OS 落后 1 个大版本"）

**数据模型扩展**：
```sql
-- 新增字段到 soc_assets
ALTER TABLE soc_assets ADD COLUMN risk_score INTEGER DEFAULT 0;
ALTER TABLE soc_assets ADD COLUMN risk_summary TEXT;
ALTER TABLE soc_assets ADD COLUMN risk_scored_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE soc_assets ADD COLUMN score_breakdown JSONB;  -- v1.2 新增：评分明细（可解释性）

-- v1.2 新增：风险评分历史表（趋势分析）
CREATE TABLE soc_asset_risk_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES soc_assets(id) ON DELETE CASCADE,
    risk_score INTEGER NOT NULL,
    score_breakdown JSONB,
    scored_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

**API 设计**：
```
GET  /api/v1/assets/{id}/risk          # 获取单个资产风险详情（含 breakdown + 趋势）
GET  /api/v1/assets/{id}/risk/history  # v1.2 新增：评分历史（趋势折线图数据）
POST /api/v1/assets/risk/batch-score   # 批量重新计算风险评分
GET  /api/v1/assets/risk/overview      # 风险总览（各分数段分布）
GET  /api/v1/assets/risk/rules         # v1.2 新增：查看当前评分规则与权重
PUT  /api/v1/assets/risk/rules         # v1.2 新增：调整权重/阈值（admin，落审计）
```

**前端展示**：
- 资产列表：新增"风险"列，用颜色标签显示（绿/黄/橙/红）
- 资产详情页：新增"风险概览"卡片，显示评分 + AI 摘要 + 各维度雷达图 + **维度明细列表（breakdown，含 data_gap 标注）+ 近 90 天趋势折线（v1.2）**
- 仪表盘：风险分布饼图 + Top10 高风险资产列表 + **"本周评分上升最快"列表（v1.2）**

---

#### F1.2 资产-告警-事件关联（复用 P0/P1 已建关联）

**优先级**: P1（增值层，非新建机制）
**用户价值**: 资产详情页一目了然看到关联的安全事件

**关联能力现状（前置已就绪，勿重复建设）**：
- **资产-告警关联**：P0 已实现，告警聚合与 AI 研判已落库 `soc_ai_analyses`，资产详情页可直接读取。
- **资产-事件关联**：P1 已实现，`soc_incidents` 通过 `soc_asset_incidents` 关联资产，事件闭环与状态流转已可用。

**功能描述**：
- 资产详情页新增"安全态势"Tab，**聚合展示已有关联数据**（不新建关联逻辑）：
  - 该资产 IP 近 7/30 天的告警列表（复用 P0 告警聚合 / OpenSearch 查询结果，而非绕过现有层直连 Wazuh）
  - 关联的安全事件列表（从 `soc_incidents` + `soc_asset_incidents` 查询）
  - AI 生成的该资产安全态势摘要

**AI 增强**：
- 对资产的告警历史进行 AI 聚合分析
- 输出："该服务器近 30 天收到 47 条告警，主要是 SSH 暴力破解（32次）和异常进程（8次）。SSH 攻击来自 3 个不同 IP，建议检查密码强度并考虑启用 fail2ban。"
- **溯源要求（v1.2 新增）**：摘要须标注所引用的数据窗口与数据源（如"基于 2026-08-14 ~ 08-21 OpenSearch 告警聚合"），角标点开可见完整溯源信息（横切需求 X2）

**API 设计**：
```
GET /api/v1/assets/{id}/alerts         # 获取资产关联告警（代理 Wazuh 查询）
GET /api/v1/assets/{id}/incidents      # 获取资产关联事件
GET /api/v1/assets/{id}/security-summary  # AI 生成安全态势摘要
```

**前端展示**：
- 资产详情页新增 Tab："安全态势"
  - 安全摘要卡片（AI 生成，带数据窗口标注与反馈入口）
  - 告警时间线（按时间排列的告警列表）
  - 关联事件列表（可跳转到事件详情）

---

#### F1.3 资产自动对账

**优先级**: P0
**用户价值**: 发现台账与实际网络的差异，消除影子资产

**功能描述**：
- 对比台账数据与 Wazuh Agent 列表，自动发现差异
- 差异类型：
  - **影子资产**：Wazuh 有 Agent 但台账没有 → 自动提示补录
  - **疑似下线**：台账有但 Wazuh Agent 已断开 → 标记待确认
  - **信息不一致**：IP/主机名/OS 与台账不匹配 → 记录变更

**数据新鲜度与边界澄清（v1.2 新增，执行前必读）**：

- **新鲜度标注**：对账结果与对账页面必须展示"**最近一次成功同步时间**"（读 `soc_sync_tasks` / `soc_source_health`）；源异常时页面顶部横幅提示"**源异常中，结果可能不全**"，禁止在数据不新鲜时静默给出"无差异"结论
- **三者边界**（避免与 P4 已建机制混淆或重复）：
  - `soc_source_health`（源健康）= **基础设施层**：采集器/同步任务还在不在工作
  - `soc_sync_dead_letter`（同步死信）= **数据层**：同步过程中被丢弃/失败的数据
  - `soc_asset_reconciliations`（对账）= **业务层**：台账与实际网络的差异
  - 前端统一在"**数据健康**"入口展示三者（对账页面内嵌源健康状态卡，可下钻死信列表），而非三处散落
- **并发与审计（v1.2 新增）**：对账处理（确认/忽略/补录）走状态机校验（`pending → confirmed/ignored/resolved`，重复处理第二个请求直接失败），不引入额外锁；全部处理操作落 `soc_audit_logs`（谁、何时、处理了哪条差异）
- **权限（v1.2 新增）**：处理操作要求对账处理权限，operator 角色仅能处理本部门资产（见横切需求 X1）

**AI 增强**：
- 自动对账后生成 AI 分析报告
- 输出："本次对账发现 3 台影子资产和 2 台疑似下线设备。影子资产 192.168.0.67 是新加入的 Ubuntu 22.04 服务器，建议确认后补录台账。192.168.0.45 已断开超过 7 天，可能是已退役设备。"
- 对账结果可一键确认/忽略/补录

**数据模型扩展**：
```sql
-- 对账结果表
CREATE TABLE soc_asset_reconciliations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES soc_sync_tasks(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES soc_assets(id),
    reconciliation_type VARCHAR(20),  -- shadow, offline, mismatch, confirmed
    details JSONB,                    -- 含数据新鲜度快照（本次对账依据的最近成功同步时间）
    status VARCHAR(20) DEFAULT 'pending',  -- pending, confirmed, ignored, resolved
    resolved_by VARCHAR(255),
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**API 设计**：
```
POST /api/v1/assets/reconcile          # 触发对账
GET  /api/v1/assets/reconciliations    # 查询对账结果
PUT  /api/v1/assets/reconciliations/{id}/resolve  # 处理对账结果（状态机校验 + 审计）
GET  /api/v1/assets/reconcile/report   # AI 生成对账报告
GET  /api/v1/data-health               # v1.2 新增：源健康 + 死信 + 对账 统一数据健康视图
```

**前端展示**：
- 资产管理菜单下新增"资产对账"页面（内嵌源健康状态卡与新鲜度提示）
- 新增"数据健康"聚合入口（v1.2）：源健康 / 死信 / 对账差异三卡联动
- 对账结果列表：差异类型标签 + 详情 + 操作按钮（确认补录/标记下线/忽略）
- 对账报告卡片（AI 生成，带数据窗口标注）

---

### Phase 2：AI 智能交互

#### F2.1 自然语言资产查询

**优先级**: P1（L1）/ P2（L2）（v1.2 修订：拆分两层能力，修正"意图识别硬塞复合查询"的设计缺陷）
**用户价值**: 用中文直接问资产相关问题，无需学习筛选器或 SQL

**能力分层（v1.2 核心修订）**：

原方案"意图识别 + 参数提取 + API 映射"对**跨表（端口）、时间窗（掉线）、跨源（告警）**查询本质不可表达。修订为两层：

**L1 — 简单筛选查询（MVP 范围，P1）**：
- 仅覆盖**单表可表达**的查询：资产类型 / OS / criticality / 在线状态 / 负责人 / 标签 / 关键词 / 网段
- 意图识别 + 参数提取 + 映射到已有资产 API 查询参数
- 意图识别失败或置信度低时，**诚实返回"无法理解，请换种说法"并给出可查询示例**，不猜测、不硬凑参数
- **参数回显确认**：前端以 chips 形式回显 AI 提取的参数（如 `[OS: Windows] [网段: 3F]`），用户可点击修正——这是反馈闭环的轻量形态，也兜住参数提取错误

**L2 — 复合查询（P2，MVP 后迭代）**：
- 覆盖跨表/时间窗/跨源查询（开放端口、掉线设备、资产近期告警、分组统计）
- 方案：**LLM 选择受限查询模板 + 填参数**，不生成裸 SQL（安全 + 稳定）：

```yaml
# configs/query_templates.yaml（示意）
templates:
  - id: port_open
    description: 查询开放了指定端口的资产
    params: { port: int, protocol: "tcp|udp" }
  - id: offline_since
    description: 查询指定时间后未再上线的资产
    params: { since: date }
  - id: asset_recent_alerts
    description: 查询某资产近期告警
    params: { asset: string, days: int }
  - id: stats_group_by
    description: 按指定维度统计资产数量
    params: { dimension: "os_name|asset_type|criticality|department" }
```

- LLM 输出 `{template_id, params}` JSON；后端校验参数类型与白名单后执行固定实现（模板执行层不经过 LLM）
- 模板库可扩展，新模板 = 一段后端代码 + 一条 YAML 描述，无需改 Prompt 主逻辑

**支持的查询类型与层级**：

| 查询类型 | 示例 | 层级 |
|---------|------|------|
| 条件筛选 | "3楼机房有哪些 Windows 服务器？" | L1 |
| 风险相关 | "哪些资产开放了 3389 端口？" | L2（`port_open` 模板） |
| 状态查询 | "上次同步以来有哪些设备掉线了？" | L2（`offline_since` 模板） |
| 统计分析 | "按操作系统统计资产数量" | L2（`stats_group_by` 模板） |
| 关联查询 | "这台服务器上最近有什么告警？" | L2（`asset_recent_alerts` 模板） |

**多轮对话（v1.2 新增）**：
- 支持上下文追问："3楼机房 Windows" → 得到结果后追问"其中哪些高风险？"
- 复用已有 `soc_chat_sessions` / `soc_chat_messages` 表，上下文保留最近 3 轮
- 查询历史落库，支持一键重放历史查询

**AI Prompt 设计（L1 意图识别）**：
```
你是 IT 资产管理助手。用户会用中文提问关于资产的问题。

你需要：
1. 判断查询意图：filter（筛选资产）/ stats（统计）/ detail（单个资产详情）
2. 提取查询参数：
   - asset_type: server/workstation/iot/network_device/cloud/other
   - os_name: 操作系统名
   - criticality: critical/high/medium/low
   - asset_status: 在线/离线
   - port: 端口号
   - network_segment: 网段
   - owner: 负责人
   - keywords: 关键词
3. 若问题超出上述参数可表达范围（如涉及端口/告警/时间趋势），返回 {"intent": "unsupported"}
4. 返回 JSON 格式

用户问题: {query}
```

**API 设计**：
```
POST /api/v1/assets/ask             # 自然语言查询（L1；L2 上线后同一入口自动路由）
Body: { "question": "3楼机房哪些Windows没打补丁？", "session_id": "可选，多轮对话" }
Response: {
  "level": "L1",
  "intent": "filter",
  "params": { "network_segment": "3F", "os_name": "Windows" },
  "assets": [...],
  "summary": "在3楼机房找到 5 台 Windows 服务器，其中 2 台系统版本较旧..."
}
GET /api/v1/assets/ask/history      # v1.2 新增：查询历史（支持重放）
```

**前端展示**：
- 资产列表页顶部新增"AI 查询"输入框（类似搜索栏）
- 输入问题后展示：参数回显 chips（可修正）+ 结果列表 + AI 摘要
- 支持追问（多轮会话形态）；查询历史可重放
- L2 模板查询结果中，unsupported 的问题给出"我能回答这些类型"的引导示例

---

#### F2.2 AI 安全报告解读

**优先级**: P1
**用户价值**: 将 Wazuh 扫描结果和告警数据转化为可操作的安全报告

**功能描述**：
- 触发方式（v1.2 修订：定时之外补充事件驱动，适配个人运维者的低频阅读习惯）：
  - 定期（周/月）
  - 按需
  - **事件驱动**：当月高危（critical/high）事件累计 ≥ N 条时自动生成专项报告（N 可配置，默认 3）
- 报告内容：
  - 资产安全总览：在线率、风险分布、高危资产 Top5
  - 告警趋势分析：近期告警数量变化、主要威胁类型
  - 风险发现：新开放的高危端口、EOL 系统、频繁告警资产
  - 处置建议：优先处理什么、具体操作步骤
- 报告以人话撰写，非原始数据堆砌

**数据完整性校验（v1.2 新增，硬性门槛）**：
- 报告生成前校验时间窗数据完整性（Loki 覆盖窗口、OpenSearch 可用性、源健康状态）
- 数据缺口（如超出 Loki 7 天保留、源中断区间）**显式写入报告"数据说明"章节**，落 `data_coverage` JSONB 字段
- **禁止用空区间编造趋势**（对齐 §八-B 执行建议第 2 条）

**AI 增强**：
- 调用 GLM 对安全数据进行整体分析，生成结构化报告
- 报告内容参考已有的告警分析 Prompt 风格（中文、分节、具体可操作）
- 报告缓存，支持历史查看

**数据模型扩展**：
```sql
CREATE TABLE soc_security_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type VARCHAR(20),  -- weekly, monthly, on_demand, incident_driven（v1.2 新增类型）
    period_start TIMESTAMP WITH TIME ZONE,
    period_end TIMESTAMP WITH TIME ZONE,
    title VARCHAR(255),
    summary TEXT,             -- AI 生成的执行摘要
    content JSONB,            -- 报告各章节内容
    risk_highlights TEXT,     -- AI 生成的高亮风险
    recommendations TEXT,     -- AI 生成的处置建议
    data_coverage JSONB,      -- v1.2 新增：数据完整性说明（窗口、缺口、源状态）
    prompt_version VARCHAR(20), -- v1.2 新增：溯源（横切需求 X2）
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**API 设计**：
```
POST /api/v1/reports/generate    # 生成报告（支持 weekly/monthly/on_demand/incident_driven）
GET  /api/v1/reports              # 报告列表
GET  /api/v1/reports/{id}         # 报告详情
```

**前端展示**：
- 侧边栏新增"安全报告"菜单
- 报告列表页：时间、类型、摘要预览
- 报告详情页：分节展示（总览→风险→告警→建议→**数据说明**），支持导出 PDF；"数据说明"章节用醒目样式提示缺口

---

#### F2.3 运维知识库

**优先级**: P1
**用户价值**: 将历史故障排查经验积累为可检索的知识

**功能描述**：
- 基于已有的告警分析和事件处理记录，自动构建运维知识
- 支持自然语言检索
- 知识来源：
  - AI 告警分析结果（已有 `soc_ai_analyses` 表）
  - 事件处理笔记和状态流转（`soc_incidents` + timeline）
  - 手动录入的运维文档

**检索方案（v1.2 修订：务实降级，不引入 pgvector）**：
- 主路径：候选召回（关键词 + 标签过滤）→ **GLM 对候选条目语义 rerank**
- `tsvector` 全文索引作为**可选加速层**（量大后再启用），MVP 不依赖
- 200 台规模下知识条目量级小（百条），无需向量数据库

**知识老化管理（v1.2 新增）**：
- 每条知识带 `last_validated_at` / `confidence_score` / `review_status`
- 超过 12 个月未复审、或与最新告警分析结论冲突的知识，自动进入 `pending_review` 队列，前端标黄提示"待复审"
- 用户可手动标记"已验证"刷新 `last_validated_at`

**AI 增强**：
- 对已解决的事件，AI 自动生成"故障→原因→解决方案"三元组
- 提取结果默认 `confidence_score=70`，人工确认后提升至 90

**数据模型扩展**：
```sql
CREATE TABLE soc_knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(50),     -- troubleshooting, configuration, policy, reference
    source_type VARCHAR(50),  -- ai_generated, manual, incident_summary
    source_id VARCHAR(100),   -- 关联的事件ID或分析ID
    tags TEXT[],               -- PostgreSQL 数组类型
    last_validated_at TIMESTAMP WITH TIME ZONE,  -- v1.2 新增：最近验证时间
    confidence_score SMALLINT DEFAULT 70,         -- v1.2 新增：置信度（人工确认后提升）
    review_status VARCHAR(20) DEFAULT 'active',  -- v1.2 新增：active / pending_review / expired
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    -- tsvector 全文列为可选加速层，MVP 不启用（v1.2 修订）
);
```

**API 设计**：
```
POST /api/v1/knowledge/search      # 自然语言搜索知识
GET  /api/v1/knowledge              # 知识列表（支持 review_status 过滤）
POST /api/v1/knowledge              # 手动创建知识条目
PUT  /api/v1/knowledge/{id}         # v1.2 新增：编辑知识条目
POST /api/v1/knowledge/{id}/validate  # v1.2 新增：标记已验证（刷新 last_validated_at）
POST /api/v1/knowledge/auto-extract # 从已解决事件中自动提取知识
```

---

### Phase 3：AI 主动防御

#### F3.1 智能变更影响分析

**优先级**: P2
**用户价值**: 变更前评估影响范围，降低操作风险

**前置依赖（v1.2 新增）**：
- 变更影响分析依赖**资产关系建模**（资产间依赖关系 / 网络拓扑）。关系模型建成前，本功能降级为"基于 IP 相邻性 + 告警关联 + 标签分组"的**粗粒度评估**，输出必须明确标注"基于有限关联数据，未包含拓扑信息"——诚实降级，不装作有拓扑
- 资产关系建模不在本 PRD 范围，建议作为后续迭代（P5）单独立项

**功能描述**：
- 用户描述计划变更（如"升级核心交换机固件"），AI 分析影响
- 分析维度：受影响资产、关联业务、历史告警、潜在风险
- 输出影响评估报告和维护窗口建议

**API 设计**：
```
POST /api/v1/assets/impact-analysis
Body: { "change_description": "将 192.168.0.10 的 SSH 端口从 22 改为 2222" }
```

#### F3.2 资产生命周期管理

**优先级**: P2
**用户价值**: 自动提醒设备退役、保修到期、系统 EOL

**功能描述**：
- 记录资产采购日期、保修期限
- 生成退役/升级建议列表

**EOL 数据源（v1.2 修订：弃 WebSearch 主路径，防幻觉）**：
- **主路径**：预置生命周期参考表（来源 endoflife.date 等公开数据 + 人工维护），落库为 `soc_eol_reference` 参考表（DDL 见 §5.3），**月度批量刷新**
- WebSearch 仅作补充校验，且结果**必须人工确认后才写入**
- 用户可手动覆盖 EOL 日期：`expected_eol_source=manual` 优先于 preset，覆盖操作落审计
- EOL 临近（30/7 天）触发通知（联动 F4.2）

**数据模型扩展**：
```sql
ALTER TABLE soc_assets ADD COLUMN purchase_date DATE;
ALTER TABLE soc_assets ADD COLUMN warranty_end DATE;
ALTER TABLE soc_assets ADD COLUMN expected_EOL DATE;
ALTER TABLE soc_assets ADD COLUMN expected_eol_source VARCHAR(20) DEFAULT 'preset';  -- v1.2 新增：preset / manual
```

**实现记录（2026-08-21 已落地，migration `c2d3e4f5a6b7`）**：

1. **参考表 schema 与 §5.3 DDL 有意偏差**：实际用 `pattern`（规范化小写子串）+ `display_name`
   替代 `product_name + cycle_name`。原因：Wazuh 上报的 OS 字段变体极多
   （`Ubuntu` / `Ubuntu Linux`、`24.04 LTS` / `24.04.2 LTS`、`Debian GNU/Linux 12`、
   `Microsoft Windows 11 Home China` + version `10.0.26200`），按 product+cycle 精确解析需要
   为每种发行版写版本号解析器；改为「规范化标签（去 `gnu/linux`、` linux` 噪声词）
   → 子串匹配 → 最长模式优先」后，DEV 22 台有 OS 信息的资产 100% 正确命中，
   且 `windows 11` 不会误命中 `windows 10`。
2. **诚实留空优于猜测**：滚动发行版（如 Kali 2025.3）无参考条目即 `expected_eol=NULL`，
   不按规律推算日期。DEV 实测 2 台 Kali 保持未匹配。
3. **`source='preset_unverified'` 口径分级（超出原 PRD 设计）**：种子数据编写过程中发现
   「凭记忆填 EOL」本身就是幻觉风险源——初版把 Alibaba Cloud Linux 3 填成 2026-03-31
   （实为 Linux **2** 的 EOL），官方文档核对后修正为 **2034-03-31**，误差 8 年，
   会把一台健康资产误报成「已超期」。因此：
   - 官方明确日期 → `source='preset'`
   - 按厂商支持政策推算 / 社区口径未定（openEuler 22.03、Windows 11 滚动版、
     Debian 13、Ubuntu 26.04）→ `source='preset_unverified'` + `notes` 写明依据，
     总览接口透出 `eol_unverified=true`，前端打「预估」标签
   - 人工核实后再改 `preset`（对应 PRD「WebSearch 结果必须人工确认后才写入」）
4. **落地范围**：33 条种子；API `GET /assets/lifecycle/overview`、`POST /lifecycle/refresh-eol`、
   `GET /lifecycle/eol-reference`、`PUT|DELETE /assets/{id}/eol`（覆盖/恢复均落审计）；
   前端概览页「生命周期预警」表 + 详情页 EOL 行与设置弹窗 + 编辑弹窗采购/保修日期；
   F4.2 推送场景 3（30 天 info / 7 天 warn / 已超期 warn，24h 去重）。
5. **与风险评分的关系**：`asset_risk` 的 health 维度仍用自带 `eol_systems` 兜底配置
   （无漏洞扫描数据时使用），未改为消费本表——遵循「本 PRD 不改动既有评分口径」，
   两套口径并存已在代码注释标注，后续可统一。

#### F3.3 合规基线检查

**优先级**: P2（v1.2 修订实现方案：判定不得交给 LLM）
**用户价值**: 按等保/CIS 基线自动检查合规状态

**功能描述**：
- 基于已有资产数据（端口、OS、告警），对照等保二级或 CIS 基线**子集**
- **双层架构（v1.2 核心修订）**：
  - **规则层（判定）**：合规项以结构化规则（YAML DSL）维护，每条规则有唯一 ID 与版本号；判定引擎输出**确定性**结论：达标 / 不达标 / 无法判定（数据缺失）；**LLM 不参与"是否合规"的判定**
  - **AI 层（解读）**：仅对"不达标"项生成整改步骤与风险解释，解读中引用规则 ID；报告注明规则库版本，可复核
- 合规范围先做 **10-15 条高价值规则**（高危端口暴露、EOL 系统在网、资产缺 Agent、明文协议在用等），不追求全量 CIS
- 可生成审计报告（引用规则版本号 + 判定依据，审计可自证）

> **为何废弃 v1.0 方案**：等保/CIS 是精确规则表（如"密码长度 ≥ 8"、"必须开启审计日志"），用 LLM 判定存在幻觉且审计时无法自证，等于埋下"AI 伪合规"的雷。修订后规则判定确定可审计，AI 只负责把"为什么不合规、怎么整改"讲成人话。

---

### Phase 4：AI 反馈闭环与主动运营（v1.2 新增）

#### F4.1 AI 反馈闭环

**优先级**: P1（横切能力，**随 Phase 1 一起交付**，不单独立项排期）
**用户价值**: AI 能力越用越准；AI 产物质量可量化

**功能描述**：
- 所有 AI 产物（风险摘要 / 态势摘要 / NL 查询结果 / 报告 / 知识条目）统一附 👍/👎 反馈入口 + 可选修正文本
- 前端以通用组件（`AiFeedback.vue`）实现，一次开发全场景复用
- 反馈落库后：
  - 月度汇总：按 `target_type` 统计 👎 率；👎 率 > 20% 的 AI 能力触发 **Prompt 迭代评审**
  - NL 查询的 👎 + 用户修正的参数 chips，直接构成意图识别的**评测集**（供 W0 之后的回归测试）
- 反馈采纳率纳入 §九 成功指标

**数据模型**：
```sql
CREATE TABLE soc_ai_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(50) NOT NULL,   -- risk_summary / security_summary / query / report / knowledge
    target_id VARCHAR(100) NOT NULL,    -- 关联产物ID（资产ID/报告ID/会话ID/知识ID）
    rating VARCHAR(10) NOT NULL,        -- up / down
    comment TEXT,                       -- 用户修正文本（可选）
    user_id UUID REFERENCES soc_users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**API 设计**：
```
POST /api/v1/ai/feedback            # 提交反馈
GET  /api/v1/ai/feedback/summary    # 反馈汇总（admin，月度）
```

#### F4.2 主动推送

**优先级**: P2
**用户价值**: 最有价值的 AI 是主动找你，而不是等你来问

**功能描述**：
- 基于已有 `soc_notifications` + WebSocket 通道（零新增基础设施）实现场景化推送：

| 推送场景 | 触发条件 | 重要度 |
|---------|---------|--------|
| 数据链路异常 | 源健康降级（如 Wazuh 同步中断 ≥ 3 小时） | critical |
| 风险评分突变 | 单资产 7 天内评分上升 ≥ 20 分 | warn |
| 影子资产发现 | 对账发现新增 shadow 差异 | warn |
| EOL 临近 | 距 EOL 30 天 / 7 天 | info / warn |
| 报告生成完成 | 周/月/专项报告就绪 | info |

> **【依赖澄清 · v1.2.1 修正】** "数据链路异常"场景依赖 P4 的 `soc_source_health` 源健康状态。经核实，P4 的源健康表为**后台调度被动落表**，并无"降级即自动推送"的事件钩子。因此本场景**由 F4.2 自身主动触发**：F4.2 的调度/轮询任务周期性检查 `soc_source_health` 中状态为 `degraded`/`down` 且持续 ≥ 3h 的记录（如 Wazuh 同步中断），自行通过已有 `soc_notifications` + WebSocket 发起 critical 站内通知，**不依赖 P4 主动回调**。其余 4 类场景（评分突变/影子资产/EOL 临近/报告完成）均由本模块内部事件直接触发，与本澄清无关。

- **频控**：同类通知 24h 内合并去重，避免打扰；重要度分级（info/warn/critical），critical 支持重复提醒
- 渠道：站内通知（已有）优先；邮件/Webhook 预留接口（Phase 3 后按需实现，对齐 CLAUDE.md Phase 3 规划）

**API 设计**：
```
POST /api/v1/notifications/push-rules   # 推送规则配置（阈值、重要度、开关）
GET  /api/v1/notifications/push-rules
```

---

### 横切需求（v1.2 新增，适用于所有 Phase）

#### X1 权限矩阵

多用户场景下的功能可见性与操作权限（复用现有 RBAC：`require_menu_permission` + 前端 `v-auth`）：

| 功能 | admin | operator（运维） | viewer | auditor |
|------|-------|-----------------|--------|---------|
| 资产/端口/标签 CRUD | ✅ | ✅ | 只读 | 只读 |
| 风险评分查看 | ✅ | ✅ | ✅ | ✅ |
| 风险重算 / 权重调整 | ✅ | ❌ | ❌ | ❌ |
| 对账触发 / 差异处理 | ✅ | ✅（限本部门资产） | ❌ | 只读 |
| AI 查询（F2.1） | ✅ | ✅ | ✅ | ✅ |
| 报告生成 | ✅ | ✅ | ❌ | ❌ |
| 报告查看 | ✅ | ✅ | ✅ | ✅ |
| 知识库编辑 / 验证 | ✅ | ✅ | ❌ | ❌ |
| AI 反馈提交（F4.1） | ✅ | ✅ | ✅ | ✅ |
| EOL 手动覆盖 | ✅ | ✅ | ❌ | ❌ |
| 通知接收（F4.2） | ✅ | ✅ | ✅ | ✅ |

配套要求：
- 对账差异处理按部门隔离（复用现有 department 体系）
- 对账处理、权重调整、EOL 覆盖、知识编辑等**写操作全部落 `soc_audit_logs`**

#### X2 AI 产物可追溯性

所有 AI 产物必须记录以下溯源元数据（审计自证 + 质量排查 + 成本核算三重目的）：

| 元数据 | 说明 | 存放（精确字段，已与代码核实） |
|--------|------|------|
| 输入数据窗口 | 引用了哪个时间段的数据 | 各产物表的 `data_coverage` / `score_breakdown` |
| 数据源 | OpenSearch / Loki / P0 聚合结果 | 同上 |
| Prompt 版本 | 如 `risk-summary@v3` | 各产物表自有列：`soc_security_reports.prompt_version`（已定义于 §5.3）；复用 P0 `soc_ai_analyses` 的产物以其现有 `model_version` 列承载（**不新增 `prompt_version` 列**，避免与 P0 迁移漂移） |
| 模型与参数 | GLM-4-flash / temperature 等 | `soc_ai_analyses.model_name` + `model_version`（P0 已建）；新产物表写入各自 `prompt_version` / `score_breakdown` JSONB |
| token 用量 | 本次调用消耗 | 现有 `soc_ai_analyses.tokens_used` 列（P0 已建，**不新增**）；新产物表的 token 用量记录在各自 `data_coverage` / `score_breakdown` JSONB（如有） |
| 生成时间 | 落库时间戳 | `created_at` |

> **字段核对（v1.2.1 修正）**：经代码核实，`soc_ai_analyses`（P0 已建）仅有 `model_name` / `model_version` / `tokens_used` / `cost` 列，**无 `prompt_version` 列**。故所有"Prompt 版本"溯源统一落 `soc_security_reports.prompt_version`（本 PRD 新增表）或 P0 现有 `model_version`，不再要求为 `soc_ai_analyses` 新增列；token 用量统一记 `tokens_used`，避免执行时因"字段不存在"报错。

前端约定：所有 AI 生成内容带"AI 生成"角标，点开可见溯源信息与反馈入口（F4.1）。

---

## 四、技术架构

### 4.1 AI 能力架构

```
┌───────────────────────────────────────────────────────┐
│                  前端 (Vue3 + Element Plus)            │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌────────────┐ │
│  │ AI查询栏  │ │ 风险面板  │ │ 报告页 │ │ 知识库对话  │ │
│  └──────────┘ └──────────┘ └────────┘ └────────────┘ │
└────────────────────────┬──────────────────────────────┘
                         │ REST API
┌────────────────────────┴──────────────────────────────┐
│                  后端 (FastAPI)                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │              AI Service Layer                     │ │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────────────┐│ │
│  │  │意图识别/  │ │风险评估   │ │报告生成/知识提取  ││ │
│  │  │模板路由   │ │(规则引擎) │ │                  ││ │
│  │  └──────────┘ └──────────┘ └───────────────────┘│ │
│  │  ┌──────────────────┐ ┌───────────────────────┐ │ │
│  │  │ 预算/限流/熔断    │ │ 反馈闭环/溯源记录     │ │ │
│  │  └──────────────────┘ └───────────────────────┘ │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │资产服务   │ │对账服务   │ │同步服务   │ │报告服务  │ │
│  │(已有)     │ │(新增)     │ │(已有)     │ │(新增)    │ │
│  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │
└───────────────┬──────────┬──────────┬────────────────┘
                │          │          │
          ┌─────┴──┐ ┌────┴───┐ ┌────┴─────────┐
          │PostgreSQL│ │Wazuh  │ │GLM API      │
          │(资产/   │ │API    │ │(智谱AI)      │
          │ 对账/   │ │       │ │              │
          │ 报告/   │ │       │ │              │
          │ 知识库) │ │       │ │              │
          └────────┘ └───────┘ └──────────────┘
```

### 4.2 AI 调用策略

| 场景 | 触发方式 | 模型 | 缓存策略 |
|------|---------|------|---------|
| 风险评分摘要 | 评分计算后（仅 score≥60 或上升≥20 的资产） | GLM-4-flash | 缓存 24h |
| 安全态势摘要 | 用户访问资产详情时 | GLM-4-flash | 缓存 12h |
| 自然语言查询 | 用户输入时 | GLM-4-flash | 不缓存 |
| 对账报告 | 对账完成后 | GLM-4-flash | 缓存至下次对账 |
| 安全报告 | 定时/手动/事件驱动 | GLM-4-flash | 缓存至报告周期结束 |
| 知识提取 | 事件关闭时 | GLM-4-flash | 永久 |
| 知识检索 rerank | 用户搜索时 | GLM-4-flash | 不缓存 |

> **统一要求（v1.2）**：所有场景记录 Prompt 版本、输入数据窗口、token 用量（横切需求 X2）；预算与限流见 §4.4。注意：**风险评分本身是规则计算，不调用 GLM**——只有摘要/解读类产物走 LLM。

### 4.3 新增文件清单

```
src/backend/app/
├── api/
│   ├── asset_risk.py           # F1.1 风险评分 API
│   ├── asset_reconciliation.py # F1.3 对账 API
│   ├── asset_query.py          # F2.1 自然语言查询 API（L1 意图识别 + L2 模板路由）
│   ├── reports.py              # F2.2 安全报告 API
│   ├── knowledge.py            # F2.3 知识库 API
│   └── ai_feedback.py          # F4.1 反馈 API（v1.2 新增）
├── services/
│   ├── asset_risk.py           # 风险评分服务（规则引擎）
│   ├── asset_reconciliation.py # 对账服务
│   ├── asset_query.py          # NL→意图识别（L1）/模板选择（L2）→API映射
│   ├── report_generator.py     # 报告生成服务（含数据完整性校验）
│   ├── knowledge_service.py    # 知识库服务（含 rerank、老化队列）
│   └── ai_budget.py            # 预算/限流/熔断（v1.2 新增，§4.4）
├── models/
│   ├── asset_reconciliation.py # 对账模型
│   ├── security_report.py      # 报告模型
│   ├── knowledge.py            # 知识模型
│   ├── asset_risk_history.py   # 风险历史模型（v1.2 新增）
│   ├── eol_reference.py        # EOL 生命周期参考表模型（F3.2 预置数据源）
│   └── ai_feedback.py          # 反馈模型（v1.2 新增）
└── schemas/
    ├── asset_risk.py
    ├── reconciliation.py
    ├── report.py
    └── knowledge.py

configs/
├── risk_rules.yaml             # 评分规则配置（v1.2 新增）
└── query_templates.yaml        # L2 查询模板配置（v1.2 新增）

src/frontend/src/
├── views/asset/
│   ├── AssetRiskPanel.vue      # 风险概览组件（含 breakdown 明细 + 趋势图）
│   ├── AssetReconciliation.vue # 对账页面
│   ├── AssetDataHealth.vue     # 数据健康聚合页（源健康/死信/对账，v1.2 新增）
│   ├── AssetSecurityTab.vue    # 资产安全态势Tab
│   └── AssetAIQuery.vue        # AI 查询组件（含参数 chips 回显 + 多轮追问）
├── views/report/
│   ├── ReportList.vue          # 报告列表
│   └── ReportDetail.vue        # 报告详情（含数据说明章节）
├── views/knowledge/
│   ├── KnowledgeList.vue       # 知识库列表（含待复审标黄）
│   └── KnowledgeSearch.vue     # 知识库搜索
└── components/
    └── AiFeedback.vue          # 通用 AI 反馈组件（v1.2 新增，👍/👎+修正文本）
```

### 4.4 AI 调用预算与限流（v1.2 新增）

| 项 | 默认值 | 说明 |
|----|--------|------|
| QPS 上限 | 2 | GLM-4-flash 免费档限制内 |
| 单日调用上限 | 500 次 | 超限后新请求直接走降级，次日恢复 |
| 单月成本预算 | ¥10 | 超预算触发通知（F4.2），**不自动熔断**（避免关键功能静默失效） |
| 429/超时处理 | 指数退避重试 ≤ 2 次 | 仍失败则走非 AI 降级 |
| 熔断 | 5 分钟内失败率 > 50% → 熔断 10 分钟 | 熔断期间全部 AI 功能走降级，防止重试风暴 |

**调用量估算（200 资产规模）**：

| 场景 | 频次估算 |
|------|---------|
| 风险摘要 | ~40 次/天（缓存 24h，仅 score≥60 或评分上升资产刷新） |
| 态势摘要 | ~20 次/天（访问触发 + 12h 缓存） |
| NL 查询 | ~50 次/天（人工触发） |
| 报告 | 周 1 + 月 1 + 事件驱动 ≤ 4/月 |
| 知识提取 / rerank | ~30 次/月 |
| **合计** | **≈ 110 次/天 × ~600 token/次 ≈ 6.6 万 token/天，远低于预算** |

> 故障场景下的重试放大是成本失控主因，故熔断（而非预算）是第一道防线；成本按月出报表（token 用量已在 X2 落库）。

### 4.5 数据稀疏降级策略（v1.2 新增）

| 场景 | 处理方式 |
|------|---------|
| 无 OS 信息（手动录入资产） | 健康度维度按 50% 权重计入，breakdown 标注 `data_gap: true` |
| 无端口数据 | 暴露面维度按 50% 权重计入 + data_gap 标注 |
| 告警数据源异常 | 回退上次缓存评分值 + 打标 `stale`（对齐 §八-B） |
| 长期离线资产（笔记本/IoT） | 状态区分 在线/离线/退役；离线资产加"数据陈旧度"惩罚，但**不参与告警密度计分**（无告警 ≠ 安全） |
| 全维度缺失 | 评分显示 N/A（不显示 0，避免误导"很安全"） |

---

## 五、数据库变更汇总

> **表基线（v1.2.1 更正）**：截至 2026-08-21 实测（导入全部模型模块后 `Base.metadata`）共 **40 张表**（v1.0 编写时为 24 张，P0/P1/P2/P4 期间新增 16 张未回写文档；注意 `app/models/__init__.py` 未导出 vulnerability/sca/source_health 等 7 张表，仅 `import app.models` 会误报 33 张，CLAUDE.md 中“24 张”待同步更新）。本 PRD 新增 5 张表 + `soc_assets` 扩列后，总数为 **45 张**。

### 5.1 soc_assets 新增字段

```sql
-- 风险评分相关（4 个）
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS risk_score INTEGER DEFAULT 0;
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS risk_summary TEXT;
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS risk_scored_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS score_breakdown JSONB;  -- v1.2 新增

-- 生命周期相关（4 个）
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS purchase_date DATE;
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS warranty_end DATE;
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS expected_EOL DATE;
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS expected_eol_source VARCHAR(20) DEFAULT 'preset';  -- v1.2 新增
```

### 5.2 字段复用原则

> **对齐已有建模**：`soc_assets` 已存在 `data_classification`（数据分级）、`owner_contact`（责任人联系方式，alembic `a1b2c3d4e5f6`）等字段。风险评分的「资产重要性」维度应**直接复用这些字段**作为权重输入，不要重复新增责任人/分级字段；仅 §5.1 所列 8 个字段为本次确需新增。

### 5.3 新增表

```sql
-- 对账结果表
CREATE TABLE soc_asset_reconciliations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES soc_sync_tasks(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES soc_assets(id) ON DELETE SET NULL,
    reconciliation_type VARCHAR(20),  -- shadow, offline, mismatch, confirmed
    details JSONB,                    -- 含数据新鲜度快照
    status VARCHAR(20) DEFAULT 'pending',
    resolved_by VARCHAR(255),
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 风险评分历史表（v1.2 新增，趋势分析）
CREATE TABLE soc_asset_risk_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES soc_assets(id) ON DELETE CASCADE,
    risk_score INTEGER NOT NULL,
    score_breakdown JSONB,
    scored_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- 安全报告表
CREATE TABLE soc_security_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type VARCHAR(20),           -- weekly, monthly, on_demand, incident_driven
    period_start TIMESTAMP WITH TIME ZONE,
    period_end TIMESTAMP WITH TIME ZONE,
    title VARCHAR(255),
    summary TEXT,
    content JSONB,
    risk_highlights TEXT,
    recommendations TEXT,
    data_coverage JSONB,               -- v1.2 新增：数据完整性说明
    prompt_version VARCHAR(20),        -- v1.2 新增：溯源
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 知识库表
CREATE TABLE soc_knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(50),
    source_type VARCHAR(50),
    source_id VARCHAR(100),
    tags TEXT[],
    last_validated_at TIMESTAMP WITH TIME ZONE,  -- v1.2 新增
    confidence_score SMALLINT DEFAULT 70,         -- v1.2 新增
    review_status VARCHAR(20) DEFAULT 'active',   -- v1.2 新增
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- AI 反馈表（v1.2 新增）
CREATE TABLE soc_ai_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(50) NOT NULL,
    target_id VARCHAR(100) NOT NULL,
    rating VARCHAR(10) NOT NULL,       -- up / down
    comment TEXT,
    user_id UUID REFERENCES soc_users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- EOL 生命周期参考表（F3.2：预置数据源，月度批量刷新）
CREATE TABLE soc_eol_reference (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_name VARCHAR(255) NOT NULL,      -- 产品名，如 CentOS / Windows Server / Nginx
    product_type VARCHAR(50) DEFAULT 'os',   -- os / software / library
    cycle_name VARCHAR(100),                 -- 版本/周期名，如 "7" / "2019" / "1.24"
    eol_date DATE NOT NULL,                  -- 生命周期终止日期
    source VARCHAR(20) DEFAULT 'preset',    -- preset(endoflife.date 等) / manual
    refreshed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (product_name, cycle_name, source)
);
```

### 5.4 索引

```sql
CREATE INDEX idx_reconciliations_status ON soc_asset_reconciliations(status);
CREATE INDEX idx_reconciliations_type ON soc_asset_reconciliations(reconciliation_type);
CREATE INDEX idx_risk_history_asset_time ON soc_asset_risk_history(asset_id, scored_at DESC);  -- v1.2 新增
CREATE INDEX idx_reports_type ON soc_security_reports(report_type);
CREATE INDEX idx_reports_period ON soc_security_reports(period_start, period_end);
CREATE INDEX idx_kb_category ON soc_knowledge_base(category);
CREATE INDEX idx_kb_review_status ON soc_knowledge_base(review_status);  -- v1.2 新增（待复审队列）
CREATE INDEX idx_kb_tags ON soc_knowledge_base USING GIN(tags);
CREATE INDEX idx_ai_feedback_target ON soc_ai_feedback(target_type, target_id);  -- v1.2 新增
CREATE INDEX idx_eol_reference_product ON soc_eol_reference(product_name, cycle_name);  -- F3.2 新增：EOL 参考表查询
```

### 5.5 迁移策略（v1.2 新增，吸取 alembic 漂移教训）

CLAUDE.md 已记录 alembic 迁移历史不完整的已知问题（`soc_menus` 手工列、8 张 P4 表缺迁移）。本 PRD 的 schema 变更**不得重蹈覆辙**：

1. **全部走 alembic**：8 个新增字段 + 6 张新表（含 `soc_eol_reference`）全部出迁移脚本，禁止手工 ALTER 生产库
2. **空库验证**：每个迁移在空库通过 `alembic upgrade head` 验证后再合并；CI 流程为「先跑迁移 → 再 `scripts/ci_create_tables.py` create_all 补漏」，逐步收敛历史欠账
3. **每个迁移提供 downgrade**：支持回滚
4. **上线顺序**：迁库 → 后端发布（新代码兼容旧 schema 的灰度写法，如新字段全部带默认值）→ 前端发布
5. **生产执行**：alembic 迁移仍由 DBA 审阅后手动执行（对齐 CI/CD 现有约定，不进自动化）

---

## 六、实施路线图

### 6.1 排期（14 周）

| 周次 | 任务 | 交付物 |
|------|------|--------|
| **W0（v1.2 新增）** | 准备阶段：risk_history 冷启动基线回填、评分权重校准样本、50 条标注查询样本集（意图识别评测集）、Prompt 初始评测 | 基线数据 + 评测集 |
| W1 | F1.1 风险评分：数据模型 + 规则引擎（配置外置）+ API + **F4.1 反馈基础设施** | 后端 API + 可配置评分 |
| W2 | F1.1 前端：风险面板（breakdown + 趋势图）+ 列表风险列 + AiFeedback 组件接入 | 资产列表风险展示 + 反馈入口 |
| W3 | F1.2 资产关联：告警/事件关联 API + AI 摘要（带溯源） | 资产安全态势 Tab |
| W4 | F1.3 资产对账：对账逻辑 + 数据健康聚合页 + AI 报告 | 对账页面 + 数据健康入口 |
| W5 | F2.1 L1 查询：意图识别 + 参数提取 + 参数 chips 回显 | AI 查询 API + 前端输入框 |
| W6 | F2.1 查询优化 + 多轮对话 + 查询历史（重放） | 会话式查询体验 |
| W7 | F2.2 安全报告：数据完整性校验 + 报告生成 + AI 分析 | 周报/月报/事件驱动报告 |
| W8 | F2.3 知识库：自动提取 + rerank 搜索 + 老化队列 | 知识库列表 + 搜索页面 |
| W9-10 | F3.2 生命周期（预置 EOL 表 + 覆盖机制）+ F4.2 主动推送 | 退役提醒 + 场景化通知 |
| W11-12 | F3.3 合规基线（规则引擎 + AI 解读）+ F2.1 L2 复合查询（模板库） | 合规检查 + 模板化查询 |
| W13-14 | F3.1 变更影响分析（降级版：有限关联数据）+ 打磨与指标基线采集 | 影响评估页面 |

**里程碑**：
- Phase 1 后：资产详情页从"信息卡片"升级为"安全态势仪表盘"，且全部 AI 产物带反馈与溯源
- Phase 2 后：用户可以用中文和系统对话，获取安全洞察
- Phase 3/4 后：系统从被动查询变为主动防御与主动运营

### 6.2 优先级与 ROI 排序（v1.2 新增）

若资源受限按以下顺序裁剪/推进：

| 执行序 | 功能 | 理由 |
|--------|------|------|
| P0 | F1.1 风险评分（规则外置 + 可解释 + 趋势） | 立刻可见的核心价值 |
| P0 | F1.3 对账 + 数据健康聚合页 | 解决"台账不准"核心痛点 |
| P1 | F4.1 反馈闭环（随 F1.1 交付） | 横切基础，越早积累反馈越好 |
| P1 | F2.1 仅 L1 简单筛选 | 控制 MVP 范围，复合查询后置 |
| P1 | F2.2 安全报告（周报 + 事件驱动） | 业务价值高，硬性要求数据完整性校验 |
| P2 | F3.2 生命周期（预置 EOL 表） | 避免 WebSearch 幻觉 |
| P2 | F3.3 合规基线（规则引擎 + AI 解读） | 避免 AI 伪合规 |
| P2 | F4.2 主动推送 | 不做这个，AI 价值大打折扣 |
| P3 | F2.3 知识库 | ROI 中等，LLM rerank 起步够用 |
| P3 | F2.1 L2 复合查询 / F3.1 变更影响分析 | L2 依赖模板库打磨；F3.1 依赖资产关系建模（P5） |

---

## 七、竞品对照

本 PRD 中的功能与开源竞品的能力对比（v1.2 补齐 Ralph、OCS Inventory 两列）：

| 功能 | AI-miniSOC (本方案) | Snipe-IT | GLPI | NetBox | Ralph | OCS Inventory | 维易CMDB |
|------|-------------------|----------|------|--------|-------|---------------|---------|
| 资产台账 | ✅ 已有 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 自动发现 | ✅ Wazuh | ❌ | ✅ Agent | ❌ | ⚠️ Agent（数据中心向） | ✅ Agent | ✅ |
| 风险评分 | ✅ **AI增强+可解释** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| AI 查询 | ✅ **NL→意图/模板** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 安全报告 | ✅ **AI解读** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 资产对账 | ✅ **智能对账** | ❌ | ⚠️ 手动 | ❌ | ❌ | ❌ | ⚠️ |
| 知识库 | ✅ **AI积累** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 告警关联 | ✅ Wazuh深度 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

**差异化定位**：AI-miniSOC 的资产管理不是"又一个 Snipe-IT"，而是**以安全为中心、AI 驱动的智能资产运营平台**。竞品均无 AI 增强能力，这是核心差异化；同时本 PRD 坚持"判定交给规则、解读交给 AI"，避免把差异化建立在不可审计的 LLM 结论上。

---

## 八、风险与约束

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| GLM API 调用成本 | 高频查询可能产生费用 | 缓存策略 + 批量调用 + 按需触发 + §4.4 预算/熔断 |
| GLM API 不可用 | AI 功能降级 | 所有 AI 功能有非 AI 降级方案（逐功能降级行为见 §八-C） |
| NL 查询准确率 | 意图识别错误 | 限定 L1 支持查询类型 + 参数 chips 用户确认 + unsupported 诚实拒答 |
| 数据量增长 | 200 台规模下无压力 | 设计时考虑索引优化 |
| Wazuh API 限流 | 对账/同步受影响 | 控制请求频率 + 错误重试 |
| **AI 幻觉影响确定性结论**（v1.2 新增） | 合规误判、EOL 日期编造误导决策 | 确定性结论不交给 LLM：规则引擎 + 预置数据 + 人工确认，AI 只解读（F3.2/F3.3，原则 7） |
| **成本失控 / 重试风暴**（v1.2 新增） | 故障时重试放大 10x 调用 | §4.4 熔断为第一道防线 + 单日上限 + 缓存 + 月度成本报表 |
| **多用户并发与越权**（v1.2 新增） | 对账重复处理、越权操作 | 状态机校验防重复处理；权限矩阵（X1）+ 全写操作审计 |
| **知识老化**（v1.2 新增） | 过期知识误导后续排障 | last_validated_at + 待复审队列 + 置信度（F2.3） |

---

## 八-B、P4 数据可靠性依赖（执行前必读）

本 PRD 的 F1.1/F1.3/F2.2 强依赖采集、同步、日志、搜索链路。截至 2026-08-20，P4（数据可靠性）已**完成设计与部分骨架落地**（后台任务可观测性 `soc_task_executions`、源健康 `soc_source_health`、同步死信 `soc_sync_dead_letter`、自托管 runner CI/CD 全链路），但**核心修复项仍 open**。落地本 PRD 前必须正视以下已核实事实，并在实现中加入降级策略，否则产物会被脏数据污染：

| 本 PRD 功能 | 依赖链路 | P4 已知不可靠点（2026-08-16 核实） | 本 PRD 须采取的降级/对齐措施 |
|------|---------|------|------|
| F1.3 资产对账 | Wazuh API + `soc_sync_tasks`(36610 行) | 采集中断无感知（如 192.168.0.2 凌晨中断无监控）；对账结果 `task_id` 关联同步任务 | 对账结果须标注**数据新鲜度**（最近一次成功同步时间）；同步失败进 `soc_sync_dead_letter`，对账页面联动展示"源异常中，结果可能不全" |
| F1.1 风险评分（告警密度维度） | OpenSearch 告警聚合 / `soc_ai_analyses` | OpenSearch 双源字段结构不一致（`wazuh-states-*` 顶层 `vulnerability.*` vs `wazuh-alerts-*` `data.vulnerability.*`）；KEV∩漏洞对齐未建立 | 评分取数走 P0 已封装的聚合接口，不自行拼 OpenSearch 字段；源异常时回退到 `risk_scored_at` 上次缓存值并打标 |
| F2.2 安全报告（告警趋势段） | Loki 日志 + OpenSearch 趋势 | Loki `query_range` 默认 `limit=10000` 无分页循环 → **静默截断**；且仅 **7 天保留**；192.168.0.2 凌晨中断无监控 | 报告生成前校验时间窗数据完整性；对超出 7 天或缺失区间**显式提示"数据不全"**，禁止用空区间编造趋势 |
| F1.1/F2.2 脆弱性加权 | Wazuh 漏洞状态 / KEV | KEV∩漏洞 = 0 是 `cve_id` 对齐未建立（非 mock）；`has_exploit` 接 CISA KEV（P1 已落）但整体对齐待 P4 | 风险评分中"可利用性"维度在 KEV 对齐完成前用 `has_exploit` 字段兜底，标注口径版本 |

**执行建议**：
1. 本 PRD 的 MVP（F1.1 + F2.1 L1）可先于 P4 核心修复启动，但**对账（F1.3）与报告（F2.2）应与 P4 修复并行排期**，至少等"源健康可观测 + Loki 截断修复"后再正式发布。
2. 所有 AI 产物（摘要/报告）在底层数据不完整时必须**显式标注数据时效与缺口**，这是 P3 上线的硬性质量门槛（见 §八-C），不可静默。

---

## 八-C、AI 可解释性与反馈（上线质量门槛，v1.2 新增）

本节与 §八-B（数据可靠性）共同构成 P3 上线的**硬性质量门槛**，发布前逐项核验（见 §十一）：

1. **可解释**：风险评分必须可拆解到维度分数、规则命中与权重（`score_breakdown`），前端可见；"为什么这台是 85 分"必须可回答
2. **可溯源**：所有 AI 产物记录输入数据窗口、数据源、Prompt 版本、模型参数、token 用量（横切需求 X2），"AI 生成"角标点开可见
3. **可反馈**：所有 AI 产物带 👍/👎 反馈入口（F4.1）；👎 率 > 20% 的 AI 能力触发 Prompt 迭代评审
4. **可降级**：每个 AI 功能明确非 AI 降级行为——

| AI 功能 | 降级行为 |
|---------|---------|
| 风险摘要 | 展示 breakdown 规则化文案（如"开放 2 个高危端口，OS 落后 1 个大版本"） |
| 态势摘要 | 展示原始告警列表与统计数字，无摘要 |
| NL 查询 | 提示"AI 服务暂不可用"，引导使用常规筛选器 |
| 安全报告 | 输出数据附表（无 AI 解读章节），标注"解读生成失败" |
| 知识提取 | 事件关闭不阻塞，知识提取标记为待补，次日重试 |

5. **缺口显式**：数据不完整时显式标注时效与缺口，禁止编造（对齐 §八-B 执行建议第 2 条）

---

## 九、成功指标

| 指标 | 目标 |
|------|------|
| 资产台账准确率 | ≥95%（通过对账验证） |
| 高危资产识别率 | 100%（风险评分 >80 的资产全部可识别） |
| AI 查询准确率 | ≥80%（意图识别正确率） |
| 告警-资产关联率 | ≥90%（有 IP 的告警能关联到资产） |
| 安全报告生成时间 | ≤30 秒 |
| AI 调用成本（v1.2 新增） | ≤ ¥10/月（§4.4 预算，超限告警） |
| 摘要缓存命中率（v1.2 新增） | ≥ 60%（风险/态势摘要） |
| AI 反馈采纳率（v1.2 新增） | 👍 占比 ≥ 75%（月度，按 target_type 分列） |
| 用户价值（v1.2 新增） | 季度调研：≥70% 用户认为"节省排查时间 / 提前发现风险" |

**指标测量方法**：
- **资产台账准确率**：以 F1.3 对账的 `confirmed/resolved` 结果反推，公式 = 已确认一致资产数 / 台账总资产数；基线值于首次对账后记录，目标 ≥95%。
- **高危资产识别率**：风险评分 >80 的资产中经人工抽检确属高危的比例；抽检样本 ≥20 条/月。
- **AI 查询准确率**：从 `asset_query` 调用日志 + F4.1 反馈抽样，意图识别 + 参数提取 + 结果正确的占比；基线取首月实测，目标 ≥80%；W0 评测集作为回归基线。
- **告警-资产关联率**：有源 IP 的告警簇研判中成功落库 `soc_alert_group_analyses.linked_asset_id` 的比例（复用 P0 关联口径；v1.2.1 更正：该字段位于告警簇分析/快照表，`soc_assets` 上并无此字段）；基线取自 P0 运行统计。
- **安全报告生成时间**：端到端（触发 → GLM 返回 → 落库）的 P95 时延；取 30 次生成样本的中位数与 P95，目标 ≤30 秒。
- **AI 调用成本 / 缓存命中率**（v1.2）：token 用量与缓存命中在 X2 溯元数据中落库，月度汇总出报表。
- **AI 反馈采纳率**（v1.2）：`soc_ai_feedback` 月度聚合，👎 率 >20% 的能力触发 Prompt 迭代评审。
- **用户价值**（v1.2）：季度问卷（用户数少，用简式 NPS + 开放题），关注"节省工时"与"提前发现风险"两个自评项。

---

## 十、参考文档

| 文档 | 位置 |
|------|------|
| IT资产管理竞品分析 | `wiki/synthesis/it-asset-management-competitive-analysis.md` |
| LLM/Agent 应用场景 | `wiki/synthesis/llm-agent-in-itam.md` |
| CMDB/ASM 推荐方案 | `docs/design/cmdb-asset-management-asm-recommendations.md` |
| 产品愿景与技术路线 | `docs/design/product-vision-and-technical-roadmap.md` |
| 项目开发指南 | `CLAUDE.md` |

---

## 十一、Go/No-Go 自检清单（v1.2 新增）

发布前逐项确认，任一未通过则不发布（对应章节见括号）：

**数据与迁移**
- [ ] 全部 schema 变更已入 alembic 迁移，空库 `upgrade head` 通过，含 downgrade（§5.5）
- [ ] 对账页面展示源健康状态与"最近成功同步时间"，源异常有横幅提示（F1.3）
- [ ] 报告生成前完成时间窗数据完整性校验，缺口显式写入"数据说明"章节（F2.2）

**AI 质量**
- [ ] 风险评分 breakdown 前端可见；权重可配置且调整留审计（F1.1）
- [ ] 全部 AI 产物带反馈入口与溯源元数据（F4.1 / X2）
- [ ] 合规判定路径不含 LLM 调用（F3.3）；EOL 日期有来源标识 preset/manual（F3.2）
- [ ] §4.4 预算/限流/熔断参数生效，且演练过一次降级路径（§八-C）

**安全与权限**
- [ ] 权限矩阵（X1）逐功能落到 `require_menu_permission` + 前端 `v-auth`
- [ ] 对账处理 / 权重调整 / EOL 覆盖 / 知识编辑写操作落 `soc_audit_logs`（X1）
- [ ] NL 查询参数经白名单校验；系统中不存在任何 LLM 生成 SQL 的执行路径（F2.1）

**指标**
- [ ] §九 全部指标的采集点（日志/表字段）已实现，基线值已记录

---

## 十二、修订记录

| 版本 | 日期 | 修订内容 |
|------|------|---------|
| v1.0 | 2026-06-01 | 初稿（Draft），当时 P0/P1/P2 未启动 |
| v1.1 | 2026-08-20 | 基线对齐至 P2 交付：① §1.2 将"资产-告警关联/资产-事件关联"由「未完成」更正为「已完成（P0/P1）」，新增阶段基线说明；② F1.2 由"新建关联"改为"复用 P0/P1 已建关联 + AI 聚合摘要"；③ F1.1 告警密度数据来源改为复用 P0 `soc_ai_analyses`；④ 命名对齐：对账表 FK `sync_tasks` → `soc_sync_tasks`；⑤ §5.1 新增字段复用原则（复用 `data_classification`/`owner_contact`）；⑥ 新增 §八-B「P4 数据可靠性依赖」；⑦ §九 补成功指标测量方法；⑧ 文档状态/日期刷新 |
| v1.2 | 2026-08-21 | 评审修订（本轮重点：AI 可信度、成本、权限、反馈闭环四类横切缺口）：① **F2.1 拆分 L1/L2 两层能力**——L1 仅做单表筛选（意图+参数+chips 回显），L2 复合查询改"受限模板选择"方案，废弃硬塞 filter 参数的设计，新增多轮对话与查询历史重放；② **F1.1 评分规则外置可配置**（risk_rules.yaml）+ `score_breakdown` 可解释 + `soc_asset_risk_history` 趋势表 + 缺失维度降权 + GLM 摘要调用门槛（score≥60）；③ **F1.3 增数据新鲜度标注**、源健康/死信/对账三层边界澄清（新增"数据健康"聚合入口）、状态机防重复处理、处理落审计；④ **新增 Phase 4**：F4.1 AI 反馈闭环（`soc_ai_feedback` + 通用反馈组件，随 Phase 1 交付）、F4.2 主动推送（复用通知通道，5 类场景+频控）；⑤ **新增横切需求**：X1 权限矩阵（4 角色逐功能）、X2 AI 产物可追溯性（数据窗口/Prompt 版本/token 用量）；⑥ **F3.3 合规改"规则引擎判定 + AI 解读"双层**，判定不经过 LLM；**F3.2 EOL 改预置数据主路径**（弃 WebSearch 主路径）+ manual 覆盖；F3.1 补前置依赖（资产关系建模，降级口径诚实标注）；⑦ **新增 §4.4 预算与限流**（QPS/日限/熔断/调用量估算）、**§4.5 数据稀疏降级策略**、**§5.5 迁移策略**（alembic 空库验证，防漂移）、**§八-C 可解释性与反馈门槛**（含逐功能降级行为表）、**§十一 Go/No-Go 自检清单**；⑧ §六 加 W0 准备阶段（基线回填+评测集）、排期扩至 14 周、新增 6.2 ROI 裁剪排序；⑨ §七 竞品表补 Ralph/OCS Inventory；⑩ §八 风险表增 AI 幻觉/成本失控/并发越权/知识老化 4 行；⑪ §九 增成本/缓存命中率/反馈采纳率/用户价值 4 项指标及测量方法；⑫ F2.2 增事件驱动触发与 `data_coverage` 完整性校验；F2.3 检索改 LLM rerank 主路径（tsvector 降为可选）+ 知识老化字段与复审队列；⑬ §1.3 设计原则改为 7 条（增可解释可反馈可降级/成本可控/判定交给规则解读交给 AI） |
| v1.2.1 | 2026-08-21 | 可执行性核验后修订（对照代码库实测）：① F1.1 新增「与已有漏洞评分体系的关系」——系统已存在 `VulnerabilityAIService.calculate_risk_score`（CVSS 40%+关键度 25%+暴露面 20%+在野利用 15%），F1.1 资产评分与其是“资产聚合←漏洞明细”上下层关系而非平行体系，「系统健康度」维度消费漏洞评分输出，`exposure_level`/`criticality` 口径两套共享；② §九 告警-资产关联率口径更正：`linked_asset_id` 实际位于 `soc_alert_group_analyses`/`soc_alert_group_snapshots`（P0 落库位置），非 `soc_assets`；③ §五 表基线更正 24→40 张（实测；注：`app/models/__init__.py` 未导出全部模型，仅 `import app.models` 会误报 33 张），本 PRD 后为 45 张。MVP（F1.1+F4.1+F2.1-L1）于本日启动实施 |
| v1.2.1 | 2026-08-20 | 评审硬伤修正（主 Agent 直接修订，对应评审 3 处问题）：① **🔴 EOL 参考表落地**：F3.2 正文要求"落库 EOL 参考表"但 §5.3 无该表——新增 `soc_eol_reference` 表 DDL（§5.3）、`eol_reference.py` 模型（§4.3）、`idx_eol_reference_product` 索引（§5.4）；F3.2 与其对齐引用表名；§5.5 新表计数 `5 张` → `6 张`；② **🔴 X2 溯源字段落点纠错**：经代码核实 `soc_ai_analyses` 仅有 `model_name`/`model_version`/`tokens_used`，**无 `prompt_version` 列**——修正 X2 表，明确 Prompt 版本落 `soc_security_reports.prompt_version`（新增表）或 P0 现有 `model_version`，token 用量落现有 `tokens_used`，**不再要求为 `soc_ai_analyses` 新增列**（防执行时字段不存在报错）；③ **🟠 F4.2 跨模块依赖澄清**："数据链路异常"场景依赖 P4 `soc_source_health`，但 P4 仅被动落表无自动推送钩子——明确由 F4.2 自身轮询源健康表主动触发 critical 通知，不依赖 P4 回调 |
