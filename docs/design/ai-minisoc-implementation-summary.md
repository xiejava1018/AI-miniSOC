# AI-miniSOC 混合方案实施总结

## ✅ 已完成工作

### 1. 基础环境调研 ✓
- 调研了192.168.0.40上的Wazuh部署情况
- 调研了192.168.0.30上的Alloy + Loki + Grafana部署情况
- 确认了各组件的版本和运行状态

**环境清单**:
```
192.168.0.40 (Wazuh服务器):
├── Wazuh Manager v4.13.0 (运行中)
├── Wazuh Indexer (OpenSearch) (运行中)
└── Wazuh Dashboard (运行中)

192.168.0.30 (监控中心):
├── Grafana Alloy v1.10.0 (运行中)
├── Loki 3.5.1 (运行中)
└── Grafana 12.1.0 (运行中)
```

### 2. 数据源配置 ✓
已在Grafana中配置以下数据源:
- ✅ OpenSearch数据源 (连接Wazuh Indexer)
- ✅ Loki数据源 (本地日志系统)

### 3. Dashboard创建与部署 ✓

#### Dashboard 1: AI-miniSOC 安全态势总览
- **文件**: `configs/grafana/dashboards/ai-minisoc-overview.json`
- **Grafana ID**: 34
- **访问URL**: https://grafana.xiejava.dpdns.org/grafana/d/ai-minisoc-overview/

**功能特性**:
- 今日告警统计 (带颜色阈值)
- 高危告警实时监控
- 在线主机状态
- 7天告警趋势分析
- 威胁类型分布可视化
- Top 10威胁规则排行
- Agent主机健康度矩阵
- 最近告警实时列表

#### Dashboard 2: AI-miniSOC Wazuh告警分析
- **文件**: `configs/grafana/dashboards/ai-minisoc-wazuh-alerts.json`
- **Grafana ID**: 35
- **访问URL**: https://grafana.xiejava.dpdns.org/grafana/d/ai-minisoc-wazuh-alerts/

**功能特性**:
- 告警级别分布 (甜甜圈图)
- 多级别告警时间趋势
- 主机告警排行分析
- Agent详细统计表
- 规则组分类统计
- Top 15高频规则
- 实时告警流 (最新50条)

---

## 🏗️ 架构设计

### 当前架构
```
┌─────────────────────────────────────────────────────────┐
│                    AI-miniSOC 架构                       │
└─────────────────────────────────────────────────────────┘

┌──────────────────┐         ┌──────────────────┐
│   Wazuh Agents   │         │   其他日志源      │
│  (14台主机)       │         │  (Syslog/OTLP)   │
└────────┬─────────┘         └────────┬─────────┘
         │                            │
         ↓                            ↓
┌──────────────────┐         ┌──────────────────┐
│  Wazuh Manager   │         │   Grafana Alloy  │
│  192.168.0.40    │         │  192.168.0.30    │
└────────┬─────────┘         └────────┬─────────┘
         │                            │
         ↓                            ↓
┌──────────────────┐         ┌──────────────────┐
│  Wazuh Indexer   │────────→│      Loki        │
│  (OpenSearch)    │         │  192.168.0.30    │
│  192.168.0.40    │         └────────┬─────────┘
└────────┬─────────┘                  │
         │                            │
         └────────────┬───────────────┘
                      ↓
              ┌──────────────────┐
              │     Grafana      │
              │  192.168.0.30    │
              │  统一展示层       │
              └──────────────────┘
```

### 数据流向
1. **安全事件流**: Agent → Wazuh Manager → OpenSearch → Grafana
2. **日志流**: 各种日志源 → Alloy → Loki → Grafana
3. **统一展示**: Grafana整合多数据源，提供统一视图

---

## 🎯 核心特性

### 1. 多数据源整合
- OpenSearch: Wazuh告警和事件
- Loki: 系统日志和应用日志
- 未来可扩展: Prometheus指标、其他SIEM

