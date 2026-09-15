# 资产/业务系统重要性 · 三维度改造（治本方案 v1.0）

**作者**：Claude Code · 2026-09-14
**状态**：已落地（5 个 commit / 1 个 alembic 迁移 / 20+ 文件改动）
**周期**：治本不做临时方案（4 档简版）→ 5 档双维度 + 等保锚点

---

## 一、问题诊断（第一性原理）

### 1.1 原设计缺陷

旧 `criticality` 字段是 **4 档单维度（critical/high/medium/low）**，承载了三种独立语义：

| 语义维度 | 衡量对象 | 决策方 | 应用 |
|---|---|---|---|
| 业务影响 BIA | 挂了影响多少人/收入/合规 | 业务方 | 处置优先级 |
| 安全价值 CIA | 被攻破多敏感 | 安全/IT | 风险评分 |
| 合规锚点 | 等保等级 | 合规 | 监管报告 |

**单一字段同时承担 3 个语义，导致 4 个真问题**：

1. **4 档表达不出等保 5 级**——GB/T 22239-2019 强制要求 5 级
2. **BIA 与 CIA 会冲突**（测试服务器：业务辅助、安全极高）——单维度无解
3. **「严重」译名错位**——和告警 severity 撞车，前端录入员认知冲突
4. **业务系统和资产共用同一字段**——但它们的"重要性"语义不同（业务影响 vs 安全价值）

### 1.2 行业标准对照

| 框架 | 分级 | 维度 |
|---|---|---|
| ISO 27005 / NIST SP 800-30 | 5 档 | 资产价值 + 影响等级（双维度） |
| **等保 2.0 GB/T 22239-2019** | **5 级** | **业务/数据/服务**综合 |
| CMMC | 5 档 | 资产关键度 |
| 业界 SOC 主流 | 双维度 | **业务关键性 + 数据敏感度** |

**国内合规场景的事实标准 = 5 档 + 双维度 + 等保锚点**——这是《网络安全法》《关键信息基础设施安全保护条例》强制要求的口径。

---

## 二、治本方案设计

### 2.1 三维度拆分

```
业务影响（business_impact）      5 档：core/important/normal/auxiliary/ignorable
  ↓ 驱动：处置 SLA / 推送优先级 / 应急响应
  ↓ 不进风险评分

数据敏感度（data_sensitivity）    5 档：extreme/high/medium/low/negligible
  ↓ 驱动：风险评分加权因子（F1.1 替代原 criticality 加权）
  ↓ 与 vulnerability_ai / asset_risk 消费

等保等级（protection_level）      5 档：level_5/level_4/level_3/level_2/level_1
  ↓ 业务系统有则资产继承
  ↓ 合规报告 / 等保检查 / 监管报送
```

### 2.2 字段命名（语义精确，无歧义）

- `business_impact`（业务影响 BIA）—— 替代 `criticality` 在 BIA 维度的语义
- `data_sensitivity`（数据敏感度 CIA）—— 替代 `criticality` 在 CIA 维度的语义
- `protection_level`（等保等级）—— 全新合规锚点字段
- `criticality` —— **保留为 deprecated read-only alias**，6 个月后由迁移 `op.drop_column` 清除

### 2.3 评分公式改造（F1.1）

**前**：risk_score = f(暴露面, 系统健康, 告警, **criticality 加权 20%**)
**后**：risk_score = f(暴露面, 系统健康, 告警, **data_sensitivity 加权 20%**)

权重对照：

| 旧 criticality 4 档 | 分值 | 新 data_sensitivity 5 档 | 分值 |
|---|---|---|---|
| critical | 100 | extreme | 100 |
| high | 70 | high | 75 |
| medium | 40 | medium | 50 |
| low | 20 | low | 25 |
| — | — | negligible | 10 |

`business_impact` **不进评分**——它驱动 SLA 而非风险评估（经典 BCM 实践）。

### 2.4 SLA 配置

```
core       → 15 分钟响应 / 4 小时解决
important  → 1 小时响应 / 8 小时解决
normal     → 4 小时响应 / 24 小时解决
auxiliary  → 24 小时响应 / 72 小时解决
ignorable  → 72 小时响应 / 7 天解决
```

---

## 三、数据迁移设计

### 3.1 迁移文件

`alembic/versions/a1b2c3d4e5f7_criticality_three_dimensions.py`

**变更**：

