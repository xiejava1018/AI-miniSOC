# Grafana Infinity 配置指南 - 调用Wazuh API

## 📋 配置步骤概览

1. ✅ Infinity插件已安装 (v3.7.3)
2. ✅ Grafana已重启
3. 🔧 接下来：配置Infinity数据源
4. 🎨 创建Dashboard面板

---

## 🚀 步骤1: 配置Infinity数据源

### 1.1 打开数据源配置页面

访问Grafana并登录：
```
URL: https://grafana.xiejava.dpdns.org
用户: admin
密码: <见环境变量配置>
```

**操作步骤**:
1. 点击左侧菜单 **"Configuration"** (齿轮图标)
2. 点击 **"Data sources"**
3. 点击右上角 **"Add data source"** 按钮
4. 搜索并选择 **"Infinity"**

### 1.2 配置Infinity数据源

**基本配置**:

| 字段 | 值 | 说明 |
|------|-----|------|
| **Name** | `Wazuh API` | 数据源名称 |
| **Type** | `Infinity` | 类型自动选择 |

**Authentication设置**:

| 字段 | 值 | 说明 |
|------|-----|------|
| **Authentication method** | `Basic Authentication` | 选择Basic认证 |
| **Username** | `admin` | Wazuh WebUI用户名 |
| **Password** | `<见环境变量配置>` | Wazuh WebUI密码 |

**TLS配置**:

| 字段 | 值 | 说明 |
|------|-----|------|
| **Skip TLS Verify** | ✅ 勾选 | 跳过TLS证书验证(内网环境) |

**其他配置**:

| 字段 | 值 | 说明 |
|------|-----|------|
| **Forward Proxy Headers** | 取消勾选 | 不需要 |

### 1.3 保存并测试

1. 点击页面底部的 **"Save & Test"** 按钮
2. 确认显示 **"Success"** 或 **"OK"**

---

## 🎯 步骤2: 获取Wazuh Agent列表

### 2.1 Wazuh API端点

Wazuh提供了多个API端点获取Agent信息：

#### 方法A: 获取Agent摘要统计
```
URL: https://192.168.0.40:55000/agents/summary/status
Method: GET
```

**返回数据示例**:
```json
{
  "data": {
    "total": 14,
    "active": 8,
    "disconnected": 6,
    "never_connected": 0
  }
}
```

#### 方法B: 获取完整Agent列表
```
URL: https://192.168.0.40:55000/agents?limit=20
Method: GET
```

**返回数据示例**:
```json
{
  "data": {
    "items": [
      {
        "id": "000",
        "name": "pve-ubuntu01",
        "ip": "127.0.0.1",
        "status": "active"
      },
      {
        "id": "002",
        "name": "fnos-vm-ubuntu01",
        "ip": "any",
        "status": "active"
      }
    ]
  }
}
```

---

## 🎨 步骤3: 创建Dashboard面板

### 3.1 创建"在线Agent数量"面板

1. **打开Dashboard编辑**
   - 访问: https://grafana.xiejava.dpdns.org/grafana/d/ai-minisoc-overview/
   - 点击右上角 **"Edit"** (铅笔图标)

2. **添加新面板或编辑现有面板**
   - 找到"💻 在线主机"面板(ID: 3)
   - 点击面板标题 → **"Edit"**

3. **配置查询**
   - 在数据源下拉菜单中选择 **"Wazuh API"** (刚创建的Infinity数据源)
   - **Type**: 选择 **"REST API"**
   - **URL**: `https://192.168.0.40:55000/agents/summary/status`
   - **Method**: `GET`
   - **Authentication**: 选择 **"From Data Source"**

4. **配置数据解析**
   - **Root Data Selector**: `$` (使用整个响应)
   - **Columns**: 点击 **"Add column"** 添加以下列

   | 列名 | JSONPath | 类型 |
   |------|----------|------|
   | 总数 | `$.data.total` | Number |
   | 在线数 | `$.data.active` | Number |
   | 离线数 | `$.data.disconnected` | Number |

5. **配置可视化**
   - **Visualization**: 选择 **"Stat"**
   - **Value**: 选择 **"在线数"** (`$.data.active`)
   - **Title**: `💻 在线Agent`
   - **Color**: 设置阈值颜色
     - Green: 0
     - Yellow: 5
     - Red: 10

6. **保存面板**
   - 点击右上角 **"Save"** 按钮
   - 或者 **"Apply"** 保存更改

### 3.2 创建"Agent状态列表"面板

1. **添加新面板**
   - 点击 **"Add panel"** → **"Add new panel"**

2. **配置查询**
   - **Data source**: `Wazuh API`
   - **Type**: `REST API`
   - **URL**: `https://192.168.0.40:55000/agents?limit=20`
   - **Method**: `GET`

