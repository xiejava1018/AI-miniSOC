#!/usr/bin/env python3
"""
网络资产扫描脚本 - 自动扫描内网并更新 Supabase + 飞书（双源同步）

正确流程：
1. 扫描网络 -> 获取在线主机列表
2. 更新 Supabase（主数据源）
3. 从 Supabase 同步到飞书（展示/备份）

使用方法: 
  cp .env.example .env
  # 编辑 .env 填入你的配置
  python3 network_scan_unified.py

环境变量（配置在 .env 文件中）:
  NETWORK - 扫描网段，默认 192.168.0.0/24
  SUPABASE_URL - Supabase 项目 URL
  SUPABASE_KEY - Supabase API Key (anon public)
  FEISHU_APP_TOKEN - 飞书多维表格 App Token
  FEISHU_TABLE_ID - 飞书多维表格 Table ID
  FEISHU_APP_ID - 飞书应用 App ID
  FEISHU_APP_SECRET - 飞书应用 App Secret

更新日志:
2026-03-04: 修复流程 - 添加先更新Supabase再更新飞书的逻辑
2026-03-10: 修复去重 - 飞书同步时检查IP是否已存在，避免重复创建
"""
import subprocess
import json
import time
import os
import requests
from datetime import datetime
from pathlib import Path

# ===== 配置区域 =====
# 从环境变量或 .env 文件加载配置
def load_config():
    """加载配置"""
    config = {}
    
    # 检查 .env 文件
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    
    config['NETWORK'] = os.environ.get('NETWORK', '192.168.0.0/24')
    config['SUPABASE_URL'] = os.environ.get('SUPABASE_URL', '')
    config['SUPABASE_KEY'] = os.environ.get('SUPABASE_KEY', '')
    config['FEISHU_APP_TOKEN'] = os.environ.get('FEISHU_APP_TOKEN', '')
    config['FEISHU_TABLE_ID'] = os.environ.get('FEISHU_TABLE_ID', '')
    config['FEISHU_APP_ID'] = os.environ.get('FEISHU_APP_ID', '')
    config['FEISHU_APP_SECRET'] = os.environ.get('FEISHU_APP_SECRET', '')
    
    return config

CONFIG = load_config()
NETWORK = CONFIG['NETWORK']
SUPABASE_URL = CONFIG['SUPABASE_URL']
SUPABASE_KEY = CONFIG['SUPABASE_KEY']
FEISHU_APP_TOKEN = CONFIG['FEISHU_APP_TOKEN']
FEISHU_TABLE_ID = CONFIG['FEISHU_TABLE_ID']
FEISHU_APP_ID = CONFIG['FEISHU_APP_ID']
FEISHU_APP_SECRET = CONFIG['FEISHU_APP_SECRET']

# ===== Supabase 函数 =====

