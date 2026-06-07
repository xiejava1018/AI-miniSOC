"""
TP-Link SLP 路由器 API 客户端

适用于 TL-R479GP-AC 等使用 SLP (Single Page Application) 管理界面的 TP-Link 路由器。

认证流程:
  1. 密码经 XOR 字符映射混淆 (securityEncode) 加密
  2. POST / 发送登录请求，获取 stok (会话令牌)
  3. 后续请求使用 /stok=<token>/ds 端点
  4. 必须携带 X-Requested-With: XMLHttpRequest 请求头
"""

import logging
from typing import Optional
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """认证失败"""
    pass


class APIError(Exception):
    """API 调用失败"""
    pass


class TPLinkSLPClient:
    """TP-Link SLP 路由器 API 客户端"""

    XOR_KEY1 = "RDpbLfCPsJZ7fiv"
    XOR_KEY2 = (
        "yLwVl0zKqws7LgKPRQ84Mdt708T1qQ3Ha7xv3H7NyU84p21BriUWBU43odz3iP4r"
        "BL3cD02KZciXTysVXiV8ngg6vL48rPJyAUw0HurW20xqxv9aYb4M9wK1Ae0wlro5"
        "10qXeU07kV57fQMc8L6aLgMLwygtc0F10a0Dg70TOoouyFhdysuRMO51yY5ZlOZZL"
        "Eal1h0t9YQW0Ko7oBwmCAHoic4HYbUyVeU3sfQ1xtXcPcf1aT303wAQhv66qzW"
    )

    API_HEADERS = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }

    def __init__(self, host: str, username: str, password: str, port: int = 80):
        self.base_url = f"http://{host}:{port}"
        self.username = username
        self.password = password
        self.client = httpx.AsyncClient(timeout=30, verify=False)
        self.stok: Optional[str] = None

    @classmethod
    def security_encode(cls, password: str) -> str:
        """
        TP-Link SLP 密码 XOR 混淆加密

        对 password 和 key1 逐字符 XOR，结果对 key2 长度取模映射到 key2 字符。
        超出长度部分用 187 做 XOR 基准值。
        """
        result = ""
        k1, k2 = cls.XOR_KEY1, cls.XOR_KEY2
        pwd_len, k1_len, k2_len = len(password), len(k1), len(k2)
        length = max(pwd_len, k1_len)
        for i in range(length):
            char_pwd = char_key = 187
            if i >= pwd_len:
                char_key = ord(k1[i])
            elif i >= k1_len:
                char_pwd = ord(password[i])
            else:
                char_pwd = ord(password[i])
                char_key = ord(k1[i])
            result += k2[(char_pwd ^ char_key) % k2_len]
        return result

    async def login(self) -> str:
        """登录路由器，获取 stok token"""
        enc_pwd = self.security_encode(self.password)
        resp = await self.client.post(
            f"{self.base_url}/",
            json={
                "method": "do",
                "login": {
                    "username": self.username,
                    "password": enc_pwd,
                },
            },
        )

        if resp.status_code == 401:
            data = resp.json()
            raise AuthenticationError(
                f"登录失败: code={data.get('error_code')}, "
                f"剩余尝试={data.get('data', {}).get('time', '?')}"
            )

        resp.raise_for_status()
        data = resp.json()

        if data.get("error_code") != 0:
            raise AuthenticationError(f"登录失败: {data}")

        self.stok = data["stok"]
        logger.info(f"登录成功，stok: {self.stok[:8]}...")
        return self.stok

    async def get_hosts(self) -> list[dict]:
        """获取在线终端设备列表（标准化后的格式）"""
        if not self.stok:
            await self.login()

        url = f"{self.base_url}/stok={self.stok}/ds"
        resp = await self.client.post(
            url,
            json={"method": "get", "host_management": {"table": "host_info"}},
            headers=self.API_HEADERS,
        )

        if resp.status_code == 401:
            self.stok = None
            return await self.get_hosts()

        resp.raise_for_status()
        data = resp.json()

        if data.get("error_code") != 0:
            raise APIError(f"获取设备列表失败: {data}")

        hosts = []
        for item in data["host_management"]["host_info"]:
            for key, host_data in item.items():
                hosts.append(self._normalize_host(host_data))

        logger.info(f"获取到 {len(hosts)} 台在线设备")
        return hosts

    async def logout(self):
        """退出登录，释放 stok"""
        if self.stok:
            try:
                url = f"{self.base_url}/stok={self.stok}/ds"
                await self.client.post(
                    url,
                    json={"method": "do", "system": {"logout": None}},
                    headers=self.API_HEADERS,
                )
            except Exception as e:
                logger.debug(f"注销时出错（可忽略）: {e}")
            finally:
                self.stok = None

    def _normalize_host(self, raw: dict) -> dict:
        """将路由器原始数据转换为 AI-miniSOC 标准格式"""
        mac = raw.get("mac", "")
        hostname = raw.get("hostname", "")
        conn_type = raw.get("type", "")
        state = raw.get("state", "")

        # 构建描述信息
        desc_parts = []
        if conn_type == "wireless":
            desc_parts.append("无线设备")
            if raw.get("ssid"):
                desc_parts.append(f"SSID: {raw['ssid']}")
            if raw.get("freq_name"):
                desc_parts.append(raw["freq_name"])
            if raw.get("rssi"):
                desc_parts.append(f"RSSI: {raw['rssi']}dBm")
            if raw.get("ap_name"):
                desc_parts.append(f"AP: {raw['ap_name']}")
        elif conn_type == "wired":
            desc_parts.append("有线设备")

        down_speed = int(raw.get("down_speed", "0"))
        up_speed = int(raw.get("up_speed", "0"))
        if down_speed or up_speed:
            desc_parts.append(f"↑{up_speed}Kbps ↓{down_speed}Kbps")

        connect_date = unquote(raw.get("connect_date", ""))
        connect_time = unquote(raw.get("connect_time", ""))
        if connect_date and connect_time:
            desc_parts.append(f"接入: {connect_date} {connect_time}")

        return {
            "name": hostname if hostname != "anonymous" else None,
            "asset_ip": raw.get("ip"),
            "mac_address": mac.replace("-", ":") if mac else None,
            "asset_type": "server" if conn_type == "wired" else "client",
            "asset_status": state,
            "network_zone": "intranet",
            "network_segment": "default",
            "criticality": "normal",
            "data_source": "tplink-router",
            "asset_description": " | ".join(desc_parts) if desc_parts else None,
        }

    async def close(self):
        await self.client.aclose()
