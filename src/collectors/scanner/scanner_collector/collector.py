"""
ScannerCollector — 资产发现与攻击面扫描采集器（数据面）

设计依据：docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md §6.1
Phase 1 仅实现 _collect_ports()（公网暴露面），Phase 2 加 _collect_discovery()（内网发现）。

架构说明（final.md §2）：
  - 控制面/数据面分离：任务管理/调度/编排全部在 AI-miniSOC
  - 扫描器仅执行轻量循环：心跳 + 拉任务 + 跑 nmap + 推结果 + 回写状态
  - Phase 1 暂用本地 target 列表（环境变量 SCAN_PUBLIC_TARGETS），不接入控制面
    （控制面 in Phase 2 v1.2 ADR-7 落地）
"""

import logging
import os
from typing import Optional

from collector_framework.base import BaseCollector, CollectResult, DataType
try:
    from .nmap_runner import NmapRunner, NmapResult   # 包内正常路径
except ImportError:  # 兼容直接把 scanner_collector 目录塞 PYTHONPATH 的跑法
    from nmap_runner import NmapRunner, NmapResult


logger = logging.getLogger(__name__)


# ============================================================================
# 目标解析（Phase 1：环境变量 / config.yaml）
# ============================================================================
def _resolve_public_targets() -> list[str]:
    """Phase 1：解析公网扫描目标。

    来源（按优先级）：
      1. 环境变量 SCAN_PUBLIC_TARGETS（逗号分隔 IP/CIDR）
      2. 环境变量 SCAN_CONFIG_FILE 指向的 YAML，键 public_targets

    真正"控制面路由"由 Phase 2 接管，本期最小可用。
    """
    env_targets = os.getenv("SCAN_PUBLIC_TARGETS", "").strip()
    if env_targets:
        targets = [t.strip() for t in env_targets.split(",") if t.strip()]
        if targets:
            return targets

    config_file = os.getenv("SCAN_CONFIG_FILE", "/etc/scanner/config.yaml")
    try:
        import yaml
        with open(config_file) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("public_targets", []) or []
    except FileNotFoundError:
        logger.warning("config file %s not found; use SCAN_PUBLIC_TARGETS env", config_file)
        return []
    except Exception as e:
        logger.error("config load failed: %s", e)
        return []


