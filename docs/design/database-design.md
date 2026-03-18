# AI-miniSOC 数据库设计文档

**文档版本**: v1.0
**创建日期**: 2026-03-18
**最后更新**: 2026-03-18
**数据库**: PostgreSQL 16
**字符集**: UTF-8

---

## 📋 目录

- [1. 概述](#1-概述)
- [2. 命名规范](#2-命名规范)
- [3. ER图](#3-er图)
- [4. 表结构详解](#4-表结构详解)
  - [4.1 资产表 (soc_assets)](#41-资产表-soc_assets)
  - [4.2 资产端口表 (soc_asset_ports)](#42-资产端口表-soc_asset_ports)
  - [4.3 事件表 (soc_incidents)](#43-事件表-soc_incidents)
  - [4.4 AI分析表 (soc_ai_analyses)](#44-ai分析表-soc_ai_analyses)
  - [4.5 资产标签表 (soc_asset_tags)](#45-资产标签表-soc_asset_tags)
  - [4.6 资产-事件关联表 (soc_asset_incidents)](#46-资产-事件关联表-soc_asset_incidents)
  - [4.7 事件时间线表 (soc_incident_timeline)](#47-事件时间线表-soc_incident_timeline)
- [5. 表关系图](#5-表关系图)
- [6. 索引设计](#6-索引设计)
- [7. 数据字典](#7-数据字典)
- [8. SQL示例](#8-sql示例)
- [9. 性能优化建议](#9-性能优化建议)

---

## 1. 概述

### 1.1 设计目标

AI-miniSOC 数据库设计遵循以下原则：

- **标准化**: 遵循第三范式（3NF），减少数据冗余
- **性能优化**: 合理使用索引、约束、数据类型
- **可扩展性**: 预留扩展字段，支持未来功能迭代
- **数据完整性**: 使用外键、CHECK约束、唯一约束
- **命名规范**: 统一使用 `soc_` 前缀

### 1.2 MVP v0.1 核心功能

- ✅ 资产管理（主机、端口、服务）
- ✅ 事件管理（工作流、状态流转）
- ✅ AI分析缓存（避免重复调用API）
- ✅ 标签系统（灵活分类）

### 1.3 技术栈

- **数据库**: PostgreSQL 16
- **连接信息**: 192.168.0.42:5432/AI-miniSOC-db
- **ORM**: SQLAlchemy 2.0 (async)
- **迁移工具**: Bytebase

---

## 2. 命名规范

### 2.1 表命名

- 格式：`soc_<module>_<entity>`
- 示例：`soc_assets`, `soc_incidents`, `soc_ai_analyses`
- 所有表使用小写字母和下划线

### 2.2 字段命名

- 使用小写字母和下划线
- 布尔字段：`is_<name>`, `has_<name>`
- 时间字段：`<action>_at`, `<action>_time`
- ID字段：`<entity>_id`, `<entity>_uuid`

### 2.3 索引命名

- 主键索引：`<table>_pkey`
- 唯一索引：`uq_<table>_<column>`
- 普通索引：`idx_<table>_<column>`
- 外键索引：`idx_<table>_<fk_column>`

### 2.4 约束命名

- 主键：`<table>_pkey`
- 外键：`fk_<table>_<referred>`
- 唯一约束：`uq_<table>_<column>`
- 检查约束：`<table>_<column>_check`

---

## 3. ER图

```
┌─────────────────┐
│   soc_assets    │
│   (资产表)       │
└────────┬────────┘
         │ 1
         │
         │ N
┌────────▼────────┐       ┌──────────────────┐
│soc_asset_ports  │       │ soc_asset_tags   │
│   (端口表)       │       │   (标签表)        │
└─────────────────┘       └──────────────────┘

┌─────────────────┐       ┌──────────────────┐
│  soc_incidents  │───────│soc_ai_analyses   │
│   (事件表)       │  1   1│  (AI分析)        │
└────────┬────────┘       └──────────────────┘
         │ 1
         │
         │ N
┌────────▼────────┐       ┌──────────────────┐
│soc_asset_incidents│     │soc_incident_timeline│
│  (资产-事件关联) │       │  (事件时间线)      │
└─────────────────┘       └──────────────────┘
```

---

## 4. 表结构详解

### 4.1 资产表 (soc_assets)

**用途**: 存储资产的基本信息和状态

#### 表结构

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | uuid | PRIMARY KEY | gen_random_uuid() | 主键 |
| asset_ip | inet | NOT NULL, UNIQUE | - | IP地址 |
| mac_address | macaddr | NULL | - | MAC地址 |
| name | varchar(255) | NULL | - | 资产名称 |
| asset_description | text | NULL | - | 资产描述 |
| asset_type | varchar(50) | NULL | 'other' | 资产类型 |
| criticality | varchar(20) | NULL | 'medium' | 重要性等级 |
| owner | varchar(255) | NULL | - | 负责人 |
| business_unit | varchar(255) | NULL | - | 业务单元 |
| asset_status | varchar(20) | NULL | - | 资产状态 |
| wazuh_agent_id | varchar(100) | NULL | - | Wazuh Agent ID |
| status_updated_at | timestamptz | NULL | - | 状态更新时间 |
| created_at | timestamptz | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | timestamptz | NOT NULL | CURRENT_TIMESTAMP | 更新时间 |

#### 索引

- `soc_assets_pkey` - 主键索引 (id)
- `soc_assets_asset_ip_key` - 唯一索引 (asset_ip)
- `idx_soc_assets_ip` - IP索引 (asset_ip)
- `idx_soc_assets_type` - 类型索引 (asset_type)
- `idx_soc_assets_criticality` - 重要性索引 (criticality)
- `idx_soc_assets_status` - 状态索引 (asset_status)
- `idx_soc_assets_wazuh_agent_id` - Wazuh Agent索引 (wazuh_agent_id)
- `idx_soc_assets_created_at` - 创建时间索引 (created_at DESC)

#### 枚举值

**asset_type**:
- `server` - 服务器
- `workstation` - 工作站
- `printer` - 打印机
- `router` - 路由器
- `switch` - 交换机
- `other` - 其他

**criticality**:
- `critical` - 关键
- `high` - 重要
- `medium` - 一般
- `low` - 低

**asset_status**:
- `active` - 在线
- `inactive` - 离线
- `retired` - 报废

---

### 4.2 资产端口表 (soc_asset_ports)

**用途**: 存储资产的开放端口和服务信息

#### 表结构

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | uuid | PRIMARY KEY | gen_random_uuid() | 主键 |
| asset_id | uuid | FOREIGN KEY | NULL | 关联资产ID |
| asset_ip | inet | NOT NULL | - | 关联资产IP |
| port | integer | NOT NULL | - | 端口号 |
| protocol | text | NOT NULL | 'tcp' | 协议类型 |
| state | text | NOT NULL | 'open' | 端口状态 |
| service | text | NULL | - | 服务名称 |
| version | text | NULL | - | 服务版本 |
| scan_time | timestamptz | NOT NULL | now() | 扫描时间 |
| service_banner | text | NULL | - | 服务指纹 |
| vulnerability | text | NULL | - | 漏洞信息 |
| last_seen | timestamptz | NULL | CURRENT_TIMESTAMP | 最后检测时间 |

#### 约束

- `unique_asset_port` - 唯一约束 (asset_ip, port, protocol)
- `asset_ports_asset_id_fkey` - 外键 → soc_assets(id) ON DELETE CASCADE

#### 索引

- `asset_ports_pkey` - 主键索引 (id)
- `idx_asset_ports_asset_ip` - IP索引 (asset_ip)
- `idx_soc_asset_ports_service` - 服务索引 (service)
- `idx_soc_asset_ports_protocol` - 协议索引 (protocol)
- `idx_soc_asset_ports_state` - 状态索引 (state)
- `idx_soc_asset_ports_scan_time` - 扫描时间索引 (scan_time DESC)
- `idx_soc_asset_ports_ip_port` - 复合索引 (asset_ip, port)

#### 枚举值

**protocol**:
- `tcp` - TCP协议
- `udp` - UDP协议

**state**:
- `open` - 开放
- `closed` - 关闭
- `filtered` - 过滤

---

### 4.3 事件表 (soc_incidents)

**用途**: 管理安全事件的生命周期

#### 表结构

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | uuid | PRIMARY KEY | gen_random_uuid() | 主键 |
| title | varchar(255) | NOT NULL | - | 事件标题 |
| description | text | NULL | - | 事件描述 |
| status | varchar(20) | NOT NULL | 'open' | 事件状态 |
| severity | varchar(20) | NOT NULL | 'medium' | 严重程度 |
| wazuh_alert_id | varchar(100) | NULL | - | Wazuh告警ID |
| assigned_to | varchar(255) | NULL | - | 负责人 |
| created_by | varchar(255) | NOT NULL | - | 创建人 |
| created_at | timestamptz | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | timestamptz | NOT NULL | CURRENT_TIMESTAMP | 更新时间 |
| resolved_at | timestamptz | NULL | - | 解决时间 |
| resolution_notes | text | NULL | - | 解决方案 |
| ai_analysis_id | uuid | FOREIGN KEY | NULL | AI分析ID |

#### 约束

- `soc_incidents_status_check` - CHECK (status IN ('open', 'in_progress', 'resolved', 'closed'))
- `soc_incidents_severity_check` - CHECK (severity IN ('critical', 'high', 'medium', 'low'))
- `fk_incidents_ai_analysis` - 外键 → soc_ai_analyses(id) ON DELETE SET NULL

#### 索引

- `soc_incidents_pkey` - 主键索引 (id)
- `idx_soc_incidents_status` - 状态索引 (status)
- `idx_soc_incidents_severity` - 严重程度索引 (severity)
- `idx_soc_incidents_created_at` - 创建时间索引 (created_at DESC)
- `idx_soc_incidents_wazuh_alert_id` - Wazuh告警索引 (wazuh_alert_id)
- `idx_soc_incidents_assigned_to` - 负责人索引 (assigned_to)

#### 枚举值

**status**:
- `open` - 待处理
- `in_progress` - 处理中
- `resolved` - 已解决
- `closed` - 已关闭

**severity**:
- `critical` - 严重
- `high` - 高
- `medium` - 中
- `low` - 低

---

### 4.4 AI分析表 (soc_ai_analyses)

**用途**: 缓存AI分析结果，避免重复调用API

#### 表结构

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | uuid | PRIMARY KEY | gen_random_uuid() | 主键 |
| alert_id | varchar(100) | UNIQUE, NOT NULL | - | Wazuh告警ID |
| alert_fingerprint | varchar(100) | NULL | - | 告警指纹 |
| explanation | text | NULL | - | AI解释 |
| risk_assessment | text | NULL | - | 风险评估 |
| recommendations | text | NULL | - | 处置建议 |
| model_name | varchar(100) | NOT NULL | - | 模型名称 |
| model_version | varchar(50) | NULL | - | 模型版本 |
| tokens_used | integer | NULL | - | Token消耗 |
| cost | numeric(10,4) | NULL | - | 成本（人民币） |
| created_at | timestamptz | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |
| expires_at | timestamptz | NULL | - | 过期时间 |

#### 约束

- `soc_ai_analyses_alert_id_key` - 唯一约束 (alert_id)

#### 索引

- `soc_ai_analyses_pkey` - 主键索引 (id)
- `idx_soc_ai_analyses_alert_id` - 告警ID索引 (alert_id)
- `idx_soc_ai_analyses_fingerprint` - 指纹索引 (alert_fingerprint)
- `idx_soc_ai_analyses_expires_at` - 过期时间索引 (expires_at)

---

### 4.5 资产标签表 (soc_asset_tags)

**用途**: 灵活的资产标签系统

#### 表结构

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | uuid | PRIMARY KEY | gen_random_uuid() | 主键 |
| asset_id | uuid | FOREIGN KEY, NOT NULL | - | 资产ID |
| tag_key | varchar(50) | NOT NULL | - | 标签键 |
| tag_value | varchar(100) | NOT NULL | - | 标签值 |
| created_at | timestamptz | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |

#### 约束

- `uq_asset_tag_key` - 唯一约束 (asset_id, tag_key)
- `fk_asset_tags_asset` - 外键 → soc_assets(id) ON DELETE CASCADE

#### 索引

- `soc_asset_tags_pkey` - 主键索引 (id)
- `idx_soc_asset_tags_asset` - 资产ID索引 (asset_id)
- `idx_soc_asset_tags_key_value` - 标签索引 (tag_key, tag_value)

#### 常用标签

**tag_key** 示例:
- `environment` - 环境（production, staging, development）
- `business_system` - 业务系统（hr-system, finance-system）
- `location` - 位置（beijing, shanghai）
- `team` - 团队（backend, frontend）

---

### 4.6 资产-事件关联表 (soc_asset_incidents)

**用途**: 多对多关系：一个事件可关联多个资产，一个资产可关联多个事件

#### 表结构

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| asset_id | uuid | FOREIGN KEY, NOT NULL | - | 资产ID |
| incident_id | uuid | FOREIGN KEY, NOT NULL | - | 事件ID |
| created_at | timestamptz | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |

#### 约束

- `soc_asset_incidents_pkey` - 复合主键 (asset_id, incident_id)
- `fk_asset_incidents_asset` - 外键 → soc_assets(id) ON DELETE CASCADE
- `fk_asset_incidents_incident` - 外键 → soc_incidents(id) ON DELETE CASCADE

#### 索引

- `soc_asset_incidents_pkey` - 复合主键索引
- `idx_soc_asset_incidents_asset` - 资产ID索引 (asset_id)
- `idx_soc_asset_incidents_incident` - 事件ID索引 (incident_id)

---

### 4.7 事件时间线表 (soc_incident_timeline)

**用途**: 记录事件的处理历史

#### 表结构

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | uuid | PRIMARY KEY | gen_random_uuid() | 主键 |
| incident_id | uuid | FOREIGN KEY, NOT NULL | - | 事件ID |
| action_type | varchar(50) | NOT NULL | - | 操作类型 |
| action_data | jsonb | NULL | - | 操作数据 |
| created_by | varchar(255) | NOT NULL | - | 操作人 |
| created_at | timestamptz | NOT NULL | CURRENT_TIMESTAMP | 操作时间 |

#### 约束

- `fk_incident_timeline_incident` - 外键 → soc_incidents(id) ON DELETE CASCADE

#### 索引

- `soc_incident_timeline_pkey` - 主键索引 (id)
- `idx_soc_incident_timeline_incident` - 事件ID索引 (incident_id)
- `idx_soc_incident_timeline_action_type` - 操作类型索引 (action_type)
- `idx_soc_incident_timeline_created_at` - 时间索引 (created_at DESC)

#### action_type 类型

- `status_change` - 状态变更
- `note` - 添加笔记
- `assignment` - 分配负责人
- `asset_linked` - 关联资产
- `resolved` - 事件解决
- `closed` - 事件关闭

#### action_data 示例

```json
// status_change
{
  "from": "open",
  "to": "in_progress",
  "reason": "开始调查"
}

// note
{
  "content": "已联系系统管理员确认",
  "attachments": ["screenshot.png"]
}

// assignment
{
  "to": "admin@example.com",
  "from": "security@example.com"
}
```

---

## 5. 表关系图

### 5.1 一对多关系

```
soc_assets (1) ───< (N) soc_asset_ports
    │                        主键: asset_id → soc_assets.id
    │                        级联删除: CASCADE

soc_assets (1) ───< (N) soc_asset_tags
    │                        主键: asset_id → soc_assets.id
    │                        级联删除: CASCADE

soc_incidents (1) ───< (N) soc_incident_timeline
                             主键: incident_id → soc_incidents.id
                             级联删除: CASCADE
```

### 5.2 多对多关系

```
soc_assets (N) ───< soc_asset_incidents >── (N) soc_incidents
                      复合主键: (asset_id, incident_id)
                      外键: asset_id → soc_assets.id
                      外键: incident_id → soc_incidents.id
                      级联删除: CASCADE
```

### 5.3 一对一关系

```
soc_incidents (1) ─── (1) soc_ai_analyses
                        外键: ai_analysis_id → soc_ai_analyses.id
                        级联删除: SET NULL
```

---

## 6. 索引设计

### 6.1 索引策略

#### 主键索引
- 所有表的 `id` 字段自动创建主键索引

#### 唯一索引
- `soc_assets.asset_ip` - 保证IP唯一
- `soc_asset_ports (asset_ip, port, protocol)` - 避免重复端口
- `soc_ai_analyses.alert_id` - 避免重复分析
- `soc_asset_tags (asset_id, tag_key)` - 每个资产每个标签键唯一

#### 外键索引
- 所有外键字段自动创建索引，优化JOIN查询

#### 查询优化索引
- **时间范围查询**: `created_at DESC`
- **状态筛选**: `status`, `severity`, `state`
- **关联查询**: `asset_id`, `incident_id`
- **复合索引**: `(asset_ip, port)` 优化组合查询

### 6.2 索引统计

| 表名 | 主键索引 | 唯一索引 | 普通索引 | 总计 |
|------|----------|----------|----------|------|
| soc_assets | 1 | 1 | 6 | 8 |
| soc_asset_ports | 1 | 1 | 5 | 7 |
| soc_incidents | 1 | 0 | 5 | 6 |
| soc_ai_analyses | 1 | 1 | 3 | 5 |
| soc_asset_tags | 1 | 1 | 2 | 4 |
| soc_asset_incidents | 1 | 0 | 2 | 3 |
| soc_incident_timeline | 1 | 0 | 3 | 4 |

---

## 7. 数据字典

### 7.1 通用字段

所有表都包含以下字段（或部分）：

| 字段名 | 类型 | 说明 | 使用场景 |
|--------|------|------|----------|
| id | uuid | 主键 | 所有表 |
| created_at | timestamptz | 创建时间 | 所有表 |
| updated_at | timestamptz | 更新时间 | soc_assets, soc_incidents |
| <entity>_id | uuid | 外键ID | 关联表 |

### 7.2 枚举值汇总

#### 资产类型 (asset_type)
```sql
'server', 'workstation', 'printer', 'router', 'switch', 'other'
```

#### 重要性等级 (criticality)
```sql
'critical', 'high', 'medium', 'low'
```

#### 资产状态 (asset_status)
```sql
'active', 'inactive', 'retired'
```

#### 协议类型 (protocol)
```sql
'tcp', 'udp'
```

#### 端口状态 (state)
```sql
'open', 'closed', 'filtered'
```

#### 事件状态 (status)
```sql
'open', 'in_progress', 'resolved', 'closed'
```

#### 事件严重程度 (severity)
```sql
'critical', 'high', 'medium', 'low'
```

---

## 8. SQL示例

### 8.1 资产查询

#### 查询所有活跃资产
```sql
SELECT
    id,
    asset_ip,
    name,
    asset_type,
    criticality,
    owner
FROM soc_assets
WHERE asset_status = 'active'
ORDER BY criticality DESC, created_at DESC;
```

#### 查询资产详情（含端口）
```sql
SELECT
    a.*,
    json_agg(
        json_build_object(
            'port', p.port,
            'protocol', p.protocol,
            'service', p.service,
            'state', p.state
        )
    ) AS ports
FROM soc_assets a
LEFT JOIN soc_asset_ports p ON a.id = p.asset_id
WHERE a.id = $1
GROUP BY a.id;
```

#### 按标签查询资产
```sql
SELECT DISTINCT a.*
FROM soc_assets a
JOIN soc_asset_tags t ON a.id = t.asset_id
WHERE t.tag_key = 'environment'
AND t.tag_value = 'production';
```

### 8.2 事件查询

#### 查询待处理的高危事件
```sql
SELECT
    id,
    title,
    severity,
    status,
    assigned_to,
    created_at
FROM soc_incidents
WHERE status IN ('open', 'in_progress')
AND severity IN ('critical', 'high')
ORDER BY severity DESC, created_at DESC;
```

#### 查询事件关联的所有资产
```sql
SELECT
    i.id AS incident_id,
    i.title,
    json_agg(
        json_build_object(
            'asset_ip', a.asset_ip,
            'name', a.name,
            'criticality', a.criticality
        )
    ) AS assets
FROM soc_incidents i
JOIN soc_asset_incidents ai ON i.id = ai.incident_id
JOIN soc_assets a ON ai.asset_id = a.id
WHERE i.id = $1
GROUP BY i.id;
```

### 8.3 AI分析查询

#### 查询告警的AI分析（带缓存检查）
```sql
SELECT
    id,
    alert_id,
    explanation,
    risk_assessment,
    recommendations,
    created_at,
    expires_at
FROM soc_ai_analyses
WHERE alert_id = $1
AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP);
```

#### 统计AI调用成本
```sql
SELECT
    model_name,
    COUNT(*) AS total_calls,
    SUM(tokens_used) AS total_tokens,
    SUM(cost) AS total_cost
FROM soc_ai_analyses
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY model_name
ORDER BY total_cost DESC;
```

### 8.4 复杂查询示例

#### 查询资产的完整信息
```sql
WITH asset_ports AS (
    SELECT
        asset_id,
        json_agg(
            json_build_object(
                'port', port,
                'protocol', protocol,
                'service', service,
                'state', state
            )
        ) AS ports
    FROM soc_asset_ports
    GROUP BY asset_id
),
asset_tags AS (
    SELECT
        asset_id,
        json_object_agg(tag_key, tag_value) AS tags
    FROM soc_asset_tags
    GROUP BY asset_id
),
asset_incidents AS (
    SELECT
        asset_id,
        COUNT(*) AS incident_count,
        SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS critical_count
    FROM soc_asset_incidents
    JOIN soc_incidents ON soc_asset_incidents.incident_id = soc_incidents.id
    WHERE soc_incidents.status != 'closed'
    GROUP BY asset_id
)
SELECT
    a.*,
    COALESCE(ap.ports, '[]'::json) AS ports,
    COALESCE(at.tags, '{}'::json) AS tags,
    COALESCE(ai.incident_count, 0) AS open_incidents,
    COALESCE(ai.critical_count, 0) AS critical_incidents
FROM soc_assets a
LEFT JOIN asset_ports ap ON a.id = ap.asset_id
LEFT JOIN asset_tags at ON a.id = at.asset_id
LEFT JOIN asset_incidents ai ON a.id = ai.asset_id
WHERE a.id = $1;
```

---

## 9. 性能优化建议

### 9.1 查询优化

#### 使用 EXPLAIN ANALYZE
```sql
EXPLAIN ANALYZE
SELECT * FROM soc_assets WHERE asset_status = 'active';
```

#### 避免 SELECT *
```sql
-- 不推荐
SELECT * FROM soc_assets;

-- 推荐
SELECT id, asset_ip, name FROM soc_assets;
```

#### 使用批量操作
```sql
-- 批量插入
INSERT INTO soc_asset_tags (asset_id, tag_key, tag_value)
VALUES
    (uuid1, 'environment', 'production'),
    (uuid2, 'environment', 'production'),
    (uuid3, 'environment', 'staging');
```

### 9.2 索引维护

#### 重建索引
```sql
REINDEX TABLE soc_assets;
REINDEX INDEX idx_soc_assets_ip;
```

#### 分析表统计信息
```sql
ANALYZE soc_assets;
VACUUM ANALYZE soc_assets;
```

### 9.3 分区策略（未来扩展）

当数据量增长时，考虑按时间分区：

```sql
-- 按月分区 soc_incidents
CREATE TABLE soc_incidents_2026_03 PARTITION OF soc_incidents
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
```

### 9.4 连接池配置

使用 PgBouncer 或 SQLAlchemy 连接池：

```python
# SQLAlchemy 连接池配置
engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600
)
```

### 9.5 监控指标

定期检查以下指标：

- 表大小：`pg_total_relation_size('soc_assets')`
- 索引使用率：`pg_stat_user_indexes`
- 慢查询：`pg_stat_statements`
- 缓存命中率：`pg_stat_database`

---

## 10. 备份与恢复

### 10.1 备份

```bash
# 备份所有 soc_ 表
pg_dump -h 192.168.0.42 -U postgres -d AI-miniSOC-db \
  -t 'soc_*' -f backup_soc_tables.sql

# 备份特定表
pg_dump -h 192.168.0.42 -U postgres -d AI-miniSOC-db \
  -t soc_assets -t soc_incidents -f backup_critical.sql
```

### 10.2 恢复

```bash
psql -h 192.168.0.42 -U postgres -d AI-miniSOC-db \
  -f backup_soc_tables.sql
```

---

## 11. 版本历史

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-03-18 | MVP v0.1 初始版本 | Claude |

---

## 12. 相关文档

- [命名规范](./database-naming-conventions.md)
- [产品路线图](./product-vision-and-technical-roadmap.md)
- [初始化指南](../installation/database-init-guide.md)

---

**文档维护**: 本文档应随数据库结构变更同步更新
**反馈**: 发现问题请提交 Issue 或 PR
