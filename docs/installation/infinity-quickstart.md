# 快速开始 - 使用Infinity获取Wazuh Agent状态

## 🚀 5分钟快速配置

### 1️⃣ 确认插件已安装 ✅

```bash
# SSH到Grafana服务器
ssh xiejava@192.168.0.30

# 检查插件
grafana-cli plugins ls | grep infinity
# 应该看到: yesoreyeram-infinity-datasource
```

**状态**: ✅ 已安装

### 2️⃣ 在Grafana中添加Infinity数据源

#### 步骤:
1. 登录 Grafana: https://grafana.xiejava.dpdns.org
2. 进入: **Configuration** → **Data sources**
3. 点击: **Add data source**
4. 搜索: **Infinity**
5. 配置:
   ```
   Name: Wazuh API
   Authentication: Basic Authentication
   Username: admin
   Password: <见环境变量配置>
   Skip TLS Verify: ✅ (勾选)
   ```
6. 点击: **Save & Test**

### 3️⃣ 测试API连接

在新标签页访问测试链接:
```
https://grafana.xiejava.dpdns.org/grafana/datasources/edit/wazuh-api
```

或使用curl测试:
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

### 4️⃣ 创建第一个面板

#### 方法A: 在现有Dashboard中添加

1. 打开: https://grafana.xiejava.dpdns.org/grafana/d/ai-minisoc-overview/
2. 点击: **Edit** (铅笔图标)
3. 找到"💻 在线主机"面板
4. 点击面板 → **Edit**

#### 方法B: 创建新面板

1. 点击: **+** → **Dashboard**
2. 点击: **Add panel**
3. 配置面板:

**查询配置**:
```
Data source: Wazuh API
Type: REST API
URL: https://192.168.0.40:55000/agents/summary/status
Method: GET
Authentication: From Data Source
Root Data Selector: $
```

**列配置**:
点击"Add column"添加:

| 名称 | JSONPath | 类型 |
|------|----------|------|
| 在线Agent | `$.data.active` | Number |

**可视化配置**:
```
Visualization: Stat
Title: 💻 在线Agent
Color mode: Value
Graph mode: None
```

**阈值配置**:
```
Green: 0
Yellow: 5
Red: 10
```

5. 点击: **Apply** → **Save**

### 5️⃣ 验证结果

刷新Dashboard页面，您应该看到:
- ✅ 显示数字 "8" (在线Agent数量)
- ✅ 数字根据实际情况变化
- ✅ 颜色根据阈值变化

---

## 📊 常用API端点速查

### 1. Agent统计
```
GET /agents/summary/status
返回: { total, active, disconnected, never_connected }
```

### 2. Agent列表
```
GET /agents?limit=20
返回: 所有Agent列表
```

### 3. 在线Agent
```
GET /agents?status=active
返回: 仅在线Agent
```

### 4. 离线Agent
```
GET /agents?status=disconnected
返回: 仅离线Agent
```

### 5. 特定Agent详情
```
GET /agents/002
返回: ID为002的Agent详情
```

---

## 🎯 实用示例

### 示例1: Stat面板 - 在线Agent数量

**查询**:
```json
URL: /agents/summary/status
Type: REST API
```

**数据**:
```
Value: $.data.active
```

### 示例2: Table面板 - Agent状态列表

**查询**:
```json
URL: /agents?limit=20
Type: REST API
Root: $.data.items[*]
```

**列**:
```
ID: $.id
名称: $.name
IP: $.ip
状态: $.status
```

### 示例3: 多个Stat面板

创建3个面板显示不同指标:

1. **总数**: `$.data.total`
2. **在线**: `$.data.active`
3. **离线**: `$.data.disconnected`

---

## ⚡ 自动刷新

设置面板自动刷新:
1. 编辑面板
2. 右上角 **Refresh interval**
3. 选择: `30s` 或 `1m`

---

## 🔧 常见问题

### Q: 数据不显示？
**A**:
1. 检查数据源是否测试通过
2. 检查JSONPath是否正确
3. 打开浏览器控制台查看错误

### Q: 认证失败？
**A**:
1. 确认用户名密码正确
2. 使用curl测试API
3. 检查Wazuh API是否运行

### Q: 如何只显示在线Agent？
**A**:
```
URL: /agents?status=active
```

### Q: 如何搜索特定Agent？
**A**:
```
URL: /agents?search=ubuntu
```

---

## 📞 需要帮助？

如果遇到问题，检查:
1. Grafana日志: `sudo journalctl -u grafana-server -f`
2. Wazuh API日志: `sudo tail -f /var/ossec/logs/api.log`
3. 浏览器控制台 (F12)

---

**预计配置时间**: 5-10分钟
**难度级别**: ⭐⭐ (简单)

准备好开始了吗？🚀
