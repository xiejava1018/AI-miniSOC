#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络资产扫描脚本 - 自动扫描内网并更新 PostgreSQL + 飞书（双源同步）

功能：
1. 主机发现 - nmap 快速扫描
2. 端口扫描 - 详细扫描开放端口和服务
3. 设备识别 - 识别主机设备类型
4. 双源同步 - PostgreSQL + 飞书

使用方法: 
  cp .env.example .env
  # 编辑 .env 填入你的配置
  python3 network_scan_unified.py

环境变量（配置在 .env 文件中）:
  NETWORK - 扫描网段，默认 192.168.0.0/24
  PGHOST - PostgreSQL 主机
  PGPORT - PostgreSQL 端口，默认 5432
  PGUSER - PostgreSQL 用户
  PGPASSWORD - PostgreSQL 密码
  PGDATABASE - PostgreSQL 数据库名
  FEISHU_APP_TOKEN - 飞书多维表格 App Token
  FEISHU_TABLE_ID - 飞书多维表格 Table ID
  FEISHU_APP_ID - 飞书应用 App ID
  FEISHU_APP_SECRET - 飞书应用 App Secret

更新日志:
2026-03-18: 添加端口扫描和设备识别功能
2026-03-10: 修复去重 - 飞书同步时检查IP是否已存在，避免重复创建
"""
import subprocess
import json
import time
import os
import re
import requests
from datetime import datetime
from pathlib import Path

# ===== 配置区域 =====
def load_config():
    """加载配置"""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
    
    config = {}
    config['NETWORK'] = os.environ.get('NETWORK', '192.168.0.0/24')
    config['PGHOST'] = os.environ.get('PGHOST', 'localhost')
    config['PGPORT'] = os.environ.get('PGPORT', '5432')
    config['PGUSER'] = os.environ.get('PGUSER', 'postgres')
    config['PGPASSWORD'] = os.environ.get('PGPASSWORD', '')
    config['PGDATABASE'] = os.environ.get('PGDATABASE', 'postgres')
    config['FEISHU_APP_TOKEN'] = os.environ.get('FEISHU_APP_TOKEN', '')
    config['FEISHU_TABLE_ID'] = os.environ.get('FEISHU_TABLE_ID', '')
    config['FEISHU_APP_ID'] = os.environ.get('FEISHU_APP_ID', '')
    config['FEISHU_APP_SECRET'] = os.environ.get('FEISHU_APP_SECRET', '')
    
    return config

CONFIG = load_config()
NETWORK = CONFIG['NETWORK']
PGHOST = CONFIG['PGHOST']
PGPORT = CONFIG['PGPORT']
PGUSER = CONFIG['PGUSER']
PGPASSWORD = CONFIG['PGPASSWORD']
PGDATABASE = CONFIG['PGDATABASE']
FEISHU_APP_TOKEN = CONFIG['FEISHU_APP_TOKEN']
FEISHU_TABLE_ID = CONFIG['FEISHU_TABLE_ID']
FEISHU_APP_ID = CONFIG['FEISHU_APP_ID']
FEISHU_APP_SECRET = CONFIG['FEISHU_APP_SECRET']

# ===== PostgreSQL 函数 =====

def run_psql(sql):
    """运行 SQL 命令"""
    env = os.environ.copy()
    env['PGPASSWORD'] = PGPASSWORD
    
    try:
        result = subprocess.run(
            ['psql', '-h', PGHOST, '-p', PGPORT, '-U', PGUSER, '-d', PGDATABASE, '-c', sql],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def init_pg_tables():
    """初始化 PostgreSQL 表"""
    # 资产表
    sql1 = """
    CREATE TABLE IF NOT EXISTS soc_assets (
        id TEXT PRIMARY KEY,
        asset_ip TEXT UNIQUE NOT NULL,
        asset_description TEXT,
        asset_status TEXT DEFAULT '离线',
        status_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    success1, _, _ = run_psql(sql1)
    
    # 端口表
    sql2 = """
    CREATE TABLE IF NOT EXISTS soc_asset_ports (
        id SERIAL PRIMARY KEY,
        asset_ip TEXT NOT NULL,
        port INTEGER NOT NULL,
        protocol TEXT DEFAULT 'tcp',
        service TEXT,
        version TEXT,
        status TEXT DEFAULT 'open',
        scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(asset_ip, port, protocol)
    );
    """
    success2, _, _ = run_psql(sql2)
    
    return success1 and success2

def get_pg_assets():
    """获取 PostgreSQL 所有资产记录"""
    sql = "SELECT id, asset_ip, asset_description, asset_status, status_updated_at FROM soc_assets"
    env = os.environ.copy()
    env['PGPASSWORD'] = PGPASSWORD
    
    try:
        result = subprocess.run(
            ['psql', '-h', PGHOST, '-p', PGPORT, '-U', PGUSER, '-d', PGDATABASE, '-c', sql, '-t', '-A', '-F', ','],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"❌ 获取记录错误: {result.stderr}")
            return []
        
        records = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                parts = line.split(',')
                if len(parts) >= 2:
                    records.append({
                        'id': parts[0].strip(),
                        'asset_ip': parts[1].strip(),
                        'asset_description': parts[2].strip() if len(parts) > 2 else '',
                        'asset_status': parts[3].strip() if len(parts) > 3 else '离线',
                        'status_updated_at': parts[4].strip() if len(parts) > 4 else ''
                    })
        return records
    except Exception as e:
        print(f"❌ 获取记录错误: {e}")
        return []

def create_pg_asset(ip, description, status="新发现"):
    """创建 PostgreSQL 资产记录"""
    import uuid
    asset_id = str(uuid.uuid4())
    sql = f"INSERT INTO soc_assets (id, asset_ip, asset_description, asset_status) VALUES ('{asset_id}', '{ip}', '{description}', '{status}') ON CONFLICT (asset_ip) DO NOTHING"
    success, stdout, stderr = run_psql(sql)
    return success

def update_pg_asset(ip, status, description=None):
    """更新 PostgreSQL 资产记录"""
    if description:
        sql = f"UPDATE soc_assets SET asset_status = '{status}', asset_description = '{description}', status_updated_at = CURRENT_TIMESTAMP WHERE asset_ip = '{ip}'"
    else:
        sql = f"UPDATE soc_assets SET asset_status = '{status}', status_updated_at = CURRENT_TIMESTAMP WHERE asset_ip = '{ip}'"
    success, stdout, stderr = run_psql(sql)
    return success

def create_pg_port(ip, port, protocol, service, version):
    """创建端口记录"""
    sql = f"INSERT INTO soc_asset_ports (asset_ip, port, protocol, service, version) VALUES ('{ip}', {port}, '{protocol}', '{service}', '{version}') ON CONFLICT (asset_ip, port, protocol) DO UPDATE SET service = EXCLUDED.service, version = EXCLUDED.version, scanned_at = CURRENT_TIMESTAMP"
    success, _, _ = run_psql(sql)
    return success

def clear_pg_ports(ip):
    """清除旧端口记录"""
    sql = f"DELETE FROM soc_asset_ports WHERE asset_ip = '{ip}'"
    success, _, _ = run_psql(sql)
    return success

# ===== 设备识别 =====
DEVICE_PATTERNS = {
    'Router': ['OpenWrt', 'DD-WRT', 'Tomato', 'Router', 'Gateway', 'TP-LINK', 'Netgear', 'ASUS Router'],
    'Windows PC': ['Microsoft Windows', 'Windows 10', 'Windows 11', 'Windows Server'],
    'Linux PC': ['Ubuntu', 'Debian', 'CentOS', 'Fedora', 'Red Hat', 'Linux'],
    'Mac': ['Apple', 'MacBook', 'iMac', 'macOS'],
    'Proxmox': ['Proxmox', 'KVM', 'QEMU', 'Virtual Machine'],
    'Docker': ['Docker', 'Container'],
    'Printer': ['HP LaserJet', 'Canon', 'Epson', 'Brother', 'Printer'],
    'Camera': ['Axis', 'Hikvision', 'Dahua', 'IP Camera', 'NVR'],
    'NAS': ['Synology', 'QNAP', 'FreeNAS', 'TrueNAS', 'NAS'],
    'Phone': ['iPhone', 'Android', 'Mobile'],
    'IoT': ['Smart Home', 'Tuya', 'Aqara', 'Zigbee', 'Xiaomi'],
}

def identify_device(nmap_result):
    """根据 nmap 扫描结果识别设备类型"""
    nmap_str = str(nmap_result).lower()
    
    # 检查常见服务推断设备类型
    if 'http' in nmap_str or 'https' in nmap_str:
        if 'router' in nmap_str or 'openwrt' in nmap_str or 'dd-wrt' in nmap_str:
            return 'Router'
        if 'proxmox' in nmap_str:
            return 'Proxmox'
        if 'synology' in nmap_str or 'qnap' in nmap_str:
            return 'NAS'
        if 'nginx' in nmap_str or 'apache' in nmap_str:
            return 'Web Server'
    
    if 'ssh' in nmap_str:
        if 'openwrt' in nmap_str:
            return 'Router'
        if 'linux' in nmap_str:
            return 'Linux Server'
    
    if 'smb' in nmap_str or 'samba' in nmap_str:
        if 'windows' in nmap_str:
            return 'Windows PC'
    
    if 'rdp' in nmap_str:
        return 'Windows PC'
    
    if 'printer' in nmap_str or 'ipp' in nmap_str:
        return 'Printer'
    
    if 'rtsp' in nmap_str or 'onvif' in nmap_str:
        return 'Camera'
    
    if 'docker' in nmap_str:
        return 'Docker'
    
    if 'mysql' in nmap_str or 'postgresql' in nmap_str or 'mongodb' in nmap_str:
        return 'Database Server'
    
    if 'redis' in nmap_str:
        return 'Cache Server'
    
    if 'ldap' in nmap_str or 'kerberos' in nmap_str:
        return 'Domain Controller'
    
    # 默认尝试从 OS 识别
    for device_type, patterns in DEVICE_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in nmap_str:
                return device_type
    
    return 'Unknown Device'

# ===== 网络扫描 =====

def quick_scan(network):
    """快速扫描网段在线主机"""
    print(f"🔍 正在快速扫描 {network} 网段...")
    
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

def detailed_scan(ip):
    """详细扫描单个主机的端口和服务"""
    print(f"   🔬 详细扫描 {ip}...")
    
    try:
        # 快速扫描 常用端口
        common_ports = "21,22,23,80,443,445,3389,8080,8443,3306,5432,1521,1433,9000,9090,27017,6379"
        result = subprocess.run(
            f"nmap -sV -p {common_ports} -T5 {ip} --open",
            shell=True,
            capture_output=True,
            text=True,
            timeout=20
        )
        
        ports = []
        nmap_output = result.stdout
        
        # 解析端口信息
        for line in nmap_output.split('\n'):
            line = line.strip()
            # 匹配端口行: 22/tcp   open  ssh     OpenSSH 8.2
            match = re.match(r'(\d+)/(tcp|udp)\s+open\s+(\S+)\s+(.*)', line)
            if match:
                port = int(match.group(1))
                protocol = match.group(2)
                service = match.group(3)
                version = match.group(4).strip() if match.group(4) else ''
                ports.append({
                    'port': port,
                    'protocol': protocol,
                    'service': service,
                    'version': version[:100]  # 限制版本字符串长度
                })
        
        # 识别设备类型
        device_type = identify_device(nmap_output)
        
        return ports, device_type
        
    except Exception as e:
        print(f"   ❌ 详细扫描失败: {e}")
        return [], 'Unknown Device'

def get_current_timestamp():
    """获取当前时间戳（毫秒级）"""
    return int(time.time() * 1000)

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

# ===== 主流程 =====

def main():
    print("=" * 60)
    print("🔌 网络资产扫描 (PostgreSQL + 飞书)")
    print("=" * 60)
    print(f"📅 扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 目标网段: {NETWORK}")
    print(f"🗄️ 数据库: {PGHOST}/{PGDATABASE}")
    print("=" * 60)
    
    if not PGPASSWORD:
        print("❌ 请先配置 .env 文件")
        return
    
    # 初始化数据库表
    print("📦 初始化数据库表...")
    if not init_pg_tables():
        print("❌ 数据库初始化失败")
        return
    print("✅ 数据库表就绪")
    
    # 1. 快速扫描在线主机
    online_hosts = quick_scan(NETWORK)
    online_set = set(online_hosts)
    
    if online_hosts:
        print("\n📋 在线主机列表:")
        for i, ip in enumerate(online_hosts, 1):
            print(f"  {i:2d}. {ip}")
    
    # 2. 获取 PostgreSQL 已有资产
    pg_assets = get_pg_assets()
    pg_ip_map = {r['asset_ip']: r for r in pg_assets}
    
    print(f"\n📦 PostgreSQL 已有资产: {len(pg_ip_map)} 条")
    
    # 3. 更新 PostgreSQL（第一步！）
    print("\n" + "=" * 60)
    print("📊 步骤1: 更新 PostgreSQL（主机发现 + 端口扫描 + 设备识别）")
    print("=" * 60)
    
    stats = {'update': 0, 'create': 0, 'offline': 0}
    
    # 3.1 处理在线主机（详细扫描）
    for ip in online_hosts:
        # 详细扫描端口和服务
        ports, device_type = detailed_scan(ip)
        
        # 清除旧端口记录
        clear_pg_ports(ip)
        
        # 保存新端口记录
        port_count = 0
        for p in ports:
            create_pg_port(ip, p['port'], p['protocol'], p['service'], p['version'])
            port_count += 1
        
        # 设备描述
        if ports:
            port_info = ', '.join([f"{p['port']}/{p['service']}" for p in ports[:5]])
            if len(ports) > 5:
                port_info += f" (+{len(ports)-5} ports)"
            description = f"{device_type} ({port_info})"
        else:
            description = device_type
        
        if ip in pg_ip_map:
            # 已存在，检查状态
            record = pg_ip_map[ip]
            old_status = record.get('asset_status', '离线')
            old_desc = record.get('asset_description', '')
            
            # 更新状态
            new_status = '在线' if old_status != '新发现' else '在线'
            
            # 更新描述（如果识别到更好的描述）
            if device_type != 'Unknown Device' and (old_desc == '' or 'Unknown' in old_desc):
                update_pg_asset(ip, new_status, description)
                print(f"   ✅ {ip}: {old_status} -> {new_status}, 设备: {description}")
            else:
                update_pg_asset(ip, new_status)
                if old_status != new_status:
                    print(f"   ✅ {ip}: {old_status} -> {new_status}")
                else:
                    print(f"   ⏭️  {ip}: 状态已是在线, 端口: {port_count}")
            stats['update'] += 1
        else:
            # 新发现
            create_pg_asset(ip, description, '新发现')
            print(f"   🆕 {ip}: 新发现, 设备: {description}, 端口: {port_count}")
            stats['create'] += 1
    
    # 3.2 处理离线主机
    for ip, record in pg_ip_map.items():
        if ip not in online_set and record.get('asset_status') == '在线':
            update_pg_asset(ip, '离线')
            print(f"   ❌ {ip}: 在线 -> 离线")
            stats['offline'] += 1
    
    print(f"\n📈 PostgreSQL 更新统计:")
    print(f"   • 在线更新: {stats['update']} 条")
    print(f"   • 新增: {stats['create']} 条")
    print(f"   • 离线标记: {stats['offline']} 条")
    
    # 4. 同步到飞书（第二步！）
    print("\n" + "=" * 60)
    print("📊 步骤2: 同步到飞书")
    print("=" * 60)
    
    feishu_records = get_feishu_records()
    
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
    
    current_timestamp = get_current_timestamp()
    feishu_stats = {'update': 0, 'create': 0, 'offline': 0}
    
    # 4.1 处理在线主机
    for ip in online_hosts:
        if ip in feishu_ip_map:
            record = feishu_ip_map[ip]
            if record['status'] != '在线':
                update_feishu_record(record['record_id'], '在线', current_timestamp)
                feishu_stats['update'] += 1
            else:
                print(f"   ⏭️  飞书: {ip} 状态已是在线")
        else:
            description = pg_ip_map.get(ip, {}).get('asset_description', '新发现设备')
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
    print(f"  • PostgreSQL 资产: {len(pg_ip_map) + stats['create']} 条")
    print(f"  • 飞书资产: {len(feishu_ip_map) + feishu_stats['create']} 条")
    
    # 显示扫描结果
    print("\n📊 扫描结果示例:")
    for ip in online_hosts[:5]:
        desc = pg_ip_map.get(ip, {}).get('asset_description', 'N/A')
        print(f"   {ip}: {desc}")
    
    return stats

if __name__ == "__main__":
    main()
