"""
nmap_runner — subprocess 封装（超时 + 资源限制 + XML 解析）

设计依据：docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md §6.1
Phase 1 仅扫描公网暴露面（端口 + 服务版本），不实施主动发现。
Phase 2 才会加 _collect_discovery() + CIDR 扫描。

CLAUDE.md 教训（P3 §采集器踩坑）：
- httpx 0.28.1 / anyio / asyncio 版本与 Python 3.12/3.13 差异：subprocess 必须 + asyncio.create_subprocess_exec
- 解析 nmap XML 必须 ``-oX -``（stdout）而非默认文本输出
- 不要 await subprocess.communicate() 后忘记 cancel 超时
"""

import asyncio
import logging
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================================
# 数据类：与 nmap XML 一一对应
# ============================================================================
@dataclass
class NmapHost:
    """nmap <host> 元素反序列化"""
    ip: str
    status: str              # "up" / "down"
    mac_address: Optional[str] = None
    os_guess: Optional[str] = None
    ports: list["NmapPort"] = None  # type: ignore

    def __post_init__(self):
        if self.ports is None:
            self.ports = []


@dataclass
class NmapPort:
    """nmap <port> 元素反序列化"""
    port: int
    protocol: str            # "tcp" / "udp"
    state: str               # "open" / "closed" / "filtered"
    service: Optional[str] = None
    version: Optional[str] = None
    banner: Optional[str] = None
    cves: list[str] = None  # type: ignore  # P4-B-α: vulners 脚本输出的 CVE 列表

    def __post_init__(self):
        if self.cves is None:
            self.cves = []

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NmapResult:
    """nmap 扫描完整结果"""
    hosts: list[NmapHost]
    raw_xml: str
    duration_ms: int


