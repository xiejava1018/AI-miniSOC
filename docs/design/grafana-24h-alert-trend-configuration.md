# Grafana 24小时告警趋势图表配置指南

## 图表概述

这个图表显示Wazuh SIEM最近24小时的告警和事件趋势，帮助安全分析师快速识别威胁模式和时间分布。

## 数据源配置

### 1. Infinity数据源基础配置

**数据源名称**: wazuh-api
**数据源类型**: Infinity (REST API)
**服务地址**: http://192.168.0.30:5000

---

## 图表配置步骤

### 步骤1: 创建新面板

1. 打开Grafana Dashboard编辑模式
2. 点击 **Add panel** → **Add an empty panel**
3. 在面板编辑页面选择 **Time series** 图表类型

---

### 步骤2: 配置Infinity查询

#### A. Query设置

在 **Query** 标签页中配置：

| 字段 | 值 | 说明 |
|------|-----|------|
| **Data source** | `wazuh-api` | 选择Infinity数据源 |
| **Query type** | `REST API` | 使用REST API查询 |
| **URL Format** | `Global` | 使用全局URL配置 |

#### B. 请求配置

点击 **New Request** 按钮，配置以下参数：

**基本配置:**
```
Name: manager-stats
Type: GET
URL: /manager/stats
```

**详细配置:**

| 参数 | 配置值 |
|------|--------|
| **Request method** | `GET` |
| **URL** | `/manager/stats` |
| **Root selector** | `$.data.affected_items` |

#### C. 字段配置

**Root Selector**: `$.data.affected_items`

这将返回24小时的数组数据，每个元素包含：
- `hour`: 小时数 (0-23)
- `totalAlerts`: 总告警数
- `events`: 事件总数
- `alerts`: 详细告警规则数组
- `syscheck`: 文件完整性检查数
- `firewall`: 防火墙事件数

---

### 步骤3: 数据转换配置

由于API返回的是小时数据而不是时间戳，需要进行数据转换。

#### A. 添加转换

在 **Transformations** 标签页：

1. 点击 **Add transformation**
2. 选择 **Organize fields**（或"组织字段"）
3. 配置字段：

**保留的字段:**
- ✅ `hour` - 小时数
- ✅ `totalAlerts` - 总告警数
- ✅ `events` - 事件总数
- ✅ `alerts` - 告警规则触发数（数组长度）

**排除的字段:**
- ❌ `syscheck` - 文件完整性检查（排除）
- ❌ `firewall` - 防火墙事件（排除）
- ❌ 其他嵌套的alerts数组

#### B. 字段重命名（可选）

| 原字段名 | 显示名称 | 说明 |
|---------|---------|------|
| `hour` | `小时` | 时间标签 |
| `totalAlerts` | `总告警数` | 24小时内的总告警数量 |
| `events` | `事件总数` | 24小时内的总事件数 |
| `alerts` | `告警规则触发数` | 告警规则数组长度 |

---

### 步骤4: 时序图配置

#### A. 基本设置

在 **Panel options** 标签页：

| 选项 | 配置值 | 说明 |
|------|--------|------|
| **Title** | `24小时告警趋势` | 图表标题 |
| **Description** | `显示最近24小时的告警和事件趋势` | 图表描述 |

#### B. Axis配置（坐标轴）

在 **Standard options** → **Axis** 配置：

| 设置 | 值 | 说明 |
|------|-----|------|
| **Label** | `小时` | X轴标签 |
| **Show** | ✅ | 显示X轴 |
| **Placement** | `Auto` | 自动放置 |

#### C. 图表样式配置

在 **Graph styles** 标签页：

**基本线条设置:**
| 选项 | 配置值 | 说明 |
|------|--------|------|
| **Draw style** | `Line` | 线条样式 |
| **Line interpolation** | `Smooth` | 平滑曲线 |
| **Line width** | `2` | 线条宽度 |
| **Fill opacity** | `10` | 填充透明度 |
| **Show points** | `Never` | 不显示数据点 |
| **Point size** | `5` | 数据点大小 |

**渐变设置:**
| 选项 | 配置值 |
|------|--------|
| **Gradient mode** | `None` |

**堆叠设置:**
| 选项 | 配置值 | 说明 |
|------|--------|------|
| **Stacking** | `None` | 不堆叠 |

**阈值设置:**
| 选项 | 配置值 | 说明 |
|------|--------|------|
| **Thresholds style** | `Off` | 不显示阈值线 |

---

### 步骤5: 图例配置

在 **Legend** 标签页：