# ============================================================================
# ScannerCollector
# ============================================================================
class ScannerCollector(BaseCollector):
    """资产发现与攻击面扫描采集器。"""

    source_name = "scanner-port"
    # Phase 1 仅 PORT；Phase 2 DiscoverySyncHandler 落地后加 INTERNAL
    supported_types = [DataType.PORT]

    def __init__(
        self,
        nmap_binary: str = "/usr/bin/nmap",
        nmap_timeout: int = 300,
        max_rate: int = 100,
    ):
        self.nmap = NmapRunner(
            binary=nmap_binary,
            timeout_per_ip=nmap_timeout,
            max_rate=max_rate,
        )
        self._scan_task_uuid: Optional[str] = None   # 心跳/认领时回写（Phase 2）

    async def collect(self, data_type: DataType) -> CollectResult:
        """按 data_type 分派到具体扫描方法。

        Phase 1：仅 DataType.PORT 走 _collect_ports()；
                 其他 data_type 抛 NotImplementedError。
        """
        if data_type == DataType.PORT:
            return await self._collect_ports()
        raise NotImplementedError(
            f"data_type={data_type.value} not implemented in Phase 1"
        )

    async def _collect_ports(self) -> CollectResult:
        """公网暴露面扫描模式（final.md §6.1.1）。

        1. 从 env/config 拉取公网目标 IP 列表
        2. 每个 IP 跑 nmap -sV -Pn --top-ports 1000（生产安全门 final.md §10.1）
        3. 解析 XML，每个 open port 构造 PortSyncHandler item
        4. 返回 CollectResult(items=[...])

        注意：扫描任务 UUID 在 Phase 2 由控制面心跳/认领时回写；
        Phase 1 用本地 uuid（让 PortSyncHandler 能写入 findings/proxy task_uuid）。
        """
        import uuid
        import datetime

        targets = _resolve_public_targets()
        if not targets:
            logger.warning(
                "no public scan targets configured "
                "(set SCAN_PUBLIC_TARGETS or /etc/scanner/config.yaml)"
            )
            return CollectResult(
                source=self.source_name,
                data_type=DataType.PORT,
                items=[],
                metadata={"reason": "no targets"},
            )

        # Phase 1 用本地 uuid；Phase 2 由控制面心跳回写
        if self._scan_task_uuid is None:
            self._scan_task_uuid = str(uuid.uuid4())

        all_items: list[dict] = []
        failed_targets: list[str] = []

        for target_ip in targets:
            try:
                result = await self.nmap.scan_ports(
                    target_ip=target_ip,
                    top_ports=1000,
                    version_intensity=5,
                )
            except (asyncio.TimeoutError, RuntimeError) as e:
                # 兜底：单 IP 失败不影响后续 IP（CLAUDE.md 教训：一条失败不挂整批）
                logger.error(
                    "nmap scan failed for %s: %s", target_ip, e,
                )
                failed_targets.append(target_ip)
                continue

            # 解析结果 → PortSyncHandler items
            for host in result.hosts:
                for port in host.ports:
                    if port.state != "open":
                        continue   # 只推 open 端口（closed/filtered 入扫描噪音）
                    all_items.append({
                        "asset_ip": host.ip,
                        "port": port.port,
                        "protocol": port.protocol,
                        "state": port.state,
                        "service": port.service or "",
                        "version": port.version or "",
                        "service_banner": port.banner or "",
                        "scan_time": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                    })

        return CollectResult(
            source=self.source_name,
            data_type=DataType.PORT,
            items=all_items,
            metadata={
                "scan_task_uuid": self._scan_task_uuid,
                "scanned_targets": len(targets),
                "failed_targets": failed_targets,
                "items_count": len(all_items),
            },
        )

    async def collect_for_task(self, task: dict) -> CollectResult:
        """按控制面任务跑扫描（拉模型，Phase 2）。

        - mode=internal：nmap -sn 主机发现 → DataType.DISCOVERY items
        - mode=public/ports：nmap -sV 端口扫描 → DataType.PORT items
        目标从 task.target_summary 取（[{type,value}]），不再依赖环境变量。
        nmap_args 由任务显式下发时追加（信任控制面，不接受扫描器侧任意拼接）。
        """
        import datetime

        mode = (task.get("mode") or "public").lower()
        summary = task.get("target_summary") or []
        targets = [t["value"] for t in summary if isinstance(t, dict) and t.get("value")]
        task_uuid = task.get("task_uuid")
        self._scan_task_uuid = task_uuid

        if not targets:
            logger.warning("task %s 无目标，跳过", str(task_uuid)[:8])
            return CollectResult(
                source=self.source_name,
                data_type=DataType.PORT,
                items=[],
                metadata={"scan_task_uuid": task_uuid, "reason": "no targets"},
            )

        if mode == "internal":
            return await self._collect_discovery(targets, task_uuid)
        # P4-B-α：public 和 ports 都加 vulners CVE 映射（用户确认双模式）
        return await self._collect_ports_for_targets(
            targets, task_uuid, with_vulners=True,
        )

    async def _collect_discovery(self, targets: list[str], task_uuid) -> CollectResult:
        """内网主机发现：一次 nmap -sn 跑所有 target，存活主机产 DISCOVERY items。

        P4-A 优化：合并多目标为单次 nmap 调用，nmap 自己负责探测所有 IP。
        单次 nmap 异常 → 整批 failed；否则按 XML 只产 up 主机的 item。
        """
        import datetime
        all_items: list[dict] = []
        failed: list[str] = []
        if not targets:
            return CollectResult(
                source=self.source_name,
                data_type=DataType.DISCOVERY,
                items=[],
                metadata={"scan_task_uuid": task_uuid, "scanned_targets": 0, "failed_targets": [], "items_count": 0},
            )
        try:
            # 单次 nmap 跑所有 target
            result = await self.nmap.scan_discovery_multi(
                targets=targets,
                timeout=self._dynamic_timeout(targets, base=300, per_target=5),
            )
        except (asyncio.TimeoutError, RuntimeError) as e:
            logger.error("nmap discovery failed for batch [%s]: %s",
                         ",".join(targets)[:120], e)
            failed = list(targets)
            return CollectResult(
                source=self.source_name,
                data_type=DataType.DISCOVERY,
                items=[],
                metadata={
                    "scan_task_uuid": task_uuid,
                    "scanned_targets": len(targets),
                    "failed_targets": failed,
                    "items_count": 0,
                    "error": str(e),
                },
            )

        # 记录哪些 target 在 nmap 结果里出现过，未出现的视为超时/无响应
        seen_ips: set[str] = set()
        for host in result.hosts:
            if host.status != "up" or not host.ip:
                continue
            seen_ips.add(host.ip)
            all_items.append({
                "scan_task_uuid": task_uuid,
                "asset_ip": host.ip,
                "mac_address": host.mac_address,
                "os_guess": host.os_guess,
                "exposure": "internal",
                "discovery_source": "scanner",
                "open_ports": [],
                "raw_data": {
                    "nmap_status": host.status,
                    "target_batch": targets[:5],  # 存前 5 个作溯源
                },
                "scan_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
        # targets 中单 IP/CIDR（纯 IP）未出现在结果 → 可能是被 ping 探测的"无响应主机"，不算失败
        # CIDR 类目标不计入"failed"（CIDR 里 254 个 IP 只有部分是 up）
        failed = [
            t for t in targets
            if "/" not in t and not any(h.ip == t for h in result.hosts)
        ]

        return CollectResult(
            source=self.source_name,
            data_type=DataType.DISCOVERY,
            items=all_items,
            metadata={
                "scan_task_uuid": task_uuid,
                "scanned_targets": len(targets),
                "failed_targets": failed,
                "items_count": len(all_items),
                "seen_ips": len(seen_ips),
            },
        )

    async def _collect_ports_for_targets(
        self, targets: list[str], task_uuid, with_vulners: bool = False,
    ) -> CollectResult:
        """端口扫描：一次 nmap -sV 跑所有 target，开放端口产 PORT items。

        P4-A：合并多目标为单次 nmap 调用，共享主机发现/路由缓存。
        P4-B-α：with_vulners=True 时附加 --script=vulners，每个 open port 带 cves 列表。
        """
        import datetime
        all_items: list[dict] = []
        failed: list[str] = []
        if not targets:
            return CollectResult(
                source=self.source_name,
                data_type=DataType.PORT,
                items=[],
                metadata={"scan_task_uuid": task_uuid, "scanned_targets": 0, "failed_targets": [], "items_count": 0},
            )
        try:
            if with_vulners:
                result = await self.nmap.scan_ports_with_vulners_multi(
                    targets=targets,
                    top_ports=1000,
                    version_intensity=5,
                    # vulners 多 ~30s/IP + NSE 库下载 + 网络抖动
                    timeout=self._dynamic_timeout(targets, base=300, per_target=30),
                )
            else:
                result = await self.nmap.scan_ports_multi(
                    targets=targets,
                    top_ports=1000,
                    version_intensity=5,
                    timeout=self._dynamic_timeout(targets, base=300, per_target=10),
                )
        except (asyncio.TimeoutError, RuntimeError) as e:
            logger.error("nmap port scan failed for batch [%s]: %s",
                         ",".join(targets)[:120], e)
            failed = list(targets)
            return CollectResult(
                source=self.source_name,
                data_type=DataType.PORT,
                items=[],
                metadata={
                    "scan_task_uuid": task_uuid,
                    "scanned_targets": len(targets),
                    "failed_targets": failed,
                    "items_count": 0,
                    "error": str(e),
                },
            )

        for host in result.hosts:
            for port in host.ports:
                if port.state != "open":
                    continue
                all_items.append({
                    "scan_task_uuid": task_uuid,
                    "asset_ip": host.ip,
                    "port": port.port,
                    "protocol": port.protocol,
                    "state": port.state,
                    "service": port.service or "",
                    "version": port.version or "",
                    "service_banner": port.banner or "",
                    "cves": list(port.cves or []),   # P4-B-α：vulners 输出的 CVE 列表
                    "scan_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                })

        # targets 中纯 IP 未出现在结果 → 主机不可达/超时
        failed = [
            t for t in targets
            if "/" not in t and not any(h.ip == t for h in result.hosts)
        ]

        return CollectResult(
            source=self.source_name,
            data_type=DataType.PORT,
            items=all_items,
            metadata={
                "scan_task_uuid": task_uuid,
                "scanned_targets": len(targets),
                "failed_targets": failed,
                "items_count": len(all_items),
            },
        )

    @staticmethod
    def _dynamic_timeout(targets: list[str], base: int = 300, per_target: int = 5) -> int:
        """动态计算 nmap 超时 = max(base, N * per_target)，避免大批量被截断。"""
        n = len(targets)
        return max(base, n * per_target)

    async def test_connection(self) -> bool:
        """检查 nmap 是否可用 + 目标是否配置。"""
        nmap_ok = await self.nmap.is_available()
        if not nmap_ok:
            return False
        targets = _resolve_public_targets()
        return bool(targets)


# 导入 asyncio（避免在文件顶部加：nmap_runner 内已用）
import asyncio  # noqa: E402