# ============================================================================
# NmapRunner
# ============================================================================
class NmapRunner:
    """nmap 子进程封装。

    关键约束（生产安全门，final.md §10.1）：
      - 单 IP 扫描超时 300s（防 nmap 卡死）
      - --max-rate 100 pps（防生产网拥塞）
      - 并发 1（单容器内顺序扫，避免带宽打满）
    """

    def __init__(
        self,
        binary: str = "/usr/bin/nmap",
        timeout_per_ip: int = 300,
        max_rate: int = 100,
    ):
        self.binary = binary
        self.timeout_per_ip = timeout_per_ip
        self.max_rate = max_rate

    async def is_available(self) -> bool:
        """检查 nmap 二进制是否可用 + 版本。"""
        binary_path = shutil.which(self.binary) or self.binary
        try:
            proc = await asyncio.create_subprocess_exec(
                binary_path, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode == 0 and b"Nmap" in stdout
        except (FileNotFoundError, asyncio.TimeoutError, OSError) as e:
            logger.warning("nmap availability check failed: %s", e)
            return False

    async def run(self, args: list[str]) -> str:
        """执行 nmap，返回 stdout XML（-oX - 强制 XML 输出）。

        Args:
            args: nmap 参数列表（不含 binary 路径，不含 -oX -）

        Returns:
            stdout 的 XML 字符串

        Raises:
            asyncio.TimeoutError: 单次扫描超时
            RuntimeError: nmap 退出码非零
        """
        binary_path = shutil.which(self.binary) or self.binary
        # 强制 XML 输出到 stdout
        cmd = [binary_path] + args + ["-oX", "-"]

        logger.info("nmap exec: %s (timeout=%ds)", " ".join(cmd), self.timeout_per_ip)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_per_ip,
            )
        except asyncio.TimeoutError:
            logger.error("nmap timeout after %ds, killing pid=%d", self.timeout_per_ip, proc.pid)
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            raise

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"nmap failed (rc={proc.returncode}): {err}")

        return stdout.decode("utf-8", errors="replace")

    async def scan_ports(
        self,
        target_ip: str,
        top_ports: int = 1000,
        version_intensity: int = 5,
    ) -> NmapResult:
        """公网暴露面扫描：单 IP 的 top-ports + 服务版本探测。

        final.md §6.1.1 _collect_ports() 单 IP 实现。
        """
        args = [
            "-sV",                            # 服务版本探测
            "-Pn",                            # 跳过 ping（公网 IP 通常禁 ping）
            "--top-ports", str(top_ports),
            "--version-intensity", str(version_intensity),
            "--max-rate", str(self.max_rate),
            "-n",                             # 不反查 DNS
            target_ip,
        ]
        import time
        t0 = time.monotonic()
        xml = await self.run(args)
        duration_ms = int((time.monotonic() - t0) * 1000)

        hosts = parse_nmap_xml(xml)
        return NmapResult(hosts=hosts, raw_xml=xml, duration_ms=duration_ms)

    async def scan_discovery(self, target: str) -> NmapResult:
        """内网主机发现：nmap -sn（ping/ARP 发现，不扫端口）。

        target 可以是单 IP 或 CIDR（如 192.168.0.0/24）。
        返回的 NmapHost 只带 status/ip/mac/os_guess，ports 为空。
        final.md §6.1.2 _collect_discovery()。
        """
        args = [
            "-sn",                          # ping 发现，不扫端口
            "--max-rate", str(self.max_rate),
            "-n",
            target,
        ]
        import time
        t0 = time.monotonic()
        xml = await self.run(args)
        duration_ms = int((time.monotonic() - t0) * 1000)

        hosts = parse_nmap_xml(xml)
        return NmapResult(hosts=hosts, raw_xml=xml, duration_ms=duration_ms)

    async def scan_discovery_multi(self, targets: list[str], timeout: int = 300) -> NmapResult:
        """P4-A：一次 nmap -sn 扫多个目标（IP / CIDR 混合）。

        nmap 原生支持多目标并行：nmap -sn ip1 ip2 /24 ...
        比起逐个调用 scan_discovery() 快 5-10x（共享路由/探测缓存）。
        """
        args = [
            "-sn",
            "--max-rate", str(self.max_rate),
            "-n",
            *targets,
        ]
        import time
        # 临时覆盖单次 timeout（run() 用 self.timeout_per_ip，这里复用但传 batch timeout）
        old_timeout = self.timeout_per_ip
        self.timeout_per_ip = timeout
        try:
            t0 = time.monotonic()
            xml = await self.run(args)
            duration_ms = int((time.monotonic() - t0) * 1000)
        finally:
            self.timeout_per_ip = old_timeout
        hosts = parse_nmap_xml(xml)
        return NmapResult(hosts=hosts, raw_xml=xml, duration_ms=duration_ms)

    async def scan_ports_multi(
        self,
        targets: list[str],
        top_ports: int = 1000,
        version_intensity: int = 5,
        timeout: int = 300,
    ) -> NmapResult:
        """P4-A：一次 nmap -sV 扫多个目标，开放端口 + 服务版本。

        兼容 IP / CIDR 混合：nmap -sV ip1 ip2 /24 ...
        """
        args = [
            "-sV",
            "-Pn",                            # 多目标模式跳过 ping（防 batch 被 ping 干扰）
            "--top-ports", str(top_ports),
            "--version-intensity", str(version_intensity),
            "--max-rate", str(self.max_rate),
            "-n",
            *targets,
        ]
        import time
        old_timeout = self.timeout_per_ip
        self.timeout_per_ip = timeout
        try:
            t0 = time.monotonic()
            xml = await self.run(args)
            duration_ms = int((time.monotonic() - t0) * 1000)
        finally:
            self.timeout_per_ip = old_timeout
        hosts = parse_nmap_xml(xml)
        return NmapResult(hosts=hosts, raw_xml=xml, duration_ms=duration_ms)

    async def scan_ports_with_vulners_multi(
        self,
        targets: list[str],
        top_ports: int = 1000,
        version_intensity: int = 5,
        timeout: int = 600,
    ) -> NmapResult:
        """P4-B-α：nmap -sV + --script=vulners 扫多目标，每个 open port 产 CVE 列表。

        vulners 脚本：根据 service version 字段查 vulners.com 漏洞库，返回匹配的 CVE。
        实测 192.168.0.30 (top 100 + vulners) ~30 秒；top 1000 + vulners ~60-90 秒。
        超时建议 600s（NSE 库下载 + 网络抖动留 buffer）。
        """
        args = [
            "-sV",
            "-Pn",
            "--top-ports", str(top_ports),
            "--version-intensity", str(version_intensity),
            "--max-rate", str(self.max_rate),
            "--script=vulners",                # 关键：CVE 数据库映射
            "-n",
            *targets,
        ]
        import time
        old_timeout = self.timeout_per_ip
        self.timeout_per_ip = timeout
        try:
            t0 = time.monotonic()
            xml = await self.run(args)
            duration_ms = int((time.monotonic() - t0) * 1000)
        finally:
            self.timeout_per_ip = old_timeout
        hosts = parse_nmap_xml(xml)
        return NmapResult(hosts=hosts, raw_xml=xml, duration_ms=duration_ms)
