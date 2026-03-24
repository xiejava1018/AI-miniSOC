# Changelog

所有项目变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- **资产管理模块**
  - 完整的资产CRUD操作API和前端界面
  - 资产端口批量管理功能
  - 端口扫描结果自动导入
  - 端口状态实时监控和变更记录

- **资产从Wazuh同步功能**
  - 手动触发全量同步：从Wazuh获取所有agent信息
  - Webhook实时同步：Agent状态变化时自动触发单个agent同步（规则504/506）
  - 智能合并策略：Wazuh控制字段自动更新，手动编辑字段保留
  - 异步详情补充：先同步基础信息，后台异步补充操作系统和硬件详情
  - 同步任务追踪：记录每次同步的统计信息和进度
  - 资产变更日志：记录字段级别的变更历史用于审计
  - Wazuh自动配置脚本：一键完成Wazuh集成配置
  - 详细的配置文档和故障排查指南

### Changed

- 扩展Asset数据模型，添加：
  - `data_source`: 数据源标记
  - `last_synced_at`: 最后同步时间
  - `os_name`, `os_version`: 操作系统信息
  - `hardware_info`: 硬件信息(JSONB)
  - `wazuh_agent_id`: Wazuh agent ID

### 技术债务

- 暂无

## [0.1.0-alpha] - 2026-03-09

### Added

- 基础项目结构
- Wazuh SIEM集成
- Loki日志聚合
- Grafana可视化
- ops-health-check健康检查
- WebDAV文件共享技能
