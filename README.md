# AI-miniSOC

AI驱动的微型安全运营中心（Security Operations Center）

## 项目概述

AI-miniSOC 是一个基于AI的轻量级安全运营平台，集成了多种安全工具，提供智能化的安全监控、威胁检测和事件响应能力。

## 核心功能

### 1. 日志聚合与分析
- 📊 **Loki** - 日志聚合系统
- 📈 **Grafana** - 可视化仪表板
- 🔍 **OpenSearch** - 日志搜索与分析

### 2. 威胁检测
- 🛡️ **Wazuh** - 安全信息与事件管理(SIEM)
- 🚨 **实时告警** - 异常行为检测
- 📝 **规则引擎** - 自定义检测规则

### 3. 主机监控
- 💻 **系统健康检查** - ops-health-check
- 🐳 **容器监控** - Docker容器状态
- 📊 **性能指标** - CPU、内存、磁盘、网络

### 4. AI能力
- 🤖 **智能分析** - AI驱动的日志分析
- 🔎 **异常检测** - 机器学习异常识别
- 📊 **趋势预测** - 安全威胁趋势分析
- 💬 **自然语言查询** - 用自然语言查询日志和告警

## 技术栈

- **日志采集**: Wazuh, Filebeat, Otelp
- **日志存储**: Loki (7天保留)
- **数据可视化**: Grafana
- **搜索引擎**: OpenSearch
- **监控工具**: Prometheus, Node Exporter
- **AI/ML**: Claude AI, OpenAI API
- **编程语言**: Shell, Python, JavaScript/TypeScript
- **部署**: Docker, Docker Compose

## 项目结构

```
AI-miniSOC/
├── docs/                  # 项目文档
│   ├── design/           # 设计文档
│   ├── installation/     # 安装指南
│   └── api/              # API文档
├── services/             # 微服务
│   ├── log-collector/    # 日志采集服务
│   ├── alert-engine/     # 告警引擎
│   ├── ai-analyzer/      # AI分析服务
│   └── dashboard/        # 前端仪表板
├── configs/              # 配置文件
│   ├── wazuh/           # Wazuh配置
│   ├── loki/            # Loki配置
│   ├── grafana/         # Grafana仪表板
│   └── deployment/      # 部署配置
├── scripts/              # 工具脚本
│   ├── install/         # 安装脚本
│   ├── monitoring/      # 监控脚本
│   └── backup/          # 备份脚本
├── tests/                # 测试用例
└── docker-compose.yml    # Docker编排文件
```

## 快速开始

### 前置要求

- Docker & Docker Compose
- 8GB+ 内存
- 50GB+ 磁盘空间
- Linux系统 (推荐Ubuntu 22.04)

### 安装

```bash
# 克隆仓库
git clone git@github.com:xiejava1018/AI-miniSOC.git
cd AI-miniSOC

# 运行安装脚本
./scripts/install/install.sh

# 启动服务
docker-compose up -d
```

### 访问

- **Grafana**: http://localhost:3000
- **Wazuh**: https://localhost:55000
- **OpenSearch**: https://localhost:9200
- **Loki**: http://localhost:3100

## 配置说明

### Loki配置
- 保留期: 7天
- 最大查询范围: 500天
- 存储位置: /data/loki

### 健康检查配置
- 磁盘告警: 50% (警告), 80% (严重)
- 内存告警: 70% (警告), 90% (严重)
- CPU负载告警: 2.0 (警告), 5.0 (严重)

## 当前状态

- [x] 基础架构搭建
- [x] 日志采集 (Wazuh + Loki)
- [x] 可视化 (Grafana)
- [x] 健康检查工具 (ops-health-check)
- ] AI分析引擎
- ] 告警通知系统
- ] 用户认证
- ] 前端界面

## 开发路线图

### Phase 1: 基础监控 (已完成)
- [x] 部署Wazuh SIEM
- [x] 配置Loki日志聚合
- [x] 集成Grafana仪表板
- [x] 开发健康检查脚本

### Phase 2: AI增强 (进行中)
- [ ] AI日志分析
- [ ] 异常检测模型
- [ ] 智能告警
- [ ] 自然语言查询

### Phase 3: 自动化响应 (计划中)
- [ ] 自动化事件响应
- [ ] 威胁情报集成
- [ ] SOAR功能
- [ ] 工单系统集成

## 相关项目

- [ops-health-check](../host-manage/) - 系统健康检查工具
- [AI-Copilot](../AI-Copilot/) - AI辅助开发工具

## 贡献指南

欢迎贡献！请查看 [CONTRIBUTING.md](docs/CONTRIBUTING.md) 了解详情。

## 许可证

MIT License

## 联系方式

- 作者: xiejava
- 项目地址: https://github.com/xiejava1018/AI-miniSOC
- 问题反馈: https://github.com/xiejava1018/AI-miniSOC/issues

---

**最后更新**: 2026-03-09
**版本**: v0.1.0-alpha
