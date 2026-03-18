# Network Asset Scanner

自动扫描内网资产并同步到 PostgreSQL + 飞书（双源同步）。

## 功能

- **主机发现** - nmap 快速扫描内网在线设备
- **端口扫描** - 识别开放端口和服务
- **设备识别** - 自动识别设备类型（Proxmox/Windows/Linux/NAS等）
- **双源同步** - PostgreSQL(主) + 飞书(展示)

## 使用方法

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

## 配置说明 (.env)

```bash
# 网络配置
NETWORK=192.168.0.0/24

# PostgreSQL 配置
PGHOST=localhost
PGPORT=5432
PGUSER=postgres
PGPASSWORD=your_password_here
PGDATABASE=postgres

# 飞书多维表格配置
FEISHU_APP_TOKEN=your_app_token_here
FEISHU_TABLE_ID=your_table_id_here
FEISHU_APP_ID=your_app_id_here
FEISHU_APP_SECRET=your_app_secret_here
```

## 数据源

### PostgreSQL（主数据源）

表 `soc_assets`:
- id (TEXT, PK)
- asset_ip (TEXT, UNIQUE)
- asset_description (TEXT)
- asset_status (TEXT) - 在线/离线/新发现
- status_updated_at (TIMESTAMP)
- created_at (TIMESTAMP)

表 `soc_asset_ports`:
- id (SERIAL, PK)
- asset_ip (TEXT)
- port (INTEGER)
- protocol (TEXT)
- service (TEXT)
- version (TEXT)
- scanned_at (TIMESTAMP)

### 飞书多维表格（展示/备份）

字段:
- 资产IP (文本)
- 资产说明 (文本)
- 资产状态 (文本) - 在线/离线/新发现/已删除
- 状态更新时间 (日期时间)

## 同步流程

```
nmap扫描 → PostgreSQL(主) → 飞书(展示)
```

1. 快速扫描网段在线主机
2. 详细扫描端口和服务
3. 识别设备类型
4. 更新 PostgreSQL
5. 同步到飞书

## 设备识别

自动识别以下设备类型：
- Router (路由器)
- Windows PC
- Linux Server
- Proxmox (虚拟化)
- NAS (存储)
- Web Server
- Database Server
- Camera (摄像头)
- Printer (打印机)
- IoT (智能设备)

## 状态标记

| 状态 | 含义 |
|------|------|
| 新发现 | 首次扫描到的IP |
| 在线 | 本次扫描在线 |
| 离线 | 之前在线本次未扫描到 |
| 已删除 | 手动标记删除 |

## 时间戳格式

飞书 DateTime 字段需要**毫秒级时间戳**（13位）

```python
timestamp = int(time.time() * 1000)  # ✅ 正确
timestamp = int(time.time())          # ❌ 错误
```

## 目录结构

```
network-scan/
├── network_scan_unified.py   # 主扫描脚本
├── network_scan.py            # 旧版仅飞书
├── .env.example               # 配置模板
├── SKILL.md                  # 技能说明
└── README.md                  # 本文件
```
