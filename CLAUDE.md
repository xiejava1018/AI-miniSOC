# CLAUDE.md

# AI-miniSOC 项目开发指南

这个文件为 Claude Code (claude.ai/code) 提供 AI-miniSOC 项目开发时的上下文和指导。

## 项目概述

AI-miniSOC 是一个**AI驱动的微型安全运营中心**，集成了日志聚合、威胁检测、主机监控和AI分析能力。

当前开发环境位于 `/home/xiejava/AIproject/AI-miniSOC`

## 核心组件

### 已部署的监控栈

#### Wazuh SIEM
- **位置**: 192.168.0.30:55000
- **功能**: 安全信息和事件管理
- **数据源**: 多个主机的日志
- **OpenSearch**: 192.168.0.30:9200

#### Loki 日志系统
- **位置**: http://192.168.0.30:3100
- **配置**: /etc/loki/config.yaml
- **保留策略**: 7天
- **最大查询**: 500天 (12000小时)
- **存储**: /data/loki

#### Grafana 可视化
- **位置**: https://grafana.xiejava.dpdns.org
- **数据源**: Loki, OpenSearch, Prometheus
- **仪表板**: Wazuh威胁检测, 系统监控

#### 主机监控
- **工具**: ops-health-check (位于 ../host-manage/)
- **功能**: 系统健康检查、Docker监控、安全检查
- **输出格式**: Markdown + JSON

### 日志数据源

当前监控的IP范围：
- **内网**: 192.168.0.2-192.168.0.128
- **外网**: 多个公网IP (通过路由器日志)

日志标签:
- `host`: 主机名
- `ip`: IP地址
- `job`: 任务类型 (wazuh-alerts, wazuh-test)
- `exporter`: OTLP
- `service_name`: 服务名称

## 项目结构规划

```
AI-miniSOC/
├── docs/                      # 📚 文档
│   ├── design/               # 设计文档
│   │   ├── architecture.md   # 架构设计
│   │   ├── data-model.md     # 数据模型
│   │   └── api-design.md     # API设计
│   ├── installation/         # 安装指南
│   │   ├── wazuh-setup.md
│   │   ├── loki-setup.md
│   │   └── grafana-setup.md
│   └── api/                  # API文档
│       ├── loki-api.md
│       ├── wazuh-api.md
│       └── rest-api.md
├── services/                 # 🔧 微服务
│   ├── log-collector/        # 日志采集增强
│   ├── alert-engine/         # 告警引擎
│   ├── ai-analyzer/          # AI分析服务
│   └── dashboard/            # Web仪表板
├── configs/                  # ⚙️ 配置文件
│   ├── wazuh/
│   │   ├── rules/           # 自定义规则
│   │   └── decoders/        # 自定义解码器
│   ├── loki/
│   │   └── retention-policy.yml
│   ├── grafana/
│   │   └── dashboards/      # 仪表板JSON
│   └── deployment/
│       ├── docker-compose.yml
│       └── k8s/
├── scripts/                  # 📜 工具脚本
│   ├── install/             # 安装脚本
│   ├── monitoring/          # 监控脚本
│   │   └── health-check.sh  # 健康检查
│   ├── backup/              # 备份脚本
│   └── maintenance/         # 维护脚本
├── tests/                   # 🧪 测试
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── skills/                  # 🎯 Claude Code技能
│   ├── log-query/          # 日志查询技能
│   ├── threat-analysis/    # 威胁分析技能
│   └── report-gen/         # 报告生成技能
└── docker-compose.yml       # Docker编排
```

## 开发规范

### 代码规范
- **Shell脚本**: 遵循 ShellCheck 规范，支持 bash 3.2+
- **Python**: 遵循 PEP 8，使用类型注解
- **JavaScript**: 使用 ESLint + Prettier
- **文档**: Markdown格式，中文优先

### Git工作流
```bash
# 主分支
main              # 稳定版本
develop           # 开发分支

# 功能分支
feature/*         # 新功能
fix/*            # 修复
docs/*           # 文档更新
```

### 提交信息规范
```
<type>(<scope>): <subject>

<body>

<footer>
```

类型:
- feat: 新功能
- fix: 修复
- docs: 文档
- style: 格式
- refactor: 重构
- test: 测试
- chore: 构建/工具

## API 端点

### Loki API
```bash
# 基础URL
http://192.168.0.30:3100/loki/api/v1

# 查询日志
GET  /query_range
GET  /query

# 标签查询
GET  /label
GET  /label/<name>/values

# 示例
curl -G http://192.168.0.30:3100/loki/api/v1/query_range \
  --data-urlencode 'query={ip="192.168.0.2"}' \
  --data-urlencode 'start=<nanosecond_timestamp>' \
  --data-urlencode 'end=<nanosecond_timestamp>'
```

### Wazuh API
```bash
# 基础URL
https://192.168.0.30:55000/api

# 认证
POST /security/user/authenticate

# 查询告警
GET /alerts?offset=0&limit=10

# 示例
curl -k -X GET \
  "https://192.168.0.30:55000/api/alerts?offset=0&limit=10" \
  -H "Authorization: Bearer <JWT_TOKEN>"
```

## 常用命令

### Loki查询
```bash
# 查询特定IP的日志
curl -G http://192.168.0.30:3100/loki/api/v1/query_range \
  --data-urlencode 'query={ip="192.168.0.2"}' \
  --data-urlencode 'start=1772932355000000000' \
  --data-urlencode 'end=1773018755000000000'

# 统计日志数量
curl ... | jq '.data.result[0].values | length'
```

### Docker操作
```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f [service]

# 重启服务
docker-compose restart [service]
```

### 健康检查
```bash
# 运行健康检查
cd /home/xiejava/AIproject/host-manage
bash skills/ops-health-check/scripts/health-check.sh

# 远程检查
ssh xiejava@192.168.0.30 'bash -s' < skills/ops-health-check/scripts/health-check.sh
```

## 当前已知问题

### 日志中断
- **问题**: 192.168.0.2日志在凌晨1:27后停止（TL-R479GP-AC路由器）
- **影响**: 无法查看该主机最新活动
- **待解决**: 排查路由器日志推送服务

### Loki限制
- 查询限制10000条/次
- 需要分页查询大量数据
- 时戳使用纳秒级

## 开发优先级

### Phase 1: 基础完善 (当前)
- [ ] 补全项目文档
- [ ] 创建基础脚本框架
- [ ] 配置Docker Compose
- [ ] 集成现有监控工具

### Phase 2: AI能力
- [ ] 实现日志AI分析
- [ ] 异常检测模型
- [ ] 智能告警聚合
- [ ] 自然语言查询接口

### Phase 3: 增强功能
- [ ] 告警通知 (邮件/钉钉/微信)
- [ ] 报告自动生成
- [ ] 威胁情报集成
- [ ] 自动化响应

## 相关资源

- **Wazuh文档**: https://documentation.wazuh.com/
- **Loki文档**: https://grafana.com/docs/loki/latest/
- **Grafana文档**: https://grafana.com/docs/grafana/latest/
- **Claude Code**: https://claude.ai/code

## 注意事项

1. **日志保留**: Loki仅保留7天，重要数据需备份
2. **时间戳**: Loki使用纳秒级Unix时间戳
3. **认证**: Wazuh使用JWT认证，需定期刷新
4. **性能**: 大量日志查询注意分页，避免超时
5. **安全**: 不要在代码中硬编码凭证

---

**文档版本**: v1.0
**最后更新**: 2026-03-09
