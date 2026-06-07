# TP-Link TL-R479GP-AC 路由器对接方案

> 版本: v1.0
> 日期: 2026-06-07
> 状态: API 已验证通过，待实现代码

## 1. 概述

TP-Link TL-R479GP-AC 是一台企业级 VPN 安全路由器，通过其 SLP (Single Page Application) Web 管理界面提供的 JSON API，可以获取在线终端设备信息，同步到 AI-miniSOC 资产库。

### 可获取的数据

| 数据项 | 说明 |
|--------|------|
| 在线终端列表 | IP、MAC、主机名、连接类型、状态 |
| 无线详情 | SSID、频段(2.4GHz/5GHz)、信号强度(rssi) |
| 流量信息 | 上行/下行速度 (up_speed/down_speed) |
| 接入点信息 | AP 名称 (如 TL-XAP1800GI-PoE-0002) |
| 连接时间 | 接入日期和时间 |
| 带宽控制 | 上下行限速 (up_limit/down_limit) |

### 测试环境

- **路由器地址**: http://192.168.0.1 (HTTP, 非 HTTPS)
- **固件版本**: 2023-03-21 (SLP 界面)
- **管理界面**: TP-Link SLP (jQuery SPA)
- **实测在线设备**: 20 台

---

## 2. API 逆向分析

### 2.1 认证流程

```
浏览器 → POST / (login JSON) → 服务器返回 stok → 后续请求带 stok
```

#### 关键发现

1. **密码不是明文传输**，也不是 RSA 加密，而是 **XOR 字符映射混淆**
2. **stok 使用等号**（`stok=xxx`）而非斜杠（`stok/xxx`）拼接在 URL 中
3. **必须带 `X-Requested-With: XMLHttpRequest` 头**，否则服务器返回 HTML 登录页

### 2.2 密码加密算法 (securityEncode)

TP-Link SLP 界面使用 XOR 混淆加密密码，**不是 RSA**（虽然代码中有 encrypt.js/RSA，但那是给 TP-Link 云管理用的）。

#### 算法原理

```
输入: password (用户密码)
密钥1: "RDpbLfCPsJZ7fiv" (15 字符)
密钥2: "yLwVl0zKqws7LgKPRQ84Mdt708T1qQ3Ha7xv3H7NyU84p21BriUWBU43odz3iP4rBL3cD02KZciXTysVXiV8ngg6vL48rPJyAUw0HurW20xqxv9aYb4M9wK1Ae0wlro510qXeU07kV57fQMc8L6aLgMLwygtc0F10a0Dg70TOoouyFhdysuRMO51yY5ZlOZZLEal1h0t9YQW0Ko7oBwmCAHoic4HYbUyVeU3sfQ1xtXcPcf1aT303wAQhv66qzW" (223 字符映射表)

过程:
  for i in range(max(len(password), len(key1))):
      char_code = password[i] XOR key1[i]  (超出部分用 187 做 XOR)
      result += key2[char_code % len(key2)]
```

#### Python 实现

```python
def tplink_security_encode(
    password: str,
    key1: str = "RDpbLfCPsJZ7fiv",
    key2: str = "yLwVl0zKqws7LgKPRQ84Mdt708T1qQ3Ha7xv3H7NyU84p21BriUWBU43odz3iP4rBL3cD02KZciXTysVXiV8ngg6vL48rPJyAUw0HurW20xqxv9aYb4M9wK1Ae0wlro510qXeU07kV57fQMc8L6aLgMLwygtc0F10a0Dg70TOoouyFhdysuRMO51yY5ZlOZZLEal1h0t9YQW0Ko7oBwmCAHoic4HYbUyVeU3sfQ1xtXcPcf1aT303wAQhv66qzW"
) -> str:
    """TP-Link SLP 密码加密算法"""
    result = ""
    g, m, f = len(password), len(key1), len(key2)
    k = max(g, m)
    for e in range(k):
        l = t = 187
        if e >= g:
            t = ord(key1[e])
        elif e >= m:
            l = ord(password[e])
        else:
            l = ord(password[e])
            t = ord(key1[e])
        result += key2[(l ^ t) % f]
    return result
```

---

## 3. API 接口详细说明

### 3.1 登录获取 Token

**请求**:

```http
POST http://192.168.0.1/ HTTP/1.1
Content-Type: application/json; charset=UTF-8

{
    "method": "do",
    "login": {
        "username": "<用户名>",
        "password": "<加密后的密码>"
    }
}
```

**成功响应** (HTTP 200):

```json
{
    "stok": "cc774a8694017e2d7df36b90394b01c7",
    "error_code": 0
}
```

**失败响应** (HTTP 401):

```json
{
    "data": {"group": 0, "time": 4, "code": -40401},
    "error_code": -40401
}
```

