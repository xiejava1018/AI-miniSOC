# AI-miniSOC Grafana Dashboard 部署指南

## 📊 已部署Dashboard列表

### 1. 安全态势总览 Dashboard
- **UID**: `ai-minisoc-overview`
- **ID**: 34
- **URL**: https://grafana.xiejava.dpdns.org/grafana/d/ai-minisoc-overview/
- **刷新间隔**: 30秒
- **时间范围**: 默认显示最近7天

#### 功能模块:
- 📊 今日告警总数 (带阈值颜色)
- 🔴 高危告警统计 (Level 12+)
- 💻 在线Agent数量
- 📈 7天告警趋势图
- 🎯 威胁类型分布 (饼图)
- 🔥 Top 10 威胁规则排行
- 🖥️ Agent主机状态表
- 📋 最近告警列表 (24小时)

---

### 2. Wazuh告警分析 Dashboard
- **UID**: `ai-minisoc-wazuh-alerts`
- **ID**: 35
- **URL**: https://grafana.xiejava.dpdns.org/grafana/d/ai-minisoc-wazuh-alerts/
- **刷新间隔**: 10秒
- **时间范围**: 可选择 (1小时/6小时/24小时/7天/30天)

#### 功能模块:
- 📊 告警级别分布 (甜甜圈图)
- 📈 告警级别时间趋势 (堆叠面积图)
- 🖥️ 主机告警排行 (柱状图)
- 📋 Agent告警统计表
- 🎯 规则组分布
- 🔥 Top 15 高频触发规则
- ⚡ 实时告警列表 (最新50条)

---

## 🔧 配置信息

### 数据源配置

#### OpenSearch (Wazuh)
- **名称**: OpenSearch
- **URL**: https://192.168.0.40:9200
- **认证**:
  - 用户名: admin
  - 密码: (需配置)
- **TLS**: 跳过验证 (内网环境)
- **版本**: OpenSearch 2.x

#### Loki
- **名称**: Loki
- **URL**: http://192.168.0.30:3100
- **认证**: (可选)
- **版本**: Loki 3.5.1

### Grafana访问
- **地址**: https://grafana.xiejava.dpdns.org
- **用户名**: admin
- **密码**: <见环境变量配置>

---

## 📝 Dashboard说明

### 查询语法参考

#### OpenSearch查询示例:

```json
// 今日告警
{
  "bool": {
    "filter": [
      {"range": {"@timestamp": {"gte": "now/d"}}}
    ]
  }
}

// 高危告警 (Level 12+)
{
  "bool": {
    "filter": [
      {"range": {"@timestamp": {"gte": "now/d"}}},
      {"term": {"rule.level": "12"}}
    ]
  }
}

// 特定Agent
{
  "bool": {
    "filter": [
      {"term": {"agent.name": "pve-ubuntu01"}}
    ]
  }
}
```

#### Loki查询示例:
```
# 所有Wazuh告警
{job="wazuh-alerts"}

# 特定主机
{host="pve-ubuntu01"}

# 时间范围查询
{job="wazuh-alerts"} | line_format "{{.timestamp}} {{.message}}"
```

---

## 🎯 使用建议

### 1. 日常监控
- 使用"安全态势总览"Dashboard查看整体态势
- 关注高危告警数量和趋势
- 定期检查离线Agent

### 2. 告警调查
- 使用"Wazuh告警分析"Dashboard深度分析
- 按级别、主机、规则组筛选
- 查看告警详细日志内容

### 3. 定制建议
- 根据实际需求调整刷新间隔
- 配置告警通知规则
- 添加更多自定义面板

---

## 🔔 后续优化方向

### Phase 1: 跨数据源关联
- [ ] 配置Grafana变量联动
- [ ] 实现点击Agent跳转到Loki日志
- [ ] 添加时间同步功能

### Phase 2: 告警增强
- [ ] 配置Grafana Alerting
- [ ] 集成钉钉/企业微信通知
- [ ] 设置告警阈值和规则

### Phase 3: AI能力
- [ ] 集成自然语言查询
- [ ] 智能告警聚合
- [ ] 异常行为检测

### Phase 4: 报告生成
- [ ] 定期安全报告
- [ ] 周报/月报自动生成
- [ ] 威胁态势分析报告

---

## 📚 相关资源

- **Wazuh文档**: https://documentation.wazuh.com/
- **Grafana文档**: https://grafana.com/docs/grafana/latest/
- **OpenSearch文档**: https://opensearch.org/docs/
- **Loki文档**: https://grafana.com/docs/loki/latest/

---

**文档版本**: v1.0
**最后更新**: 2026-03-09
**维护者**: xiejava