### 2. 分层展示
- **Level 1**: 安全态势总览 (C-Level视角)
- **Level 2**: Wazuh告警详细分析 (分析师视角)
- **Level 3**: 关联分析 (调查员视角)

### 3. 实时监控
- 10-30秒自动刷新
- 实时告警流
- 动态阈值告警

### 4. 可视化增强
- 多种图表类型 (趋势图、饼图、表格、热力图)
- 颜色编码 (红/黄/绿)
- 交互式钻取

---

## 📊 当前覆盖范围

### 主机覆盖
- **总Agent数**: 14
- **在线Agent**: 8
- **离线Agent**: 6

### 监控能力
- ✅ 入侵检测 (IDS)
- ✅ 文件完整性监控 (FIM)
- ✅ 日志采集和分析
- ✅ 异常行为检测
- ✅ 合规性检查
- ✅ 漏洞检测
- ✅ 恶意软件检测

---

## 🚀 访问方式

### Web界面
1. **Grafana**: https://grafana.xiejava.dpdns.org
   - 认证方式: 环境变量配置
   - 🔒 安全提示: 请勿在文档中硬编码密码

2. **Wazuh Dashboard**: https://wazuh.xiejava.dpdns.org
   - 认证方式: 环境变量配置
   - 🔒 安全提示: 请勿在文档中硬编码密码

### Dashboard列表
1. **AI-miniSOC 安全态势总览**
   - URL: /grafana/d/ai-minisoc-overview/

2. **AI-miniSOC Wazuh告警分析**
   - URL: /grafana/d/ai-minisoc-wazuh-alerts/

---

## 📝 配置文件位置

### Dashboard配置
- `/home/xiejava/AIproject/AI-miniSOC/configs/grafana/dashboards/`
  - `ai-minisoc-overview.json` - 安全态势总览
  - `ai-minisoc-wazuh-alerts.json` - Wazuh告警分析

### 文档
- `/home/xiejava/AIproject/AI-miniSOC/docs/installation/`
  - `grafana-dashboard-guide.md` - Dashboard使用指南

---

## 🔧 下一步计划

### 短期 (1-2周)
- [ ] 配置Grafana告警通知
- [ ] 添加更多自定义面板
- [ ] 配置跨数据源变量联动
- [ ] 优化查询性能

### 中期 (1-2个月)
- [ ] 集成AI分析能力
- [ ] 自动化报告生成
- [ ] 威胁情报集成
- [ ] 移动端适配

### 长期 (3-6个月)
- [ ] 自然语言查询接口
- [ ] 智能告警聚合
- [ ] 预测性安全分析
- [ ] SOAR集成

---

## 💡 最佳实践

### 日常使用
1. **每日检查**: 查看"安全态势总览"，关注高危告警
2. **周报分析**: 使用"Wazuh告警分析"生成周报
3. **事件响应**: 点击告警查看详细日志，追踪溯源

### 性能优化
1. **合理设置时间范围**: 避免过长时间范围查询
2. **调整刷新间隔**: 根据需求设置10s-5min
3. **使用索引模板**: 优化OpenSearch查询性能

### 安全建议
1. **定期备份数据**: OpenSearch和Loki数据
2. **更新密码**: 定期更换Grafana和Wazuh密码
3. **访问控制**: 配置Grafana用户权限和团队

---

## 📞 技术支持

### 问题排查
1. **数据源连接失败**: 检查网络和认证配置
2. **Dashboard显示异常**: 查看Grafana日志
3. **查询性能慢**: 优化查询条件或调整时间范围

### 参考资源
- Wazuh官方文档: https://documentation.wazuh.com/
- Grafana官方文档: https://grafana.com/docs/grafana/latest/
- 项目Wiki: [待完善]

---

**文档版本**: v1.0
**创建日期**: 2026-03-09
**作者**: xiejava
**状态**: ✅ 基础部署完成