- `time`: 剩余尝试次数
- `code -40401`: 用户名或密码错误
- `code ESYSLOCKED`: 账户被锁定

### 3.2 获取在线终端设备列表

**请求**:

```http
POST http://192.168.0.1/stok=<stok>/ds HTTP/1.1
Content-Type: application/json; charset=UTF-8
X-Requested-With: XMLHttpRequest
Referer: http://192.168.0.1/

{
    "method": "get",
    "host_management": {
        "table": "host_info"
    }
}
```

> ⚠️ **关键**: URL 中 `stok` 使用**等号** (`stok=xxx`)，不是斜杠。
> ⚠️ **关键**: 必须带 `X-Requested-With: XMLHttpRequest` 请求头。

**成功响应** (HTTP 200):

```json
{
    "host_management": {
        "host_info": [
            {
                "host_info_1": {
                    "ip": "192.168.0.30",
                    "mac": "C0-94-44-C9-CE-38",
                    "type": "wired",
                    "hostname": "anonymous",
                    "state": "online",
                    "interface": "br-lan",
                    "is_cur_host": false,
                    "down_speed": "0",
                    "up_speed": "0",
                    "down_limit": "0",
                    "up_limit": "0",
                    "host_save": "off"
                }
            },
            {
                "host_info_2": {
                    "ip": "192.168.0.8",
                    "mac": "9E-8D-2C-8C-3E-CF",
                    "type": "wireless",
                    "hostname": "Redmi-Note-13-Pro",
                    "state": "online",
                    "interface": "br-lan",
                    "ssid": "TP-LINK_Guest_3ED4",
                    "freq_name": "2.4GHz",
                    "freq_unit": "1",
                    "rssi": "-60",
                    "ap_name": "TL-XAP1800GI-PoE-0002",
                    "connect_date": "2026%2f06%2f07",
                    "connect_time": "10%3a12%3a39",
                    "encode": "1",
                    "vlan_id": "4084",
                    "down_speed": "2938",
                    "up_speed": "27",
                    "down_limit": "0",
                    "up_limit": "0",
                    "host_save": "off",
                    "is_cur_host": false
                }
            }
        ],
        "count": {
            "host_info": 20
        }
    },
    "error_code": 0
}
```

### 3.3 响应字段说明

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `ip` | string | 设备 IP 地址 | `"192.168.0.30"` |
| `mac` | string | MAC 地址（`-` 分隔） | `"C0-94-44-C9-CE-38"` |
| `type` | string | 连接类型 | `"wired"` / `"wireless"` |
| `hostname` | string | 主机名 | `"Redmi-Note-13-Pro"` |
| `state` | string | 在线状态 | `"online"` |
| `interface` | string | 接口 | `"br-lan"` |
| `is_cur_host` | boolean | 是否为当前管理主机 | `true` / `false` |
| `ssid` | string | WiFi 名称（仅无线） | `"TP-LINK_3ED4"` |
| `freq_name` | string | 频段（仅无线） | `"2.4GHz"` / `"5GHz"` |
| `rssi` | string | 信号强度 dBm（仅无线） | `"-60"` |
| `ap_name` | string | 接入 AP 名称（仅无线） | `"TL-XAP1800GI-PoE-0002"` |
| `connect_date` | string | 连接日期（URL编码） | `"2026%2f06%2f07"` → `2026/06/07` |
| `connect_time` | string | 连接时间（URL编码） | `"10%3a12%3a39"` → `10:12:39` |
| `down_speed` | string | 下行速度 (Kbps) | `"2938"` |
| `up_speed` | string | 上行速度 (Kbps) | `"27"` |
| `down_limit` | string | 下行限速 | `"0"` = 不限 |
| `up_limit` | string | 上行限速 | `"0"` = 不限 |
| `vlan_id` | string | VLAN ID（仅无线） | `"0"` / `"4084"` |
| `encode` | string | 编码标识 | `"1"` |
| `host_save` | string | 是否保存 | `"on"` / `"off"` |

### 3.4 其他可能可用的 API

根据 SLP 框架结构，以下端点可能可用（需带 stok + XMLHttpRequest 头）：

```json
// DHCP 设置
{"method": "get", "dhcp": {"table": "dhcp"}}

// ARP 绑定
{"method": "get", "ip_mac_bind": {"table": "bind"}}

// 系统信息
{"method": "get", "system": {"info": null}}

// 流量统计
{"method": "get", "statis": {"ip": null}}
```

---

## 4. 集成实现方案

### 4.1 架构设计

