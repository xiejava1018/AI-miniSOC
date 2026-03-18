---
name: network-scan
description: |
  扫描内网192.168.0.0/24网段资产，自动更新 Supabase + 飞书双数据源。新发现的IP标记为"新发现"，已离线的标记为"离线"。使用场景：网络资产管理、资产巡检、安全扫描。
---

# Network Asset Scanner Skill

扫描内网资产并同步到 Supabase + 飞书（双源同步）。

## ⚠️ 重要：正确的同步流程

```
正确流程（必须按顺序）：
1. 扫描网络 -> 获取在线主机列表
2. 更新 Supabase（主数据源）
3. 从 Supabase 同步到飞书（展示/备份）

❌ 错误流程：
- 只更新飞书，不更新 Supabase
- 先更新飞书，再更新 Supabase
```

## 功能

1. **网络扫描** - 使用 nmap 扫描 192.168.0.0/24 网段
2. **Supabase 同步** - 更新主数据源
3. **飞书同步** - 从 Supabase 同步到飞书（展示/备份）
4. **去重逻辑** - ✅ 已存在的IP执行更新，不再重复创建
5. **状态标记**:
   - 新发现的IP → "新发现"
   - 扫描到的IP → "在线"
   - 表格有但未扫描到 → "离线"

## 数据源配置

### Supabase（主数据源）
- **表名**: soc_assets
- **URL**: https://bzivkqjuftytrdnksrxs.supabase.co
- **字段**: asset_ip, asset_description, asset_status, status_updated_at

### 飞书（展示/备份）
- **URL**: https://my.feishu.cn/base/YBfnb26B9ap5pNszOSqcQrsrnSg?table=tbl7uZwUQBnpqWbm
- **App Token**: YBfnb26B9ap5pNszOSqcQrsrnSg
- **Table ID**: tbl7uZwUQBnpqWbm
- **字段**:
  - 资产IP (Text, Primary)
  - 资产说明 (Text)
  - 资产状态 (Text) - 在线/离线/新发现/已删除
  - 状态更新时间 (DateTime)

## 使用方法

### 方式一：完整扫描（更新 Supabase + 提示飞书同步）

```bash
python3 /home/xiejava/.openclaw/workspace/skills/network-scan/network_scan_unified.py
```

### 方式二：通过 OpenClaw 手动同步

当你说"扫描内网资产"时，OpenClaw 会：
1. 扫描网络获取在线主机列表
2. ✅ 更新 Supabase（主数据源）
3. ✅ 从 Supabase 同步到飞书

## 去重逻辑详解

### 正确的双源同步流程

```
1. 扫描网络 -> 获取在线主机列表
2. 获取 Supabase 已有记录
3. 构建 IP -> id 映射
4. 更新 Supabase（第一步）:
   - 在线主机: 已存在 -> 更新状态为"在线"
   - 在线主机: 不存在 -> 创建新记录
   - 离线主机: 原在线现离线 -> 标记为"离线"
5. 同步到飞书（第二步）:
   - 从 Supabase 读取最新数据
   - 对比飞书表格，执行相同操作
```

### 关键代码（Supabase）

```python
# 获取已有记录
records = supabase_request("GET", "soc_assets?select=*")
ip_map = {r['asset_ip']: r for r in records}

# 在线主机处理
for ip in online_hosts:
    if ip in ip_map:
        update_supabase_record(ip_map[ip]['id'], '在线')
    else:
        create_supabase_record(ip, '新发现设备', '新发现')
```

### 关键代码（飞书同步）

```python
# 从 Supabase 同步到飞书
for record in supabase_records:
    ip = record['asset_ip']
    status = record['asset_status']
    if ip in feishu_ip_map:
        update_feishu_record(feishu_ip_map[ip], status, timestamp)
    else:
        create_feishu_record(ip, status, description, timestamp)
```

## 时间戳格式

**飞书 DateTime 字段需要毫秒级时间戳**

```python
# ✅ 正确
timestamp = int(time.time() * 1000)

# ❌ 错误
timestamp = int(time.time())
```

## 常见问题

### Q: 为什么 Supabase 没有重复但飞书有？
**A**: 因为之前的流程只更新飞书，没有更新 Supabase。现在已修复为先更新 Supabase 再同步飞书。

### Q: 如何验证同步成功？
**A**: 
- 检查 Supabase: asset_status 为最新状态
- 检查飞书: 与 Supabase 保持一致

## 脚本文件

- `network_scan_unified.py` - ✅ 完整双源同步脚本
- `network_scan.py` - 旧版（仅飞书）

## 更新日志

**2026-03-04**:
- ✅ **修复同步流程** - 添加先更新Supabase再更新飞书的逻辑
- ✅ 添加双源同步说明
- ✅ 明确主数据源(Supabase)和展示源(飞书)的区别
