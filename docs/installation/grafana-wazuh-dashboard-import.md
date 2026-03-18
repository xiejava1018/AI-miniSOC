# Wazuh 威胁监测仪表板 - 导入指南

## Dashboard信息

- **文件**: `wazuh-threat-monitoring.json`
- **名称**: Wazuh 威胁监测仪表板
- **UID**: `wazuh-threat-monitoring`
- **数据源**: wazuh-api (UID: fffhc15p7nthca)
- **刷新间隔**: 30秒

## 功能模块

### 1️⃣ 总览概览
- 🟢 在线Agent数量
- 🔴 离线Agent数量
- 📊 Agent总数
- ⚪ 未连接Agent数量
- 📈 Agent状态分布饼图

### 2️⃣ 操作系统分布
- 💻 操作系统类型分布饼图
- 📊 操作系统统计柱状图

### 3️⃣ Agent列表
- 📋 完整的Agent列表表格
  - Agent ID
  - 主机名
  - IP地址
  - 状态（带颜色标识）
  - 操作系统

### 4️⃣ 24小时告警趋势
- 📈 告警数量时序图
- 📊 事件总数趋势
- 📉 每小时告警统计

### 5️⃣ 系统状态
- ✅ API代理服务健康状态
- 🔑 JWT Token剩余时间
- 🌐 Wazuh服务器地址
- 🔄 Agent配置同步状态
- 🏢 集群启用/运行状态

## 导入步骤

### 方法1: 通过Grafana Web界面导入

1. **登录Grafana**
   ```
   访问: https://grafana.xiejava.dpdns.org
   ```

2. **进入导入界面**
   - 点击左侧菜单的 **+** 图标
   - 选择 **Import**

3. **上传Dashboard文件**
   - 点击 **Upload JSON file**
   - 选择文件: `configs/grafana/dashboards/wazuh-threat-monitoring.json`

4. **确认数据源映射**
   - 确保 **wazuh-api** 数据源已正确映射
   - 数据源UID应为: `fffhc15p7nthca`

5. **导入**
   - 点击 **Import** 按钮
   - Dashboard将自动加载并显示数据

### 方法2: 通过Grafana API导入

```bash
# 设置变量
GRAFANA_URL="https://grafana.xiejava.dpdns.org"
API_KEY="your-api-key"  # 需要创建API Key
DASHBOARD_FILE="configs/grafana/dashboards/wazuh-threat-monitoring.json"

# 导入Dashboard
curl -X POST "$GRAFANA_URL/api/dashboards/db" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "dashboard": $(cat $DASHBOARD_FILE),
  "overwrite": true,
  "message": "Imported Wazuh Threat Monitoring Dashboard"
}
EOF
```

### 方法3: 使用Grafana CLI工具

```bash
# 如果已安装grafana-cli
grafana-cli import-dashboard \
  --url https://grafana.xiejava.dpdns.org \
  --file configs/grafana/dashboards/wazuh-threat-monitoring.json \
  --datasource wazuh-api
```

## 数据源配置验证

在导入前，请确认以下Infinity数据源查询可以正常工作：

### 测试查询列表

Dashboard使用以下Infinity查询：

1. **agents-status-summary**
   ```
   URL: /agents/summary/status
   Type: GET
   Root Selector: $.data.connection
   ```

2. **agents-os-summary**
   ```
   URL: /agents/summary/os
   Type: GET
   Root Selector: $.data.affected_items
   ```

3. **agents-list**
   ```
   URL: /agents?limit=100
   Type: GET
   Root Selector: $.data.affected_items
   ```

4. **manager-stats**
   ```
   URL: /manager/stats
   Type: GET
   Root Selector: $.data.affected_items
   ```

5. **health**
   ```
   URL: /health
   Type: GET
   Root Selector: $.status
   ```

6. **token-info**
   ```
   URL: /token-info
   Type: GET
   Root Selector: $.time_remaining
   ```

7. **cluster-status**
   ```
   URL: /cluster/status
   Type: GET
   Root Selector: $.data.enabled
   ```

## 手动配置Infinity查询（如果需要）

如果导入后面板不显示数据，可能需要手动配置Infinity查询：