```
┌──────────────────────────────────────────────────┐
│                 AI-miniSOC Backend                │
│                                                   │
│  ┌──────────────────────────────────────────┐    │
│  │  RouterClient (services/router_client.py) │    │
│  │                                           │    │
│  │  1. securityEncode() 密码加密             │    │
│  │  2. login() → 获取 stok                   │    │
│  │  3. get_hosts() → 获取终端列表            │    │
│  │  4. logout() → 退出登录                   │    │
│  └───────────────┬──────────────────────────┘    │
│                  │                                │
│  ┌───────────────▼──────────────────────────┐    │
│  │  RouterSyncService                       │    │
│  │                                           │    │
│  │  - 设备 → Asset 映射                      │    │
│  │  - 去重逻辑 (按 IP 或 MAC)                │    │
│  │  - 增量更新 (online/offline 状态变更)     │    │
│  └───────────────┬──────────────────────────┘    │
│                  │                                │
│  ┌───────────────▼──────────────────────────┐    │
│  │  POST /api/v1/assets/sync/from-router     │    │
│  │  (手动触发 / 定时任务)                     │    │
│  └──────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
          │
          │  HTTP (stok=xxx)
          ▼
┌──────────────────────────────────────────────────┐
│        TP-Link TL-R479GP-AC (192.168.0.1)        │
│                                                   │
│  SLP Web Interface → /stok=<token>/ds             │
│  host_management.table = host_info                │
└──────────────────────────────────────────────────┘
```

### 4.2 RouterClient 实现要点

```python
class RouterClient:
    """TP-Link SLP 路由器客户端"""

    XOR_KEY1 = "RDpbLfCPsJZ7fiv"
    XOR_KEY2 = "yLwVl0zKqws7LgKPRQ84Mdt708T1qQ3Ha7xv3H7NyU84p21BriUWBU43odz3iP4rBL3cD02KZciXTysVXiV8ngg6vL48rPJyAUw0HurW20xqxv9aYb4M9wK1Ae0wlro510qXeU07kV57fQMc8L6aLgMLwygtc0F10a0Dg70TOoouyFhdysuRMO51yY5ZlOZZLEal1h0t9YQW0Ko7oBwmCAHoic4HYbUyVeU3sfQ1xtXcPcf1aT303wAQhv66qzW"

    API_HEADERS = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }

    async def login(self) -> str:
        """登录并返回 stok token"""
        enc_pwd = self.security_encode(self.password)
        resp = await self.client.post(
            f"{self.base_url}/",
            json={
                "method": "do",
                "login": {
                    "username": self.username,
                    "password": enc_pwd
                }
            }
        )
        data = resp.json()
        if data.get("error_code") != 0:
            raise AuthenticationError(f"Login failed: {data}")
        self.stok = data["stok"]
        return self.stok

    async def get_hosts(self) -> list[dict]:
        """获取在线终端设备列表"""
        if not self.stok:
            await self.login()

        url = f"{self.base_url}/stok={self.stok}/ds"
        resp = await self.client.post(
            url,
            json={
                "method": "get",
                "host_management": {"table": "host_info"}
            },
            headers=self.API_HEADERS  # 必须带 XMLHttpRequest
        )
        data = resp.json()
        if data.get("error_code") != 0:
            raise APIError(f"Get hosts failed: {data}")

        # 解析嵌套结构
        hosts = []
        for item in data["host_management"]["host_info"]:
            for key, host_data in item.items():
                hosts.append(self._parse_host(host_data))
        return hosts

    async def logout(self):
        """退出登录（释放 stok）"""
        if self.stok:
            url = f"{self.base_url}/stok={self.stok}/ds"
            await self.client.post(
                url,
                json={"method": "do", "system": {"logout": None}},
                headers=self.API_HEADERS
            )
```

### 4.3 设备 → 资产映射规则

| 路由器字段 | Asset 字段 | 转换规则 |
|-----------|-----------|---------|
| `ip` | `asset_ip` | 直接映射 |
| `mac` | `mac_address` | `-` 替换为 `:` |
| `hostname` | `name` | `"anonymous"` → `None` |
| `type` | `asset_type` | `wired` → `"server"`, `wireless` → `"client"` |
| `state` | `asset_status` | `online` → `"online"` |
| - | `data_source` | 固定 `"router"` |
| `type` | `network_zone` | `"lan"` |
| `ssid` + `freq` | `asset_description` | 组合描述 |

### 4.4 增量同步策略

```
1. 调用 get_hosts() 获取当前在线设备列表
2. 查询 data_source="router" 的现有资产
3. 对比逻辑:
   - 新 IP → 创建资产 (created)
   - 已有 IP → 更新 MAC/hostname/状态 (updated)
   - 旧资产不在当前列表 → 标记 offline (如果超过 N 次同步未出现)
4. 记录同步任务到 sync_tasks 表
```

### 4.5 定时同步（可选）

将路由器凭据存入 `soc_system_config` 表（加密存储），通过 APScheduler 或系统 cron 实现定时同步：

