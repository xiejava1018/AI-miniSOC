# AI-miniSOC AI化资产管理模块 — 产品需求文档 (PRD)

**文档版本**: v1.0
**创建日期**: 2026-06-01
**最后更新**: 2026-06-01
**状态**: Draft

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
| 资产-告警关联 | ❌ 未完成 | 资产详情页查看关联告警 |
| 资产-事件关联 | ❌ 未完成 | 资产详情页查看关联事件 |

### 1.3 设计原则

1. **不重新发明轮子** — Wazuh 已有的能力直接复用，AI-miniSOC 专注于增值层
2. **AI 贯穿始终** — 每个功能模块都要考虑 AI 如何增强，而非事后加 AI
3. **小规模优先** — 面向 200 台以内部署，不追求企业级复杂度
4. **渐进式实现** — 分阶段交付，每阶段有独立可用价值

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

**数据来源**：
- 端口数据：`soc_asset_ports` 表
- OS 信息：Wazuh 同步的 `os_name` + `os_version`
- 告警数据：Wazuh API 查询该资产 IP 的近期告警
- 资产属性：`soc_assets` 表的 `criticality` 字段

**AI 增强**：
- 调用 GLM 对高风险资产生成一句话风险摘要
- 例："此服务器开放了 3389(RDP)、22(SSH)、445(SMB) 端口，运行已 EOL 的 CentOS 7，近 7 天有 23 条告警，风险评分 85/100"
- 风险摘要缓存 24 小时

**数据模型扩展**：
```sql
-- 新增字段到 soc_assets
ALTER TABLE soc_assets ADD COLUMN risk_score INTEGER DEFAULT 0;
ALTER TABLE soc_assets ADD COLUMN risk_summary TEXT;
ALTER TABLE soc_assets ADD COLUMN risk_scored_at TIMESTAMP WITH TIME ZONE;
```

**API 设计**：
```
GET  /api/v1/assets/{id}/risk          # 获取单个资产风险详情
POST /api/v1/assets/risk/batch-score   # 批量重新计算风险评分
GET  /api/v1/assets/risk/overview      # 风险总览（各分数段分布）
```

**前端展示**：
- 资产列表：新增"风险"列，用颜色标签显示（绿/黄/橙/红）
- 资产详情页：新增"风险概览"卡片，显示评分 + AI 摘要 + 各维度雷达图
- 仪表盘：风险分布饼图 + Top10 高风险资产列表

---

#### F1.2 资产-告警-事件关联

**优先级**: P0
**用户价值**: 资产详情页一目了然看到关联的安全事件

**功能描述**：
- 资产详情页新增"安全态势"Tab，展示：
  - 该资产 IP 近 7/30 天的告警列表（从 Wazuh API 查询）
  - 关联的安全事件列表（从 `soc_incidents` + `soc_asset_incidents` 查询）
  - AI 生成的该资产安全态势摘要

**AI 增强**：
- 对资产的告警历史进行 AI 聚合分析
- 输出："该服务器近 30 天收到 47 条告警，主要是 SSH 暴力破解（32次）和异常进程（8次）。SSH 攻击来自 3 个不同 IP，建议检查密码强度并考虑启用 fail2ban。"

**API 设计**：
```
GET /api/v1/assets/{id}/alerts         # 获取资产关联告警（代理 Wazuh 查询）
GET /api/v1/assets/{id}/incidents      # 获取资产关联事件
GET /api/v1/assets/{id}/security-summary  # AI 生成安全态势摘要
```

**前端展示**：
- 资产详情页新增 Tab："安全态势"
  - 安全摘要卡片（AI 生成）
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

**AI 增强**：
- 自动对账后生成 AI 分析报告
- 输出："本次对账发现 3 台影子资产和 2 台疑似下线设备。影子资产 192.168.0.67 是新加入的 Ubuntu 22.04 服务器，建议确认后补录台账。192.168.0.45 已断开超过 7 天，可能是已退役设备。"
- 对账结果可一键确认/忽略/补录

**数据模型扩展**：
```sql
-- 对账结果表
CREATE TABLE soc_asset_reconciliations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES sync_tasks(id),
    asset_id UUID REFERENCES soc_assets(id),
    reconciliation_type VARCHAR(20),  -- shadow, offline, mismatch, confirmed
    details JSONB,
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
PUT  /api/v1/assets/reconciliations/{id}/resolve  # 处理对账结果
GET  /api/v1/assets/reconcile/report   # AI 生成对账报告
```

