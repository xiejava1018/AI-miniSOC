# Network Scan - 内网资产扫描

自动扫描内网资产并同步到 Supabase + 飞书（双源同步）。

## 功能

- 🌐 自动扫描内网在线主机
- 📦 同步到 Supabase（主数据源）
- 📋 同步到飞书多维表格（展示/备份）
- 🔄 状态自动更新（在线/离线/新发现）
- 🛡️ 去重逻辑（避免重复创建）

## 快速开始

### 1. 安装依赖

```bash
pip install requests
# 需要 nmap: apt install nmap
```

### 2. 配置

```bash
cd skills/network-scan
cp .env.example .env
# 编辑 .env 填入你的配置
```

### 3. 配置 Supabase

1. 创建 Supabase 项目
2. 创建 `soc_assets` 表：
   - `id` (int8, 主键, 自增)
   - `asset_ip` (text, 唯一)
   - `asset_description` (text)
   - `asset_status` (text)
   - `status_updated_at` (timestamp)
3. 获取 API URL 和 anon public key

### 4. 配置飞书多维表格

1. 在飞书开放平台创建应用
2. 开通多维表格权限
3. 创建多维表格，设置字段：
   - `资产IP` (文本，唯一)
   - `资产说明` (文本)
   - `资产状态` (文本：在线/离线/新发现/已删除)
   - `状态更新时间` (日期时间)

### 5. 运行

```bash
python3 network_scan_unified.py
```

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| NETWORK | 扫描网段 | 192.168.0.0/24 |
| SUPABASE_URL | Supabase 项目 URL | https://xxx.supabase.co |
| SUPABASE_KEY | Supabase anon public key | eyJxxx |
| FEISHU_APP_TOKEN | 飞书多维表格 App Token | YBxxx |
| FEISHU_TABLE_ID | 飞书多维表格 Table ID | tblxxx |
| FEISHU_APP_ID | 飞书应用 App ID | cli_xxx |
| FEISHU_APP_SECRET | 飞书应用 App Secret | xxx |

## 数据流向

```
nmap 扫描 → Supabase（主数据源）→ 飞书（展示/备份）
```

## 状态说明

- 🆕 新发现：首次扫描到的 IP
- ✅ 在线：本次扫描仍然在线
- ❌ 离线：之前在线，本次未扫描到
- 🗑️ 已删除：手动标记删除