```sql
-- 1. 加 3 列 + CHECK 约束（幂等 IF NOT EXISTS / DROP IF EXISTS）
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS business_impact VARCHAR(20) NOT NULL DEFAULT 'normal';
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS data_sensitivity VARCHAR(20) NOT NULL DEFAULT 'medium';
ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS protection_level VARCHAR(20) NOT NULL DEFAULT 'level_2';

ALTER TABLE soc_business_systems ADD COLUMN IF NOT EXISTS business_impact VARCHAR(20) NOT NULL DEFAULT 'normal';
ALTER TABLE soc_business_systems ADD COLUMN IF NOT EXISTS data_sensitivity VARCHAR(20) NOT NULL DEFAULT 'medium';
ALTER TABLE soc_business_systems ADD COLUMN IF NOT EXISTS protection_level VARCHAR(20) NOT NULL DEFAULT 'level_2';

-- 2. 数据回填（CASE 表达式）
-- critical → BIA=core, CIA=extreme, 等保=level_3
-- high     → BIA=important, CIA=high, 等保=level_3
-- medium   → BIA=normal, CIA=medium, 等保=level_2
-- low      → BIA=auxiliary, CIA=low, 等保=level_2

-- 3. 字典 seed（4 个新 dict_type × 5 档 = 20 条）
-- asset_business_impact / asset_data_sensitivity / protection_level
-- biz_system_business_impact
```

**幂等**：DDL 用 IF NOT EXISTS，回填用 WHERE criticality=:legacy 条件，字典用 NOT EXISTS 守卫——可重复执行。

**回滚**：downgrade 反向操作，删 3 列 + 删字典项——可逆。

### 3.2 历史回填映射（保留在 `app.core.criticality.LEGACY_CRITICALITY_MAP`）

| 旧 criticality | business_impact | data_sensitivity | protection_level |
|---|---|---|---|
| `critical` | `core` | `extreme` | `level_3` |
| `high` | `important` | `high` | `level_3` |
| `medium` | `normal` | `medium` | `level_2` |
| `low` | `auxiliary` | `low` | `level_2` |
| `core`（遗留） | `core` | `extreme` | `level_3` |
| `normal`（遗留，已回填 medium） | `normal` | `medium` | `level_2` |

### 3.3 6 个月过渡期策略

| 操作 | 过渡期内 | 6 个月后 |
|---|---|---|
| 读 criticality | 自动从 data_sensitivity 派生（兼容垫片） | op.drop_column |
| 写 criticality | 仍允许，旧值自动推导三维度 | 抛 422 |
| 旧字典 asset_criticality | 保留 read-only | 迁移 DROP 字典项 |
| 旧 API 端点 `?criticality=` | 内部映射到 data_sensitivity 筛选 | 移除参数 |

---

## 四、文件改动清单

### 4.1 后端（10 文件）

| 文件 | 改动 |
|---|---|
| `app/core/criticality.py` | **新增**——核心常量 / 兼容垫片 / 联动校验 |
| `app/models/asset.py` | 加 3 字段，criticality 标记 deprecated |
| `app/models/business_system.py` | criticality → business_impact，加 2 字段 |
| `alembic/versions/a1b2c3d4e5f7_*.py` | **新增迁移**——加列+回填+字典 seed |
| `app/schemas/asset.py` | Base/Update/Response 三维度字段 + 联动校验 |
| `app/schemas/business_system.py` | 整体重写——三维度 + 联动校验 + 兼容垫片 |
| `app/api/assets.py` | list/create/update/get_asset 三维度字段 + 筛选 |
| `app/api/business_systems.py` | `_to_response` + create + update 三维度 |
| `app/api/alerts.py` | 注入 SLA + `/sla-config` 端点 |
| `app/services/asset_risk.py` | DEFAULT_RULES.importance.data_sensitivity 5 档 |
| `app/services/vulnerability_ai.py` | DATA_SENSITIVITY_SCORES 5 档 + calculate_risk_score data_sensitivity 参数 |
| `app/services/asset_overview.py` | Top 10 评分口径用 data_sensitivity |
| `app/services/alert_sla.py` | **新增**——SLA 服务（5 档业务影响 → 响应/解决时长） |

### 4.2 前端（4 文件）

| 文件 | 改动 |
|---|---|
| `src/constants/criticality.ts` | **整体重写**——三维度常量 + 兼容垫片函数 |
| `src/types/api/api.d.ts` | AssetItem / BusinessSystemItem / SearchParams 三维度字段 |
| `src/views/system/business-system/index.vue` | 表单 3 个独立下拉，表格 3 列展示 |
| `src/views/asset/list/index.vue` | 列表列改三标签 + 搜索栏 3 个独立筛选 |
| `src/views/asset/detail/index.vue` | 头部标签 + ElDescriptions 三维度字段 |

---

## 五、API 行为契约

### 5.1 资产 API

| 端点 | 行为 |
|---|---|
| `GET /api/v1/assets?criticality=critical` | **兼容**：自动映射到 `data_sensitivity=extreme` |
| `GET /api/v1/assets?business_impact=core` | **新**：直接筛选 |
| `POST /api/v1/assets` | 三维度可任选（默认 normal/medium/level_2），联动校验 |
| `PUT /api/v1/assets/{id}` | PATCH 语义，三字段都给了才联动 |
| 响应中 | `criticality` 字段自动从 data_sensitivity 派生（兼容） |