```python
# 建议配置项 (存入 soc_system_config, category='router')
ROUTER_HOST = "192.168.0.1"
ROUTER_PORT = 80
ROUTER_USERNAME = "tploginadmin"
ROUTER_PASSWORD = "<加密存储>"
ROUTER_SYNC_INTERVAL = 300  # 秒, 默认 5 分钟
```

---

## 5. 注意事项

### 5.1 安全

- ⚠️ **密码必须加密存储**：使用项目中已有的 Fernet 加密存入数据库
- ⚠️ **stok 是临时令牌**：每次登录获取，会话结束后失效
- ⚠️ **登录失败锁定**：连续输错密码会锁定账户，注意异常处理
- ✅ **只读操作**：`method: "get"` 不会修改路由器配置

### 5.2 可靠性

- **stok 可能过期**：长时间不用会失效，需要重新登录
- **并发限制**：路由器 Web 管理界面同时只允许一个管理员登录，API 调用需要注意不要互相踢出
- **请求频率**：建议同步间隔不低于 1 分钟，避免对路由器造成压力
- **网络超时**：设置合理的 HTTP 超时（建议 10-30 秒）

### 5.3 已知限制

- 路由器管理界面**无正式 API 文档**，接口通过逆向分析获得
- `host_info` 只返回**当前在线**的设备，无法获取历史离线设备
- 无线设备的 `ip` 可能为 `"0.0.0.0"`（尚未完成 DHCP 分配）
- 固件更新可能导致 API 变化（当前固件日期: 2023-03-21）

---

## 6. 逆向分析笔记

### 6.1 文件结构

```
http://192.168.0.1/
├── /                          # 主页面 (HTML SPA, 登录入口)
├── /login.htm                 # 登录页面
├── /stok=<token>/             # 认证后主页面 (同根页面)
├── /stok=<token>/ds           # JSON API 数据端点
└── /web-static/
    ├── js/
    │   ├── libs/
    │   │   ├── encrypt.js         # RSA 加密 (用于云管理, 非登录)
    │   │   ├── security.js        # 160KB 安全相关 (含更多加密)
    │   │   └── md5.js             # MD5 哈希
    │   └── su/
    │       ├── su.js              # 核心框架 (含 securityEncode + orgAuthPwd)
    │       ├── data/proxy.js      # AJAX Proxy (API 通信框架)
    │       └── controller.js      # 控制器
    ├── locale/zh_CN/             # 中文语言包
    └── themes/neoteric/          # 主题样式
```

### 6.2 认证流程序列图

```
Client                          Router
  │                               │
  │  POST / (login JSON)          │
  │  Content-Type: application/json
  │  {"method":"do","login":{     │
  │    "username":"xxx",          │
  │    "password":"<XOR encrypted>"
  │  }}                           │
  │──────────────────────────────>│
  │                               │
  │  200 OK                       │
  │  {"stok":"<32-hex>","error_code":0}
  │<──────────────────────────────│
  │                               │
  │  POST /stok=<token>/ds        │
  │  X-Requested-With: XMLHttpRequest
  │  {"method":"get",...}         │
  │──────────────────────────────>│
  │                               │
  │  200 OK (JSON)                │
  │<──────────────────────────────│
  │                               │
  │  POST /stok=<token>/ds        │
  │  {"method":"do","system":     │
  │   {"logout":null}}            │
  │──────────────────────────────>│
  │                               │
```

### 6.3 密码加密源码 (su.js 原始代码)

```javascript
// su.js 中的关键代码
$.su.orgAuthPwd = function(a) {
    return this.securityEncode(a,
        "RDpbLfCPsJZ7fiv",
        "yLwVl0zKqws7LgKPRQ84Mdt708T1qQ3Ha7xv3H7NyU84p21BriUWBU43odz3iP4rBL3cD02KZciXTysVXiV8ngg6vL48rPJyAUw0HurW20xqxv9aYb4M9wK1Ae0wlro510qXeU07kV57fQMc8L6aLgMLwygtc0F10a0Dg70TOoouyFhdysuRMO51yY5ZlOZZLEal1h0t9YQW0Ko7oBwmCAHoic4HYbUyVeU3sfQ1xtXcPcf1aT303wAQhv66qzW")
};

$.su.securityEncode = function(a, c, d) {
    var h = "", k, g, m, f, l = 187, t = 187;
    g = a.length;       // password length
    m = c.length;       // key1 length (15)
    f = d.length;       // key2 length (223)
    k = g > m ? g : m;  // max of password and key1
    for (var e = 0; e < k; e++) {
        t = l = 187;
        if (e >= g)       t = c.charCodeAt(e);
        else if (e >= m)  l = a.charCodeAt(e);
        else { l = a.charCodeAt(e); t = c.charCodeAt(e); }
        h += d.charAt((l ^ t) % f);
    }
    return h;
};
```

---

## 7. 变更记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-06-07 | v1.0 | 初始版本，API 逆向分析完成，接口验证通过 |