3. **配置数据解析**
   - **Root Data Selector**: `$.data.items[*]`
   - **Columns**:

   | 列名 | JSONPath | 类型 |
   |------|----------|------|
   | ID | `$.id` | String |
   | 名称 | `$.name` | String |
   | IP | `$.ip` | String |
   | 状态 | `$.status` | String |

4. **配置可视化**
   - **Visualization**: **"Table"**
   - **Title**: `🖥️ Agent状态列表`
   - **Column settings**:
     - 为"状态"列添加颜色映射:
       - `active` → Green
       - `disconnected` → Red
       - `never_connected` → Gray

5. **保存面板**

---

## 📊 完整的Infinity查询示例

### 示例1: 在线Agent统计

```json
{
  "type": "REST API",
  "url": "https://192.168.0.40:55000/agents/summary/status",
  "method": "GET",
  "headers": {},
  "authentication": "From Data Source",
  "rootDataSelector": "$",
  "columns": [
    {
      "name": "总数",
      "selector": "$.data.total",
      "type": "number"
    },
    {
      "name": "在线",
      "selector": "$.data.active",
      "type": "number"
    },
    {
      "name": "离线",
      "selector": "$.data.disconnected",
      "type": "number"
    }
  ]
}
```

### 示例2: Agent详细列表

```json
{
  "type": "REST API",
  "url": "https://192.168.0.40:55000/agents?limit=20&status=active",
  "method": "GET",
  "headers": {},
  "authentication": "From Data Source",
  "rootDataSelector": "$.data.items[*]",
  "columns": [
    {
      "name": "Agent ID",
      "selector": "$.id",
      "type": "string"
    },
    {
      "name": "名称",
      "selector": "$.name",
      "type": "string"
    },
    {
      "name": "IP地址",
      "selector": "$.ip",
      "type": "string"
    },
    {
      "name": "状态",
      "selector": "$.status",
      "type": "string"
    },
    {
      "name": "系统",
      "selector": "$.os.name",
      "type": "string"
    },
    {
      "name": "版本",
      "selector": "$.os.version",
      "type": "string"
    }
  ]
}
```

---

## 🔧 高级配置

### 过滤器配置

只显示在线Agent:
```
URL: https://192.168.0.40:55000/agents?limit=20&status=active
```

只显示离线Agent:
```
URL: https://192.168.0.40:55000/agents?limit=20&status=disconnected
```

按名称搜索:
```
URL: https://192.168.0.40:55000/agents?search=ubuntu
```

### 刷新配置

面板自动刷新设置:
- **Refresh interval**: `30s` (30秒)
- **Max data points**: 控制数据点数量

---

## ✅ 验证测试

### 测试API连接

使用curl测试Wazuh API:
```bash
curl -k -u "admin:<password>" \
  "https://192.168.0.40:55000/agents/summary/status"
```

预期返回:
```json
{
  "data": {
    "total": 14,
    "active": 8,
    "disconnected": 6,
    "never_connected": 0
  }
}
```

---

## 📚 参考资源

- **Wazuh API文档**: https://documentation.wazuh.com/current/user-manual/api/getting-started.html
- **Grafana Infinity文档**: https://yesoreyeram.github.io/grafana-infinity-datasource/
- **API端点列表**:
  - Agent状态: `/agents/summary/status`
  - Agent列表: `/agents`
  - Agent详情: `/agents/:agent_id`
  - Agent密钥: `/agents/keys`

---

## ⚠️ 注意事项

1. **网络访问**: 确保Grafana服务器能访问192.168.0.40:55000
2. **认证信息**: 使用Wazuh Dashboard的登录凭据
3. **TLS证书**: 内网环境可以跳过TLS验证
4. **刷新频率**: 建议设置30秒-1分钟的刷新间隔
5. **数据权限**: 确保admin用户有API访问权限

---

## 🆘 故障排查

### 问题1: 无法连接到Wazuh API
**解决**:
- 检查网络连通性: `ping 192.168.0.40`
- 检查端口开放: `telnet 192.168.0.40 55000`
- 检查防火墙规则

### 问题2: 认证失败
**解决**:
- 验证用户名密码是否正确
- 检查Wazuh API日志
- 使用curl测试API

### 问题3: 数据不显示
**解决**:
- 检查JSONPath配置是否正确
- 使用Grafana的Query Inspector查看实际返回数据
- 查看浏览器控制台错误信息

---

**配置完成后，您将能够**:
- ✅ 实时查看在线Agent数量
- ✅ 查看详细的Agent状态列表
- ✅ 监控Agent的连接状态变化
- ✅ 设置告警阈值

需要我帮您进行具体的配置吗？
