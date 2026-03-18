---
name: network-scan
description: |
  扫描内网192.168.0.0/24网段资产，自动更新 PostgreSQL + 飞书双数据源。
  新发现的IP标记为"新发现"，已离线的标记为"离线"。
  使用场景：网络资产管理、资产巡检、安全扫描。
---

# Network Asset Scanner

内网资产扫描技能 - 自动发现网络设备并同步到数据库。

## 功能

1. **主机发现** - nmap 快速扫描内网在线设备
2. **端口扫描** - 识别开放端口和服务版本
3. **设备识别** - 自动识别设备类型（Proxmox/Windows/Linux/NAS等）
4. **双源同步** - PostgreSQL(主) + 飞书(展示)
5. **去重逻辑** - 已存在IP执行更新，不再重复创建

## 快速开始

### 1. 配置环境

```bash
cd /path/to/network-scan
cp .env.example .env
# 编辑 .env 填入你的配置
```

### 2. 运行扫描

```bash
python3 network_scan_unified.py
```

## 配置说明

详见 [README.md](./README.md)

## 数据源

### PostgreSQL（主数据源）
- 表: soc_assets, soc_asset_ports

### 飞书多维表格（展示/备份）
- 字段: 资产IP, 资产说明, 资产状态, 状态更新时间

## 状态标记

| 状态 | 含义 |
|------|------|
| 新发现 | 首次扫描到的IP |
| 在线 | 本次扫描在线 |
| 离线 | 之前在线本次未扫描到 |
| 已删除 | 手动标记删除 |

## 同步流程

```
nmap扫描 → PostgreSQL(主) → 飞书(展示)
```

## 重要说明

- 飞书 DateTime 字段需要**毫秒级时间戳**
- 必须先更新 PostgreSQL，再同步飞书
- 敏感配置请填写在 `.env` 文件中，不要提交到 Git

## 文件说明

- `network_scan_unified.py` - 主扫描脚本
- `.env.example` - 配置模板
- `README.md` - 详细使用说明
- `SKILL.md` - 本文件