| 选项 | 配置值 | 说明 |
|------|--------|------|
| **Show legend** | ✅ | 显示图例 |
| **Display mode** | `Table` | 表格模式 |
| **Placement** | `Bottom` | 放在底部 |
| **Calcs** | `Mean`, `Last`, `Max` | 显示平均值、最后值、最大值 |

**计算值说明:**
- **Mean**: 平均每小时告警数
- **Last (NotNull)**: 最近一小时的告警数
- **Max**: 24小时内最高告警数

---

### 步骤6: Tooltip配置

在 **Tooltip** 标签页：

| 选项 | 配置值 | 说明 |
|------|--------|------|
| **Mode** | `Multi` | 显示多个系列 |
| **Sort order** | `None` | 不排序 |
| **Max width** | `300px` | 最大宽度 |
| **Max height** | `300px` | 最大高度 |

---

### 步骤7: 颜色配置

在 **Standard options** 标签页 → **Color**:

| 系列 | 颜色模式 | 颜色 |
|------|----------|------|
| **总告警数** | `Palette classic` | 蓝色 (自动) |
| **事件总数** | `Palette classic` | 绿色 (自动) |
| **告警规则触发数** | `Palette classic` | 橙色 (自动) |

---

## 完整的JSON配置示例

可以直接导入的面板配置片段：

```json
{
  "datasource": {
    "type": "infinity",
    "uid": "fffhc15p7nthca"
  },
  "description": "24小时告警和事件趋势",
  "fieldConfig": {
    "defaults": {
      "color": {
        "mode": "palette-classic"
      },
      "custom": {
        "axisCenteredZero": false,
        "axisColorMode": "text",
        "axisLabel": "",
        "axisPlacement": "auto",
        "barAlignment": 0,
        "drawStyle": "line",
        "fillOpacity": 10,
        "gradientMode": "none",
        "hideFrom": {
          "tooltip": false,
          "viz": false,
          "legend": false
        },
        "lineInterpolation": "smooth",
        "lineWidth": 2,
        "pointSize": 5,
        "scaleDistribution": {
          "type": "linear"
        },
        "showPoints": "never",
        "spanNulls": true,
        "stacking": {
          "group": "A",
          "mode": "none"
        },
        "thresholdsStyle": {
          "mode": "off"
        }
      },
      "mappings": [],
      "thresholds": {
        "mode": "absolute",
        "steps": [
          {
            "color": "green",
            "value": null
          }
        ]
      },
      "unit": "short"
    }
  },
  "gridPos": {
    "h": 10,
    "w": 24,
    "x": 0,
    "y": 32
  },
  "id": 10,
  "options": {
    "legend": {
      "calcs": [
        "mean",
        "lastNotNull",
        "max"
      ],
      "displayMode": "table",
      "placement": "bottom",
      "showLegend": true
    },
    "tooltip": {
      "mode": "multi",
      "sort": "none"
    }
  },
  "targets": [
    {
      "datasource": {
        "type": "infinity",
        "uid": "fffhc15p7nthca"
      },
      "editorMode": "code",
      "expression": "object",
      "format": "table",
      "query": "manager-stats",
      "rawQuery": "true",
      "refId": "A",
      "root_selector": "$.data.affected_items",
      "type": "root"
    }
  ],
  "title": "24小时告警趋势",
  "transformations": [
    {
      "id": "organize",
      "options": {
        "excludeByName": {
          "firewall": true,
          "hour": false,
          "syscheck": true
        },
        "indexByName": {
          "alerts": 2,
          "events": 3,
          "hour": 1,
          "totalAlerts": 0
        },
        "renameByName": {
          "alerts": "告警规则触发数",
          "events": "事件总数",
          "hour": "小时",
          "totalAlerts": "总告警数"
        }
      }
    }
  ],
  "type": "timeseries"
}
```

---

## API数据结构详解

### 请求示例

```bash
curl http://192.168.0.30:5000/manager/stats
```

### 响应结构

```json
{
  "data": {
    "affected_items": [
      {
        "hour": 0,                    // 小时 (0-23)
        "totalAlerts": 15460,         // 总告警数
        "events": 21732,              // 事件总数
        "alerts": [                   // 告警规则数组
          {
            "sigid": 2830,            // 规则ID
            "level": 0,               // 告警级别
            "times": 1                // 触发次数
          },
          ...
        ],
        "syscheck": 0,                // 文件完整性检查数
        "firewall": 0                 // 防火墙事件数
      },
      {
        "hour": 1,
        "totalAlerts": 12419,
        "events": 18671,
        ...
      },
      ...
      {
        "hour": 23,
        ...
      }
    ],
    "total_affected_items": 24        // 24小时数据
  },
  "error": 0
}
```