1. **编辑面板**
   - 点击面板标题
   - 选择 **Edit**

2. **配置Query**
   - 在Query标签页
   - Data Source: **wazuh-api**
   - Type: **REST API**
   - URL Format: **Global**

3. **添加查询参数**
   ```
   例如 agents-list:
   - URL: /agents?limit=100
   - Method: GET
   - Root Selector: $.data.affected_items
   ```

4. **保存**
   - 点击 **Apply** 保存更改

## 故障排查

### 问题1: 面板显示"No Data"

**解决方案**:
1. 检查API代理服务是否运行:
   ```bash
   curl http://192.168.0.30:5000/health
   ```

2. 检查数据源连接:
   - 进入 Configuration → Data Sources
   - 点击 wazuh-api
   - 点击 **Save & Test**
   - 确认显示"Data source is working"

3. 检查浏览器控制台错误:
   - 按F12打开开发者工具
   - 查看Console标签页的错误信息

### 问题2: Dashboard导入失败

**解决方案**:
1. 确认JSON文件格式正确:
   ```bash
   cat configs/grafana/dashboards/wazuh-threat-monitoring.json | jq .
   ```

2. 检查Grafana版本兼容性
   - 最低要求: Grafana 9.x
   - 推荐版本: Grafana 10.x 或更高

3. 确认数据源存在:
   - UID应为: `fffhc15p7nthca`
   - 名称应为: `wazuh-api`

### 问题3: 面板数据不更新

**解决方案**:
1. 检查刷新间隔设置
   - Dashboard默认设置为30秒自动刷新
   - 可在顶部时间选择器旁调整

2. 手动刷新
   - 点击面板右上角的刷新图标

3. 检查API代理日志:
   ```bash
   ssh xiejava@192.168.0.30 'tail -f /home/xiejava/services/wazuh-api-proxy/wazuh_proxy.log'
   ```

## 自定义配置

### 修改刷新间隔

编辑Dashboard JSON:
```json
"refresh": "30s"  // 可改为: 5s, 10s, 1m等
```

### 修改时间范围

编辑Dashboard JSON:
```json
"time": {
  "from": "now-24h",  // 可改为: now-7d, now-1h等
  "to": "now"
}
```

### 添加新的面板

1. 在Grafana中编辑Dashboard
2. 点击 **Add panel**
3. 选择数据源: **wazuh-api**
4. 配置查询
5. 保存Dashboard

### 导出修改后的Dashboard

1. 在Grafana中打开Dashboard
2. 点击右上角 **Share** 图标
3. 选择 **Export**
4. 选择 **Export for sharing externally**
5. 保存为JSON文件

## 性能优化建议

### 1. 减少查询频率
如果API代理服务压力较大，可以:
- 增加刷新间隔至1分钟或更长
- 使用Dashboard变量的时间范围限制

### 2. 限制数据量
在查询中添加limit参数:
```
/agents?limit=50  // 只查询前50个Agent
```

### 3. 使用缓存
在Infinity数据源中启用响应缓存:
- 进入数据源设置
- 启用 **Cache**
- 设置TTL (建议: 60秒)

## 安全建议

1. **访问控制**
   - 设置Grafana用户权限
   - 为Dashboard配置查看权限

2. **API密钥管理**
   - 不要在Dashboard中硬编码凭证
   - 使用Grafana的内置认证

3. **网络安全**
   - 使用HTTPS访问Grafana
   - 限制API代理服务的网络访问

## 后续增强

建议的扩展功能:

1. **告警通知**
   - 为离线Agent配置告警
   - 设置告警阈值

2. **更多面板**
   - 告警详情列表
   - 规则命中率统计
   - 文件完整性检查结果

3. **AI分析**
   - 集成AI威胁评分
   - 异常检测可视化

4. **报表导出**
   - 生成日报/周报
   - PDF导出功能

## 联系支持

如遇到问题，请检查:
1. [Grafana文档](https://grafana.com/docs/)
2. [Infinity插件文档](https://grafana.com/plugins/yesoreyeram-infinity/)
3. 项目README.md

---

**最后更新**: 2026-03-10
**版本**: 1.0.0