# ============================================================================
def parse_nmap_xml(xml_str: str) -> list[NmapHost]:
    """nmap XML → List[NmapHost]。

    处理以下边界：
      - 多个 <host> 元素（单次扫多 IP；Phase 2 内部扫描用）
      - <os> 缺失（只关心 best os match 的 name 属性）
      - <address addrtype="mac">">> 缺失（mac 字段 None）
      - <port state="filtered">> 仍返回，但调用方应过滤
    """
    root = ET.fromstring(xml_str)
    hosts: list[NmapHost] = []

    for host_el in root.findall("host"):
        # 状态
        status_el = host_el.find("status")
        status = status_el.get("state", "unknown") if status_el is not None else "unknown"

        # 地址
        ip = ""
        mac = None
        for addr_el in host_el.findall("address"):
            addr_type = addr_el.get("addrtype", "")
            addr_value = addr_el.get("addr", "")
            if addr_type == "ipv4" and not ip:
                ip = addr_value
            elif addr_type == "mac":
                mac = addr_value

        # OS guess
        os_guess = None
        os_el = host_el.find("os")
        if os_el is not None:
            osmatch_el = os_el.find("osmatch")
            if osmatch_el is not None:
                os_guess = osmatch_el.get("name")

        # 端口
        ports: list[NmapPort] = []
        ports_el = host_el.find("ports")
        if ports_el is not None:
            for port_el in ports_el.findall("port"):
                port_num = int(port_el.get("portid", "0"))
                protocol = port_el.get("protocol", "tcp")

                state_el = port_el.find("state")
                state = state_el.get("state", "open") if state_el is not None else "open"

                service_el = port_el.find("service")
                service_name = None
                version = None
                banner = None
                if service_el is not None:
                    service_name = service_el.get("name")
                    product = service_el.get("product", "")
                    ver = service_el.get("version", "")
                    extra = service_el.get("extrainfo", "")
                    version_parts = [p for p in [product, ver, extra] if p]
                    version = " ".join(version_parts) if version_parts else None

                    # banner 拼装（部分 nmap 版本用 service banner；不在 XML 里）
                    # 实测 nmap -sV 不会把 banner 写进 XML，需独立 nmap -sV --script=banner
                    # Phase 1 不实现 banner（避免 -sV 复杂度上升）

                # P4-B-α：解析 vulners 脚本输出
                # nmap --script=vulners 输出结构：
                #   <port><script id="vulners" output="...">
                #     <table key="id"><elem key="id">CVE-XXXX-XXXXX</elem>
                #     <table><elem key="cvss">N.N</elem><elem key="type">cve</elem><elem key="id">CVE-XXXX-XXXXX</elem></table>
                #     ...多个 <table> 每个一个 CVE
                cves: list[str] = []
                scripts_el = port_el.find("script")
                if scripts_el is not None and scripts_el.get("id") == "vulners":
                    for tbl in scripts_el.findall("table"):
                        for inner in tbl.findall("table"):
                            cve_id_el = inner.find("elem[@key='id']")
                            if cve_id_el is not None and cve_id_el.text:
                                cid = cve_id_el.text.strip()
                                if cid.startswith("CVE-"):
                                    cves.append(cid)

                ports.append(NmapPort(
                    port=port_num,
                    protocol=protocol,
                    state=state,
                    service=service_name,
                    version=version,
                    banner=banner,
                    cves=cves,
                ))

        hosts.append(NmapHost(
            ip=ip,
            status=status,
            mac_address=mac,
            os_guess=os_guess,
            ports=ports,
        ))

    return hosts