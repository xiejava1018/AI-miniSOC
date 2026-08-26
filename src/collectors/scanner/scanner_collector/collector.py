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

    async def test_connection(self) -> bool:
        """检查 nmap 是否可用 + 目标是否配置。"""
        nmap_ok = await self.nmap.is_available()
        if not nmap_ok:
            return False
        targets = _resolve_public_targets()
        return bool(targets)


# 导入 asyncio（避免在文件顶部加：nmap_runner 内已用）
import asyncio  # noqa: E402