# Wazuh API代理服务 - Grafana Infinity集成指南

## ✅ 部署状态

**服务已成功部署并运行在:**
- **服务器**: 192.168.0.30 (Grafana服务器)
- **端口**: 5000
- **状态**: ✅ 运行中
- **Token**: ✅ 已自动获取和缓存
- **自动刷新**: ✅ 已启用（每14分钟刷新一次）

## 🚀 快速开始

### 1. 在Grafana中创建Infinity数据源

1. 登录Grafana: https://grafana.xiejava.dpdns.org
2. 进入 **Configuration** → **Data sources**
3. 点击 **Add data source**
4. 选择 **Infinity**

### 2. 配置数据源

```
Name: Wazuh API Proxy
Type: REST API

URL: http://192.168.0.30:5000

Authentication: None (代理自动处理认证)

Advanced:
  ✅ Skip TLS Verify
```

### 3. 保存并测试

点击 **Save & Test** - 应该显示"Data source is working"

## 📊 创建查询示例

### 示例1: Agents状态统计（饼图/统计面板）

**创建Panel:**
1. 点击 **Add visualization**
2. 选择 **Infinity** 数据源
3. 配置查询:

```
Type: REST API
URL: /agents/summary/status
Format: JSON

Root Data: data.connection

Frame:
  - active: $.active
  - disconnected: $.disconnected
  - never_connected: $.never_connected
  - total: $.total
```

**可视化设置:**
- 选择 **Pie Chart** 或 **Stat**
- Color: Unique colors

### 示例2: Agents列表（表格）

```
Type: REST API
URL: /agents?limit=20
Format: JSON

Root Data: data.affected_items

Columns:
  - ID: $.id
  - Name: $.name
  - IP: $.ip
  - Status: $.status
  - OS: $.os.name
  - Last Keep Alive: $.lastKeepAlive
```

### 示例3: 活跃Agents数量（时间序列）

```
Type: REST API
URL: /agents/summary/status
Format: JSON

Root Data: data.connection

Frame:
  - active: $.active
```

**可视化设置:**
- 选择 **Time Series**
- 刷新间隔: 30s或1m

## 🔧 常用API端点

### Agents相关
```
GET /agents                          # 获取所有agents
GET /agents?limit=20                 # 限制返回数量
GET /agents/summary/status           # 状态汇总（推荐）
GET /agents/status/active            # 仅活跃agents
GET /agents/{id}                     # 获取特定agent
```

### 告警相关
```
GET /alerts                          # 获取告警
GET /alerts?limit=10                 # 限制数量
GET /alerts/summary/agents           # 告警汇总
```

### 系统信息
```
GET /manager/info                    # Manager信息
GET /manager/configuration           # 配置信息
```

## 🧪 测试API

使用curl测试代理服务:

```bash
# 健康检查
curl http://192.168.0.30:5000/health

# Token信息
curl http://192.168.0.30:5000/token-info

# Agents状态
curl http://192.168.0.30:5000/agents/summary/status | jq

# Agents列表
curl http://192.168.0.30:5000/agents?limit=3 | jq
```

## 📝 管理命令

### 查看服务状态
```bash
ssh xiejava@192.168.0.30 "ps aux | grep wazuh_proxy"
```

### 查看日志
```bash
ssh xiejava@192.168.0.30 "tail -f /home/xiejava/services/wazuh-api-proxy/wazuh_proxy.log"
```

### 重启服务
```bash
ssh xiejava@192.168.0.30 "pkill -f wazuh_proxy.py && cd /home/xiejava/services/wazuh-api-proxy && nohup python3 wazuh_proxy.py > wazuh_proxy.log 2>&1 &"
```

### 停止服务
```bash
ssh xiejava@192.168.0.30 "pkill -f wazuh_proxy.py"
```

## 🔑 认证机制

**代理服务使用HTTP Basic认证自动获取JWT token:**

- **Wazuh用户**: wazuh
- **认证方式**: HTTP Basic Auth
- **Token有效期**: 15分钟
- **自动刷新**: 每14分钟（提前60秒）
- **无需手动操作**: Grafana Infinity无需配置token

## 📊 数据路径说明

### Agents状态汇总
```
响应路径: data.connection
字段:
  - active: 活跃agents数量
  - disconnected: 断开连接的agents
  - never_connected: 从未连接的agents
  - pending: 等待中的agents
  - total: 总计
```

### Agents列表
```
响应路径: data.affected_items
每个agent字段:
  - id: Agent ID
  - name: 名称
  - ip: IP地址
  - status: 状态 (active/disconnected/never_connected)
  - os.name: 操作系统名称
  - lastKeepAlive: 最后连接时间
```

## ⚠️ 故障排查

### 问题1: 无法连接到代理服务

**检查服务是否运行:**
```bash
curl http://192.168.0.30:5000/health
```

**检查防火墙:**
```bash
ssh xiejava@192.168.0.30 "sudo ufw status"
ssh xiejava@192.168.0.30 "sudo ufw allow 5000/tcp"
```

### 问题2: API返回503错误

**查看日志:**
```bash
ssh xiejava@192.168.0.30 "tail -50 /home/xiejava/services/wazuh-api-proxy/wazuh_proxy.log"
```

**检查Wazuh API连接:**
```bash
curl -k https://192.168.0.40:55000/
```

### 问题3: Token过期

**Token会自动刷新，无需手动操作。验证:**
```bash
curl http://192.168.0.30:5000/token-info
```

查看"time_remaining"字段，应该显示剩余秒数。

## 📚 完整文档

详细文档请参阅:
- `/home/xiejava/AIproject/AI-miniSOC/services/wazuh-api-proxy/README.md`

## 🎯 最佳实践

1. **使用状态汇总**: 优先使用`/agents/summary/status`而非完整列表
2. **限制数据量**: 使用`?limit=N`参数控制返回数量
3. **设置刷新间隔**: Grafana Panel建议30-60秒刷新
4. **监控代理日志**: 定期检查日志确保服务正常

## 📈 性能提示

- 代理服务有缓存机制，相同请求会快速响应
- Token自动缓存15分钟，减少认证请求
- 使用连接池和重试机制提高稳定性

---

**部署时间**: 2026-03-09
**服务版本**: v1.0.0
**状态**: ✅ 生产就绪