**前端展示**：
- 资产管理菜单下新增"资产对账"页面
- 对账结果列表：差异类型标签 + 详情 + 操作按钮（确认补录/标记下线/忽略）
- 对账报告卡片（AI 生成）

---

### Phase 2：AI 智能交互

#### F2.1 自然语言资产查询

**优先级**: P1
**用户价值**: 用中文直接问资产相关问题，无需学习筛选器或 SQL

**功能描述**：
- 提供对话式查询入口，用户输入自然语言，系统返回资产列表或统计结果
- 支持的查询类型：

| 查询类型 | 示例 |
|---------|------|
| 条件筛选 | "3楼机房有哪些 Windows 服务器？" |
| 风险相关 | "哪些资产开放了 3389 端口？" |
| 状态查询 | "上次同步以来有哪些设备掉线了？" |
| 统计分析 | "按操作系统统计资产数量" |
| 关联查询 | "这台服务器上最近有什么告警？" |

**实现方案**：
- 不做 NL2SQL（复杂且不稳定），采用 **意图识别 + 参数提取 + API 映射**：
  1. GLM 识别查询意图（筛选/统计/关联）
  2. 提取结构化参数（资产类型、IP段、端口、状态等）
  3. 映射到已有的资产 API 查询参数
  4. 返回结果后 GLM 生成自然语言摘要

**AI Prompt 设计**：
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
3. 返回 JSON 格式

用户问题: {query}
```

**API 设计**：
```
POST /api/v1/assets/ask       # 自然语言查询
Body: { "question": "3楼机房哪些Windows没打补丁？" }
Response: {
  "intent": "filter",
  "params": { "network_segment": "3F", "os_name": "Windows" },
  "assets": [...],
  "summary": "在3楼机房找到 5 台 Windows 服务器，其中 2 台系统版本较旧..."
}
```

**前端展示**：
- 资产列表页顶部新增"AI 查询"输入框（类似搜索栏）
- 输入问题后展示结果列表 + AI 摘要
- 查询历史记录

---

#### F2.2 AI 安全报告解读

**优先级**: P1
**用户价值**: 将 Wazuh 扫描结果和告警数据转化为可操作的安全报告

**功能描述**：
- 定期（周/月）或按需生成安全报告，包含：
  - 资产安全总览：在线率、风险分布、高危资产 Top5
  - 告警趋势分析：近期告警数量变化、主要威胁类型
  - 风险发现：新开放的高危端口、EOL 系统、频繁告警资产
  - 处置建议：优先处理什么、具体操作步骤
- 报告以人话撰写，非原始数据堆砌

**AI 增强**：
- 调用 GLM 对安全数据进行整体分析，生成结构化报告
- 报告内容参考已有的告警分析 Prompt 风格（中文、分节、具体可操作）
- 报告缓存，支持历史查看

**数据模型扩展**：
```sql
CREATE TABLE soc_security_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type VARCHAR(20),  -- weekly, monthly, on_demand
    period_start TIMESTAMP WITH TIME ZONE,
    period_end TIMESTAMP WITH TIME ZONE,
    title VARCHAR(255),
    summary TEXT,             -- AI 生成的执行摘要
    content JSONB,            -- 报告各章节内容
    risk_highlights TEXT,     -- AI 生成的高亮风险
    recommendations TEXT,     -- AI 生成的处置建议
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**API 设计**：
```
POST /api/v1/reports/generate    # 生成报告（支持 weekly/monthly/on_demand）
GET  /api/v1/reports              # 报告列表
GET  /api/v1/reports/{id}         # 报告详情
```

**前端展示**：
- 侧边栏新增"安全报告"菜单
- 报告列表页：时间、类型、摘要预览
- 报告详情页：分节展示（总览→风险→告警→建议），支持导出 PDF

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

**AI 增强**：
- 对已解决的事件，AI 自动生成"故障→原因→解决方案"三元组
- 检索时用向量相似度匹配（简化方案：关键词 + GLM 语义匹配）

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
    search_vector TSVECTOR,   -- 全文搜索向量
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**API 设计**：
```
POST /api/v1/knowledge/search      # 自然语言搜索知识
GET  /api/v1/knowledge              # 知识列表
POST /api/v1/knowledge              # 手动创建知识条目
POST /api/v1/knowledge/auto-extract # 从已解决事件中自动提取知识
```

---

### Phase 3：AI 主动防御

#### F3.1 智能变更影响分析

**优先级**: P2
**用户价值**: 变更前评估影响范围，降低操作风险

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
- AI 定期检查厂商 EOL 公告（通过 WebSearch 或预置数据）
- 生成退役/升级建议列表