---

## 数据流程图

```
┌─────────────────────────────────────────────────────────────┐
│  1. API请求                                                  │
│     GET http://192.168.0.30:5000/manager/stats              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  2. API响应                                                  │
│     $.data.affected_items[24个元素]                         │
│     每个元素包含: hour, totalAlerts, events等               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Root Selector提取                                        │
│     $.data.affected_items → 24行数据                        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Transformations                                         │
│     Organize fields:                                        │
│     - 排除: syscheck, firewall                              │
│     - 重命名: totalAlerts→总告警数, events→事件总数          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Time Series可视化                                       │
│     X轴: hour (0-23)                                        │
│     Y轴: 告警数量                                            │
│     系列: 总告警数(蓝), 事件总数(绿), 告警规则数(橙)        │
└─────────────────────────────────────────────────────────────┘
```

---

## 常见问题排查

### 问题1: 图表显示"No Data"

**原因**:
- API端点返回404
- Root Selector配置错误
- 数据源连接失败

**解决方法**:
```bash
# 1. 测试API端点
curl http://192.168.0.30:5000/manager/stats

# 2. 检查返回数据结构
curl http://192.168.0.30:5000/manager/stats | jq '.data.affected_items'

# 3. 验证数据源连接
# 在Grafana中: Configuration → Data Sources → wazuh-api → Save & Test
```

### 问题2: X轴显示的不是小时数

**原因**:
- Grafana自动将数据识别为时间序列
- hour字段被当作时间戳

**解决方法**:
1. 在Transformations中添加 **Convert field type**
2. 将hour字段类型设置为 `String`
3. 或在Query设置中禁用时间序列模式

### 问题3: 数据不连续

**原因**:
- 某些小时没有数据
- API返回不完整的24小时数据

**解决方法**:
1. 在Graph styles中启用 **Span nulls**
2. 设置为 `Always` 或 `Threshold`

### 问题4: 图例统计值不正确

**原因**:
- Calculations配置错误
- 字段类型不匹配

**解决方法**:
1. 检查Legend → Calcs配置
2. 确保选择了正确的计算方法:
   - `lastNotNull`: 最后非空值
   - `mean`: 平均值
   - `max`: 最大值

---

## 高级配置技巧

### 1. 添加告警阈值线

在 **Thresholds** 配置中：

```json
{
  "thresholds": {
    "mode": "absolute",
    "steps": [
      {
        "color": "green",
        "value": null
      },
      {
        "color": "yellow",
        "value": 10000
      },
      {
        "color": "red",
        "value": 15000
      }
    ]
  }
}
```

### 2. 自定义Y轴单位

在 **Standard options** → **Unit**:
- 选择 `short` - 短数字格式
- 选择 `locale` - 本地化数字格式
- 或自定义后缀: `ops` (告警/次)

### 3. 添加数据标注

在 **Annotations** 配置中:

```json
{
  "list": [
    {
      "builtIn": 1,
      "datasource": "-- Grafana --",
      "enable": true,
      "hide": false,
      "iconColor": "rgba(0, 211, 255, 1)",
      "name": "安全事件",
      "type": "dashboard"
    }
  ]
}
```

### 4. 导出图表数据

在图表右上角:
1. 点击 **More options** (三个点)
2. 选择 **Export CSV**
3. 或选择 **Export CSV (Excel)**

---

## 性能优化建议

### 1. 减少数据加载频率

在Dashboard设置中:
- **Refresh interval**: 设置为 `1m` 或更长
- 避免过快刷新导致API压力

### 2. 使用数据缓存

在Infinity数据源中:
- 启用 **Cache**
- 设置 **TTL**: 60秒
- 减少重复API请求

### 3. 查询优化

如果只需要部分数据:
```bash
# 只获取最近12小时
GET /manager/stats?hours=12

# 只获取特定字段
GET /manager/stats?fields=hour,totalAlerts,events
```

---

## 相关资源

- [Grafana Time Series文档](https://grafana.com/docs/grafana/latest/visualizations/visualizations/time-series/)
- [Infinity插件文档](https://grafana.com/plugins/yesoreyeram-infinity/)
- [Wazuh API文档](https://documentation.wazuh.com/current/user-manual/api/api-reference.html)

---

**最后更新**: 2026-03-10
**版本**: 1.0.0