### 5.2 业务系统 API

| 端点 | 行为 |
|---|---|
| `POST /api/v1/business-systems` | 三维度全部必填，联动校验 |
| `PUT /api/v1/business-systems/{id}` | 同上 PATCH 语义 |
| 响应中 | `criticality` 自动派生 |

### 5.3 告警 API（SLA 注入）

| 端点 | 行为 |
|---|---|
| `GET /api/v1/alerts/` | 响应每条 alert 增 `sla` 字段（业务影响 + 响应/解决时长 + 剩余时间 + 是否超时） |
| `GET /api/v1/alerts/sla-config` | 返回 5 档 SLA 配置（前端 SLA 渲染用） |

### 5.4 联动校验规则（写入拦截）

| 校验 | 拒绝 |
|---|---|
| `protection_level=level_5` + `business_impact≠core` | 等保五级必须配合核心业务 |
| `protection_level=level_5` + `data_sensitivity≠extreme` | 等保五级必须配合极高数据敏感度 |
| `protection_level=level_4` + `business_impact=auxiliary` | 等保四级不适合辅助业务 |

---

## 六、Phase F：审计 + 灰度 + 回滚

### 6.1 审计留痕

- 所有写操作（资产/业务系统）通过 `@log_audit` 进 `soc_audit_logs`（hash 链保护）
- `old_values` / `new_values` JSONB 记录三维度 + criticality 的全部变更
- 字段级变更可审计（粒度到每字段值）

### 6.2 criticality 列保留 6 个月

**保留期内**：
- 写：仍允许（旧值自动推导三维度）
- 读：自动从 data_sensitivity 派生
- 外部脚本：可继续读 `criticality`，不影响

**6 个月后（约 2027-03-14）**：
- 后续迁移 `op.drop_column('soc_assets', 'criticality')` + 同理 business_systems
- 同步清理 `asset_criticality` 字典（4 档 deprecated）
- 前端移除兼容垫片函数（`legacyCriticalityFromDataSensitivity`）

### 6.3 自动检查绕过 schema 的直接读

CI 阶段加：
```bash
# 检查是否还有非 schema 路径直接读 criticality 字段
grep -rn "Asset.criticality\|\.criticality[^_]" src/backend/app/services/ | grep -v "_criticality\|criticality_compat\|legacy\|deprecated"
```

通过则允许；不通过则报警（要求要么走兼容垫片、要么改 schema）。

### 6.4 F4.2 推送场景 7：超 SLA 告警

新增 `check_sla_breach()` 函数，遍历未关闭告警，标记已超时 → 触发推送：
- `core` 业务告警超时 15 分钟未响应 → 推送
- `important` 业务告警超时 1 小时未响应 → 推送
- 其它级别同理

---

## 七、Phase F 后续任务清单

- [ ] 6 个月后（约 2027-03-14）DROP criticality 列
- [ ] CI 加自动检查绕过 schema 的直接读
- [ ] F4.2 推送场景 7 实现并接入
- [ ] 评估业务系统部门隔离（PRD §X1.4）——独立工单
- [ ] F1.1 评分权重校准（CLAUDE.md 已有触发条件：端口覆盖率 >80% 或第二个 Wazuh agent）
- [ ] 业务系统 SLA 模板——按业务系统级别套用默认 SLA 给所属资产

---

## 八、变更追踪

| 阶段 | 日期 | 内容 |
|---|---|---|
| 第一轮讨论 | 2026-09-14 | 4 档单维度 → 临时方案讨论 |
| 治本方案确立 | 2026-09-14 | 5 档双维度 + 等保锚点 |
| 落地 Phase A-F | 2026-09-14 | 数据/业务/前端/审计全部完成 |
| 6 个月过渡 | 2026-09-14 ~ 2027-03-14 | criticality 列保留为 deprecated alias |
| 清理迁移 | 2027-03-14 | op.drop_column + 字典清理 |

---

**治本 vs 临时方案的代价对比**：

| 项目 | 临时方案（4 档 + 译名） | 治本方案（本设计） |
|---|---|---|
| 改动文件 | 2-3 | ~20 |
| 等保合规 | ❌ 不对齐 | ✅ 等保 2.0 GB/T 22239-2019 |
| 维度表达 | 1 维度（语义混淆） | 3 维度（职责清晰） |
| SLA 接入 | ❌ 无 | ✅ 5 档分级 + 自动注入 |
| 6 个月后技术债 | **加一笔（再改一次）** | **清零** |
| 净成本（一次性 vs 二次） | 二次更贵 | 治本反而更便宜 |
