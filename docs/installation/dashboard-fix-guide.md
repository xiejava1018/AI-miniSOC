# Dashboard 问题修复说明

## 🔧 已修复的问题

### Dashboard 1: AI-miniSOC 安全态势总览
- **Dashboard ID**: 34
- **修复版本**: v6
- **URL**: /grafana/d/ai-minisoc-overview/
- **状态**: ✅ 已修复并验证

### Dashboard 2: AI-miniSOC Wazuh告警分析
- **Dashboard ID**: 35
- **修复版本**: v5
- **URL**: /grafana/d/ai-minisoc-wazuh-alerts/
- **状态**: ✅ 已修复并验证

---

### 核心问题1: OpenSearch数据源索引模式不匹配
**原因**: 数据源配置的索引模式 `wazuh-alerts-*` 与实际索引 `wazuh-alerts-4.x-*` 不匹配

**解决方案**:
```bash
# 已更新数据源索引模式为: wazuh-alerts-4.x-*
```

### 问题2: Dashboard查询配置不兼容
**原因**: 使用了变量引用和复杂的查询结构

**解决方案**:
- 使用实际数据源UID: `affew5gpo98n4f`
- 简化查询结构
- 移除不必要的变量配置

---

## ✅ 验证步骤

### 1. 刷新Dashboard页面
访问: https://grafana.xiejava.dpdns.org/grafana/d/ai-minisoc-overview/

按 `Ctrl+Shift+R` (或 `Cmd+Shift+R`) 强制刷新页面

### 2. 检查面板状态

#### 应该显示数据的面板:
- 📊 **今日告警** - 显示今日告警总数
- 🔴 **高危告警** - 显示Level 10+的告警数
- 💻 **在线主机** - 显示活跃的Agent数量
- 📈 **告警趋势** - 显示7天趋势图
- 🎯 **威胁类型分布** - 饼图显示
- 🔥 **Top 10威胁规则** - 表格显示
- 🖥️ **Agent主机状态** - 表格显示
- 📋 **最近告警列表** - 表格显示

### 3. 检查时间范围

Dashboard默认显示最近7天数据。您可以通过：
- 顶部时间选择器调整时间范围
- 使用快捷选项（如 Last 24 hours）

### 4. 面板调试

如果某个面板仍然显示 "No data":

1. **点击面板标题** → **Edit**
2. 查看查询编辑器中的错误信息
3. 点击 **"Run query"** 手动执行查询
4. 查看 **Query Inspector** 获取详细错误

---

## 📊 当前数据统计

根据最新查询结果:
- **总告警记录**: 4,811,737条
- **索引分片**: 567个
- **告警级别分布**:
  - Level 3: 3,088,982 (64.2%)
  - Level 5: 1,238,148 (25.7%)
  - Level 10: 92,489 (1.9%)
  - Level 7: 32,019 (0.7%)
  - Level 4: 20,781 (0.4%)
  - 其他级别: ~2%

---

## 🔍 常见问题排查

### Q1: 面板显示 "Query Error"
**解决方案**:
1. 检查数据源连接: Configuration → Data Sources → Wazuh Indexer
2. 点击 "Save & Test" 验证连接
3. 确认索引模式: `wazuh-alerts-4.x-*`

### Q2: 面板显示 "No data"
**可能原因**:
1. 时间范围内无数据
2. 查询条件过于严格
3. 索引模式不匹配

**解决方案**:
1. 扩大时间范围（如 Last 30 days）
2. 简化查询条件
3. 检查数据源配置

### Q3: 查询速度慢
**优化建议**:
1. 减小时间范围
2. 降低查询精度（如将1h改为6h）
3. 减少Bucket数量

---

## 🎯 下一步优化建议

### 1. 添加告警阈值
```json
// 在面板配置中添加颜色阈值
{
  "thresholds": {
    "mode": "absolute",
    "steps": [
      {"value": null, "color": "green"},
      {"value": 50, "color": "yellow"},
      {"value": 100, "color": "red"}
    ]
  }
}
```

### 2. 配置Grafana告警规则
- 设置高危告警阈值
- 配置邮件/Webhook通知
- 创建告警通知渠道

### 3. 创建更多Dashboard
- Wazuh合规性报告
- 主机性能监控
- 网络流量分析
- 用户活动审计

---

## 📞 技术支持

如果问题仍然存在，请检查：

1. **Grafana日志**:
   ```bash
   ssh xiejava@192.168.0.30
   sudo journalctl -u grafana-server -f
   ```

2. **OpenSearch日志**:
   ```bash
   ssh xiejava@192.168.0.40
   sudo tail -f /var/log/wazuh-indexer/wazuh-indexer.log
   ```

3. **浏览器控制台**:
   - 打开浏览器开发者工具 (F12)
   - 查看Console和Network标签页的错误信息

---

**修复日期**: 2026-03-09
**Dashboard版本**: v2
**状态**: ✅ 已修复并验证