**数据模型扩展**：
```sql
ALTER TABLE soc_assets ADD COLUMN purchase_date DATE;
ALTER TABLE soc_assets ADD COLUMN warranty_end DATE;
ALTER TABLE soc_assets ADD COLUMN expected_EOL DATE;
```

#### F3.3 合规基线检查

**优先级**: P2
**用户价值**: 按等保/CIS 基线自动检查合规状态

**功能描述**：
- 基于已有资产数据（端口、OS、告警），对照等保二级或 CIS 基线
- AI 生成达标/不达标清单和整改建议
- 可生成审计报告

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
│  │  │意图识别   │ │风险评估   │ │报告生成/知识提取  ││ │
│  │  └──────────┘ └──────────┘ └───────────────────┘│ │
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
| 风险评分摘要 | 风险评分计算后 | GLM-4-flash | 缓存 24h |
| 安全态势摘要 | 用户访问资产详情时 | GLM-4-flash | 缓存 12h |
| 自然语言查询 | 用户输入时 | GLM-4-flash | 不缓存 |
| 对账报告 | 对账完成后 | GLM-4-flash | 缓存至下次对账 |
| 安全报告 | 定时/手动 | GLM-4-flash | 缓存至报告周期结束 |
| 知识提取 | 事件关闭时 | GLM-4-flash | 永久 |

### 4.3 新增文件清单

```
src/backend/app/
├── api/
│   ├── asset_risk.py           # F1.1 风险评分 API
│   ├── asset_reconciliation.py # F1.3 对账 API
│   ├── asset_query.py          # F2.1 自然语言查询 API
│   ├── reports.py              # F2.2 安全报告 API
│   └── knowledge.py            # F2.3 知识库 API
├── services/
│   ├── asset_risk.py           # 风险评分服务
│   ├── asset_reconciliation.py # 对账服务
│   ├── asset_query.py          # NL→意图识别→API映射
│   ├── report_generator.py     # 报告生成服务
│   └── knowledge_service.py    # 知识库服务
├── models/
│   ├── asset_reconciliation.py # 对账模型
│   ├── security_report.py      # 报告模型
│   └── knowledge.py            # 知识库模型
└── schemas/
    ├── asset_risk.py
    ├── reconciliation.py
    ├── report.py
    └── knowledge.py

src/frontend/src/
├── views/asset/
│   ├── AssetRiskPanel.vue      # 风险概览组件
│   ├── AssetReconciliation.vue # 对账页面
│   ├── AssetSecurityTab.vue    # 资产安全态势Tab
│   └── AssetAIQuery.vue        # AI 查询组件
├── views/report/
│   ├── ReportList.vue          # 报告列表
│   └── ReportDetail.vue        # 报告详情
└── views/knowledge/
    ├── KnowledgeList.vue       # 知识库列表
    └── KnowledgeSearch.vue     # 知识库搜索
```

---

## 五、数据库变更汇总

### 5.1 已有表扩展

```sql
-- soc_assets 新增字段
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS risk_score INTEGER DEFAULT 0;
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS risk_summary TEXT;
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS risk_scored_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS purchase_date DATE;
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS warranty_end DATE;
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS expected_EOL DATE;
```

### 5.2 新增表

```sql
-- 对账结果表
CREATE TABLE soc_asset_reconciliations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID,
    asset_id UUID REFERENCES soc_assets(id) ON DELETE SET NULL,
    reconciliation_type VARCHAR(20),  -- shadow, offline, mismatch, confirmed
    details JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    resolved_by VARCHAR(255),
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 安全报告表
CREATE TABLE soc_security_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type VARCHAR(20),
    period_start TIMESTAMP WITH TIME ZONE,
    period_end TIMESTAMP WITH TIME ZONE,
    title VARCHAR(255),
    summary TEXT,
    content JSONB,
    risk_highlights TEXT,
    recommendations TEXT,
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_reconciliations_status ON soc_asset_reconciliations(status);
CREATE INDEX idx_reconciliations_type ON soc_asset_reconciliations(reconciliation_type);
CREATE INDEX idx_reports_type ON soc_security_reports(report_type);
CREATE INDEX idx_reports_period ON soc_security_reports(period_start, period_end);
CREATE INDEX idx_kb_category ON soc_knowledge_base(category);
CREATE INDEX idx_kb_tags ON soc_knowledge_base USING GIN(tags);
```

---

## 六、实施路线图