def supabase_request(method, endpoint, data=None):
    """发送请求到 Supabase API"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ 请配置 SUPABASE_URL 和 SUPABASE_KEY")
        return None
        
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        if method == "GET":
            req = requests.Request("GET", url, headers=headers)
        elif method == "POST":
            req = requests.Request("POST", url, headers=headers, data=json.dumps(data))
        elif method == "PATCH":
            req = requests.Request("PATCH", url, headers=headers, data=json.dumps(data))
        elif method == "Delete":
            req = requests.Request("DELETE", url, headers=headers)
        
        prepped = req.prepare()
        with requests.Session().send(prepped) as response:
            if response.status_code == 204:
                return []
            return json.loads(response.text)
    except Exception as e:
        print(f"❌ Supabase 请求错误: {e}")
        return None

def get_supabase_records():
    """获取 Supabase 所有资产记录"""
    print("📦 获取 Supabase 资产表...")
    records = supabase_request("GET", "soc_assets?select=*")
    if records is None:
        return []
    return records

def create_supabase_record(ip, description, status="新发现"):
    """创建 Supabase 新记录"""
    data = {
        "asset_ip": ip,
        "asset_description": description,
        "asset_status": status,
        "status_updated_at": datetime.utcnow().isoformat() + "Z"
    }
    result = supabase_request("POST", "soc_assets", data)
    return result

def update_supabase_record(id, status):
    """更新 Supabase 记录状态"""
    data = {
        "asset_status": status,
        "status_updated_at": datetime.utcnow().isoformat() + "Z"
    }
    result = supabase_request("PATCH", f"soc_assets?id=eq.{id}", data)
    return result

# ===== 飞书函数 =====

def get_feishu_access_token():
    """获取飞书应用 access_token"""
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        print("❌ 请配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        return None
        
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    data = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        if result.get("code") == 0:
            return result.get("tenant_access_token")
        else:
            print(f"❌ 获取飞书token失败: {result.get('msg')}")
            return None
    except Exception as e:
        print(f"❌ 飞书认证错误: {e}")
        return None

def get_feishu_records():
    """获取飞书表格所有记录"""
    if not FEISHU_APP_TOKEN or not FEISHU_TABLE_ID:
        print("❌ 请配置 FEISHU_APP_TOKEN 和 FEISHU_TABLE_ID")
        return []
    
    token = get_feishu_access_token()
    if not token:
        return []
    
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{FEISHU_APP_TOKEN}/tables/{FEISHU_TABLE_ID}/records"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        all_records = []
        page_token = None
        
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            
            response = requests.get(url, headers=headers, params=params)
            result = response.json()
            
            if result.get("code") == 0:
                all_records.extend(result.get("data", {}).get("items", []))
                page_token = result.get("data", {}).get("page_token")
                if not page_token:
                    break
            else:
                print(f"❌ 获取飞书记录失败: {result.get('msg')}")
                break
        
        return all_records
    except Exception as e:
        print(f"❌ 飞书API错误: {e}")
        return []

def create_feishu_record(ip, status, description, timestamp):
    """创建飞书记录"""
    if not FEISHU_APP_TOKEN or not FEISHU_TABLE_ID:
        print("❌ 请配置 FEISHU_APP_TOKEN 和 FEISHU_TABLE_ID")
        return False
    
    token = get_feishu_access_token()
    if not token:
        return False
    
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{FEISHU_APP_TOKEN}/tables/{FEISHU_TABLE_ID}/records"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "fields": {
            "资产IP": ip,
            "资产状态": status,
            "资产说明": description,
            "状态更新时间": timestamp
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        if result.get("code") == 0:
            print(f"   🆕 飞书创建: {ip} -> {status}")
            return True
        else:
            print(f"   ❌ 飞书创建失败: {ip} - {result.get('msg')}")
            return False
    except Exception as e:
        print(f"   ❌ 飞书创建错误: {e}")
        return False

def update_feishu_record(record_id, status, timestamp):
    """更新飞书记录"""
    if not FEISHU_APP_TOKEN or not FEISHU_TABLE_ID:
        print("❌ 请配置 FEISHU_APP_TOKEN 和 FEISHU_TABLE_ID")
        return False
    
    token = get_feishu_access_token()
    if not token:
        return False
    
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{FEISHU_APP_TOKEN}/tables/{FEISHU_TABLE_ID}/records/{record_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "fields": {
            "资产状态": status,
            "状态更新时间": timestamp
        }
    }
    
    try:
        response = requests.put(url, headers=headers, json=data)
        result = response.json()
        if result.get("code") == 0:
            print(f"   ✅ 飞书更新: {record_id} -> {status}")
            return True
        else:
            print(f"   ❌ 飞书更新失败: {record_id} - {result.get('msg')}")
            return False
    except Exception as e:
        print(f"   ❌ 飞书更新错误: {e}")
        return False

# ===== 网络扫描 =====

def scan_network(network):
    """扫描指定网段的在线主机"""
    print(f"🔍 正在扫描 {network} 网段...")
    
    try:
        result = subprocess.run(
            f"nmap -sn {network} -oG -",
            shell=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        online_hosts = []
        for line in result.stdout.split('\n'):
            if 'Up' in line:
                parts = line.split()
                if len(parts) >= 2:
                    ip = parts[1]
                    online_hosts.append(ip)
        
        online_hosts.sort()
        print(f"✅ 发现 {len(online_hosts)} 台在线主机")
        return online_hosts
        
    except Exception as e:
        print(f"❌ 扫描错误: {e}")
        return []

def get_current_timestamp():
    """获取当前时间戳（毫秒级）"""
    return int(time.time() * 1000)

# ===== 主流程 =====

def main():
    print("=" * 60)
    print("🔌 网络资产扫描 (Supabase + 飞书 双源同步)")
    print("=" * 60)
    print(f"📅 扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 目标网段: {NETWORK}")
    print("=" * 60)
    
    # 检查配置
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ 请先配置 .env 文件")
        print("   cp .env.example .env")
        print("   # 然后编辑 .env 填入你的配置")
        return
    
    # 1. 扫描网络
    online_hosts = scan_network(NETWORK)
    online_set = set(online_hosts)
    
    if online_hosts:
        print("\n📋 在线主机列表:")
        for i, ip in enumerate(online_hosts, 1):
            print(f"  {i:2d}. {ip}")
    
    # 2. 获取 Supabase 已有记录
    supabase_records = get_supabase_records()
    supabase_ip_map = {r['asset_ip']: r for r in supabase_records}
    
    print(f"\n📦 Supabase 已有资产: {len(supabase_ip_map)} 条")
    
    # 3. 更新 Supabase（第一步！）
    print("\n" + "=" * 60)
    print("📊 步骤1: 更新 Supabase（主数据源）")
    print("=" * 60)
    
    current_time = datetime.utcnow().isoformat() + "Z"
    stats = {'update': 0, 'create': 0, 'offline': 0}
    
    # 3.1 处理在线主机
    for ip in online_hosts:
        if ip in supabase_ip_map:
            # 已存在，检查状态
            record = supabase_ip_map[ip]
            if record.get('asset_status') != '在线':
                update_supabase_record(record['id'], '在线')
                print(f"   ✅ {ip}: {record.get('asset_status')} -> 在线")
                stats['update'] += 1
            else:
                print(f"   ⏭️  {ip}: 状态已是在线")
        else:
            # 新发现
            create_supabase_record(ip, '新发现设备', '新发现')
            print(f"   🆕 {ip}: 新发现")
            stats['create'] += 1
    
    # 3.2 处理离线主机
    for ip, record in supabase_ip_map.items():
        if ip not in online_set and record.get('asset_status') == '在线':
            update_supabase_record(record['id'], '离线')
            print(f"   ❌ {ip}: 在线 -> 离线")
            stats['offline'] += 1
    
    print(f"\n📈 Supabase 更新统计:")
    print(f"   • 在线更新: {stats['update']} 条")
    print(f"   • 新增: {stats['create']} 条")
    print(f"   • 离线标记: {stats['offline']} 条")
    
    # 4. 同步到飞书（第二步！）- 带去重逻辑
    print("\n" + "=" * 60)
    print("📊 步骤2: 同步到飞书（展示/备份）- 带去重")
    print("=" * 60)
    
    # 获取飞书已有记录
    feishu_records = get_feishu_records()
    
    # 构建飞书 IP -> record_id 映射（排除已删除的）
    feishu_ip_map = {}
    for record in feishu_records:
        ip = record.get('fields', {}).get('资产IP', '')
        status = record.get('fields', {}).get('资产状态', '')
        if ip and status != '已删除':
            feishu_ip_map[ip] = {
                'record_id': record.get('record_id', ''),
                'status': status
            }
    
    print(f"📋 飞书已有资产: {len(feishu_ip_map)} 条")
    
    # 同步时间戳
    current_timestamp = get_current_timestamp()
    
    feishu_stats = {'update': 0, 'create': 0, 'offline': 0}
    
    # 4.1 处理在线主机
    for ip in online_hosts:
        if ip in feishu_ip_map:
            # 已存在，检查状态
            record = feishu_ip_map[ip]
            if record['status'] != '在线':
                update_feishu_record(record['record_id'], '在线', current_timestamp)
                feishu_stats['update'] += 1
            else:
                print(f"   ⏭️  飞书: {ip} 状态已是在线")
        else:
            # 新发现，创建记录
            # 从 Supabase 获取描述
            description = supabase_ip_map.get(ip, {}).get('asset_description', '新发现设备')
            create_feishu_record(ip, '在线', description, current_timestamp)
            feishu_stats['create'] += 1
    
    # 4.2 处理离线主机
    for ip, info in feishu_ip_map.items():
        if ip not in online_set and info['status'] == '在线':
            update_feishu_record(info['record_id'], '离线', current_timestamp)
            feishu_stats['offline'] += 1
    
    print(f"\n📈 飞书同步统计:")
    print(f"   • 在线更新: {feishu_stats['update']} 条")
    print(f"   • 新增: {feishu_stats['create']} 条")
    print(f"   • 离线标记: {feishu_stats['offline']} 条")
    
    # 5. 最终统计
    print("\n" + "=" * 60)
    print("✅ 扫描完成!")
    print("=" * 60)
    print(f"  • 在线主机: {len(online_hosts)} 台")
    print(f"  • Supabase 总资产: {len(supabase_ip_map) + stats['create']} 条")
    print(f"  • 飞书总资产: {len(feishu_ip_map) + feishu_stats['create']} 条")
    print(f"\n  🎯 去重逻辑已生效！")
    print(f"     - 飞书端会检查IP是否已存在")
    print(f"     - 已存在的IP会更新状态，不会重复创建")
    
    return stats

if __name__ == "__main__":
    main()
