# AI-miniSOC 数据库命名规范

**版本**: v1.0
**创建日期**: 2026-03-18
**状态**: 生效

---

## 🔤 表命名规范

### 前缀规则

**所有表必须使用 `soc_` 作为前缀**

**格式**: `soc_<模块名>_<实体名>`

**示例**:
- ✅ `soc_assets` - 资产表
- ✅ `soc_asset_ports` - 资产端口表
- ✅ `soc_incidents` - 安全事件表
- ✅ `soc_incident_timeline` - 事件时间线表
- ✅ `soc_ai_analyses` - AI分析缓存表
- ✅ `soc_asset_tags` - 资产标签表
- ✅ `soc_users` - 用户表
- ✅ `soc_alerts` - 告警表

### 命名原则

1. **使用小写字母**
   - ✅ `soc_assets`
   - ❌ `SOC_Assets`

2. **使用下划线分隔单词**
   - ✅ `soc_asset_ports`
   - ❌ `socassetports`

3. **使用复数形式表示实体**
   - ✅ `soc_assets`
   - ❌ `soc_asset`

4. **简洁且有意义**
   - ✅ `soc_incident_timeline`
   - ❌ `soc_table_for_storing_incident_timeline_events`

---

## 📋 MVP v0.1 核心表清单

### 已实现的表

| 表名 | 说明 | 创建日期 |
|------|------|----------|
| `soc_assets` | 安全资产表 | 2026-03-10 |
| `soc_asset_ports` | 资产端口表 | 2026-03-18 |

### MVP v0.1 需要新增的表

| 表名 | 说明 | 优先级 | 状态 |
|------|------|--------|------|
| `soc_incidents` | 安全事件表 | 🔴 高 | 待创建 |
| `soc_incident_assets` | 事件-资产关联表 | 🔴 高 | 待创建 |
| `soc_incident_timeline` | 事件时间线表 | 🔴 高 | 待创建 |
| `soc_ai_analyses` | AI分析缓存表 | 🔴 高 | 待创建 |
| `soc_asset_tags` | 资产标签表 | 🟡 中 | 待创建 |
| `soc_users` | 用户表 | 🟡 中 | 待创建 |

### v0.2+ 规划的表

| 表名 | 说明 | 优先级 |
|------|------|--------|
| `soc_vulnerabilities` | 漏洞表 | 🟢 低 |
| `soc_threat_intel` | 威胁情报表 | 🟢 低 |
| `soc_compliance_reports` | 合规报告表 | 🟢 低 |
| `soc_playbooks` | 响应剧本表 | 🟢 低 |

---

## 🔤 字段命名规范

### 通用字段（所有表必备）

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `id` | SERIAL/BIGINT | 主键 | 1, 2, 3 |
| `created_at` | TIMESTAMP | 创建时间 | 2026-03-18 10:00:00 |
| `updated_at` | TIMESTAMP | 更新时间 | 2026-03-18 11:00:00 |

### 资产相关字段

| 字段名 | 类型 | 说明 | 约束 |
|--------|------|------|------|
| `asset_ip` | INET | IP地址 | UNIQUE |
| `asset_name` | VARCHAR(255) | 资产名称 | NOT NULL |
| `asset_type` | VARCHAR(50) | 资产类型 | CHECK约束 |
| `asset_status` | VARCHAR(20) | 资产状态 | CHECK约束 |

### 关联字段命名

**格式**: `<关联表>_id`

**示例**:
- ✅ `wazuh_agent_id` - 关联Wazuh Agent
- ✅ `incident_id` - 关联事件
- ✅ `asset_id` - 关联资产
- ✅ `created_by` - 创建者
- ✅ `assigned_to` - 分配给

---

## 🗂️ 索引命名规范

**格式**: `idx_<表名>_<字段名>`

**示例**:
- ✅ `idx_soc_assets_ip`
- ✅ `idx_soc_assets_wazuh`
- ✅ `idx_incidents_status`
- ✅ `idx_ai_analyses_alert_id`

### 特殊索引

| 类型 | 命名格式 | 示例 |
|------|----------|------|
| 唯一索引 | `uidx_<表名>_<字段名>` | `uidx_soc_assets_ip` |
| 全文索引 | `ftidx_<表名>_<字段名>` | `ftidx_incidents_description` |
| 复合索引 | `idx_<表名>_<字段1>_<字段2>` | `idx_incidents_status_created` |

---

## 🔒 约束命名规范

**格式**: `<约束类型>_<表名>_<字段名>_check`

**示例**:
- ✅ `soc_assets_asset_type_check`
- ✅ `soc_assets_criticality_check`
- ✅ `soc_incidents_status_check`

---

## 🔧 触发器命名规范

**格式**: `trigger_<功能>_<表名>_<动作>`

**示例**:
- ✅ `trigger_update_soc_assets_updated_at`
- ✅ `trigger_log_soc_incidents_changes`
- ✅ `trigger_audit_soc_users_login`

---

## 📝 函数命名规范

**格式**: `<功能>_<表名>_<动作>`

**示例**:
- ✅ `update_soc_assets_updated_at()`
- ✅ `create_soc_incident_from_alert()`
- ✅ `get_soc_asset_by_ip()`

---

## 🎯 命名最佳实践

### ✅ 推荐做法

1. **保持一致性**
   ```sql
   -- 所有时间字段统一使用 _at 后缀
   created_at, updated_at, deleted_at, resolved_at

   -- 所有ID字段统一使用 _id 后缀
   user_id, asset_id, incident_id
   ```

2. **使用业务术语**
   ```sql
   -- ✅ 好
   asset_type, criticality, owner

   -- ❌ 不好
   type_of_asset, importance_level, person_in_charge
   ```

3. **布尔值字段使用 is_/has_ 前缀**
   ```sql
   is_active, is_deleted, has_wazuh_agent
   ```

### ❌ 避免的做法

1. **避免缩写（除非是通用缩写）**
   ```sql
   -- ❌ 不好
   ast_typ, own, biz_unit

   -- ✅ 好
   asset_type, owner, business_unit
   ```

2. **避免保留字**
   ```sql
   -- ❌ 不好
   user, order, group, select

   -- ✅ 好
   soc_user, purchase_order, user_group, select_query
   ```

3. **避免数字后缀**
   ```sql
   -- ❌ 不好
   column1, column2, field_2026

   -- ✅ 好
   primary_column, secondary_column, vintage_year
   ```

---

## 📚 参考资源

- PostgreSQL命名规范: https://www.postgresql.org/docs/current/sql-syntax-lexical.html
- 数据库设计最佳实践: https://schema.org/

---

## 🔄 版本历史

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-03-18 | 初始版本，确立soc_前缀规范 | Claude |

---

**重要提醒**:
1. 所有新增表必须遵循此规范
2. 命名必须在代码审查时检查
3. 不符合规范的表必须重命名