### Phase 1：AI 资产感知与关联（3-4 周）

| 周次 | 任务 | 交付物 |
|------|------|--------|
| W1 | F1.1 风险评分：数据模型 + 评分服务 + API | 后端 API + 风险计算逻辑 |
| W2 | F1.1 前端：风险面板 + 列表风险列 | 资产列表风险展示 + 详情风险卡片 |
| W3 | F1.2 资产关联：告警/事件关联 API + AI 摘要 | 资产安全态势 Tab |
| W4 | F1.3 资产对账：对账逻辑 + AI 报告 | 对账页面 + 差异处理 |

**里程碑**：资产详情页从"信息卡片"升级为"安全态势仪表盘"

### Phase 2：AI 智能交互（3-4 周）

| 周次 | 任务 | 交付物 |
|------|------|--------|
| W5 | F2.1 自然语言查询：意图识别 + 参数提取 | AI 查询 API + 前端输入框 |
| W6 | F2.1 查询优化 + 查询历史 | 查询历史 + 结果展示优化 |
| W7 | F2.2 安全报告：报告生成 + AI 分析 | 周报/月报自动生成 |
| W8 | F2.3 知识库：自动提取 + 搜索 | 知识库列表 + 搜索页面 |

**里程碑**：用户可以用中文和系统对话，获取安全洞察

### Phase 3：AI 主动防御（4-6 周）

| 周次 | 任务 | 交付物 |
|------|------|--------|
| W9-10 | F3.1 变更影响分析 | 影响评估页面 |
| W11-12 | F3.2 资产生命周期 + F3.3 合规基线 | 退役提醒 + 合规检查 |

**里程碑**：系统从被动查询变为主动防御

---

## 七、竞品对照

本 PRD 中的功能与开源竞品的能力对比：

| 功能 | AI-miniSOC (本方案) | Snipe-IT | GLPI | NetBox | 维易CMDB |
|------|-------------------|----------|------|--------|---------|
| 资产台账 | ✅ 已有 | ✅ | ✅ | ✅ | ✅ |
| 自动发现 | ✅ Wazuh | ❌ | ✅ Agent | ❌ | ✅ |
| 风险评分 | ✅ **AI增强** | ❌ | ❌ | ❌ | ❌ |
| AI 查询 | ✅ **NL→API** | ❌ | ❌ | ❌ | ❌ |
| 安全报告 | ✅ **AI解读** | ❌ | ❌ | ❌ | ❌ |
| 资产对账 | ✅ **智能对账** | ❌ | ⚠️ 手动 | ❌ | ⚠️ |
| 知识库 | ✅ **AI积累** | ❌ | ❌ | ❌ | ❌ |
| 告警关联 | ✅ Wazuh深度 | ❌ | ❌ | ❌ | ❌ |

**差异化定位**：AI-miniSOC 的资产管理不是"又一个 Snipe-IT"，而是**以安全为中心、AI 驱动的智能资产运营平台**。所有竞品都没有 AI 增强能力，这是核心差异化。

---

## 八、风险与约束

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| GLM API 调用成本 | 高频查询可能产生费用 | 缓存策略 + 批量调用 + 按需触发 |
| GLM API 不可用 | AI 功能降级 | 所有 AI 功能有非 AI 降级方案 |
| NL 查询准确率 | 意图识别错误 | 限定支持查询类型 + 用户确认步骤 |
| 数据量增长 | 200 台规模下无压力 | 设计时考虑索引优化 |
| Wazuh API 限流 | 对账/同步受影响 | 控制请求频率 + 错误重试 |

---

## 九、成功指标

| 指标 | 目标 |
|------|------|
| 资产台账准确率 | ≥95%（通过对账验证） |
| 高危资产识别率 | 100%（风险评分 >80 的资产全部可识别） |
| AI 查询准确率 | ≥80%（意图识别正确率） |
| 告警-资产关联率 | ≥90%（有 IP 的告警能关联到资产） |
| 安全报告生成时间 | ≤30 秒 |

---

## 十、参考文档

| 文档 | 位置 |
|------|------|
| IT资产管理竞品分析 | `wiki/synthesis/it-asset-management-competitive-analysis.md` |
| LLM/Agent 应用场景 | `wiki/synthesis/llm-agent-in-itam.md` |
| CMDB/ASM 推荐方案 | `docs/design/cmdb-asset-management-asm-recommendations.md` |
| 产品愿景与技术路线 | `docs/design/product-vision-and-technical-roadmap.md` |
| 项目开发指南 | `CLAUDE.md` |
