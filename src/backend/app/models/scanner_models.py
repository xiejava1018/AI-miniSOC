"""
资产发现与攻击面扫描采集器 — 数据模型（P3/F-S1、F-S2、F-S3，PRD 2026-08-26 final）

本文件集中 4 张与「扫描控制面」相关的表，与 `soc_asset_ports`（扫描产出落库的目标表）
独立。设计依据见 `docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md`。

表清单（与 final.md §6.3 一致）：
- ScannerTask          → soc_scanner_tasks      扫描任务记录
- ScanTarget           → soc_scan_targets       扫描目标清单（管理员配置）
- ScanFinding          → soc_scan_findings      扫描发现结果（与台账解耦）
- ScannerAgent         → soc_scanner_agents     扫描器注册/状态/心跳

注意：表名故意用 `soc_scanner_*`（除 ScanTarget/ScanFinding 沿用 PRD 写法），因为
`vulnerability.py` 已经占用 `ScanTask` 类名（`models/__init__.py:51` import），沿用
会与漏洞扫描任务冲突——这是 final.md §5.5「硬伤2 修复」的原因。
"""

from sqlalchemy import (
    BigInteger, Column, String, Text, DateTime, Integer, ForeignKey, Boolean,
    UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import text, func
from app.models.base import Base


# ============================================================================
# ScannerTask — 扫描任务记录（final.md §6.3 第一个表）
# ============================================================================
class ScannerTask(Base):
    """扫描任务表（控制面建任务 → 扫描器拉取认领 → 回写状态）"""
    __tablename__ = "soc_scanner_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_uuid = Column(UUID(as_uuid=True), nullable=False, unique=True,
                       server_default=func.gen_random_uuid())
    mode = Column(String(20), nullable=False)              # 'internal' / 'public' / 'ports'
    scope = Column(String(20), nullable=False)             # 'manual' / 'scheduled' / 'auto'
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
                                                           # 'pending'/'running'/'success'/'failed'/'cancelled'
    triggered_by = Column(String(50))                       # 用户名 / 'scheduler' / 'scanner-collector'
    target_summary = Column(JSONB)                         # [{"type":"cidr","value":"..."}]

    # v1.2 增量：路由 + 认领 + 溯源
    parent_task_id = Column(UUID(as_uuid=True))            # v1.3 F-3 重派溯源
    target_scanner_id = Column(String(36))                 # 指定执行扫描器（pinned）
    scanner_id = Column(String(36))                        # 实际执行者（认领后回写）
    assign_mode = Column(String(12), nullable=False, default="auto", server_default="auto")
                                                           # 'auto'/'pinned'
    claimed_at = Column(DateTime(timezone=True))
    capabilities = Column(JSONB)                           # 任务所需能力快照，用于路由
    run_reason = Column(String(32), default="manual", server_default="manual")
                                                           # 'manual'/'scheduled'/'auto-shadow'

    # 时间与统计
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    items_scanned = Column(Integer, default=0, server_default="0")
    items_created = Column(Integer, default=0, server_default="0")
    items_updated = Column(Integer, default=0, server_default="0")
    items_failed = Column(Integer, default=0, server_default="0")
    error_message = Column(Text)
    nmap_args = Column(Text)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_scanner_tasks_status', 'status'),
        Index('idx_scanner_tasks_assign', 'assign_mode', 'status'),
        Index('idx_scanner_tasks_started', text('started_at DESC')),
    )

    def __repr__(self):
        return f"<ScannerTask(uuid={self.task_uuid}, mode={self.mode}, status={self.status})>"


# ============================================================================
# ScanTarget — 扫描目标清单（final.md §6.3 第二个表）
# ============================================================================
class ScanTarget(Base):
    """扫描目标表（管理员配置的内网 CIDR / 公网 IP）"""
    __tablename__ = "soc_scan_targets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    target_uuid = Column(UUID(as_uuid=True), nullable=False, unique=True,
                         server_default=func.gen_random_uuid())
    scope = Column(String(20), nullable=False)            # 'internal'（CIDR）/'public'（IP/域名）
    value = Column(String(100), nullable=False)
    description = Column(String(255))
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    exclude_ips = Column(JSONB)                           # 排除列表
    added_by = Column(String(50))
    last_scan_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_scan_targets_enabled', 'enabled',
              postgresql_where=text('enabled = TRUE')),
        UniqueConstraint('scope', 'value', name='uq_scan_targets_scope_value'),
    )

    def __repr__(self):
        return f"<ScanTarget(scope={self.scope}, value={self.value}, enabled={self.enabled})>"


# ============================================================================
# ScanFinding — 扫描发现结果（final.md §6.3 第三个表，与台账解耦）
# ============================================================================
class ScanFinding(Base):
    """扫描发现表（核心修复：scanner 不直接写 soc_assets，全部落这里待纳管）"""
    __tablename__ = "soc_scan_findings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scan_task_uuid = Column(UUID(as_uuid=True), nullable=False)  # 关联 soc_scanner_tasks.task_uuid（软关联，跨表不强制 FK）
    asset_ip = Column(String(64), nullable=False)
    mac_address = Column(String(32))
    os_guess = Column(String(128))
    exposure = Column(String(16), nullable=False, default="internal", server_default="internal")
                                                          # 'internal'/'public'
    discovery_source = Column(String(32), nullable=False, default="scanner", server_default="scanner")
    scanner_id = Column(String(36))                       # v1.2：来源扫描器，便于溯源
    matched_asset_id = Column(UUID(as_uuid=True))          # 反查 soc_assets.id（与 Asset.id 一致，UUID；非空时 F1.3 跳过）
    finding_status = Column(String(16), nullable=False, default="new", server_default="new")
                                                          # 'new'/'known'/'adopted'/'ignored'
    first_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    raw_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_scan_findings_ip', 'asset_ip'),
        Index('idx_scan_findings_status', 'finding_status'),
        Index('idx_scan_findings_task', 'scan_task_uuid'),
        Index('idx_scan_findings_scanner', 'scanner_id'),
        UniqueConstraint('scan_task_uuid', 'asset_ip', name='uq_scan_findings_task_ip'),
    )

    def __repr__(self):
        return f"<ScanFinding(task={self.scan_task_uuid}, ip={self.asset_ip}, status={self.finding_status})>"


# ============================================================================
# ScannerAgent — 扫描器注册/状态/心跳（final.md §6.3 第四个表）
# ============================================================================
class ScannerAgent(Base):
    """扫描器注册/状态表（心跳 + 能力声明 + 子网可达性）"""
    __tablename__ = "soc_scanner_agents"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scanner_id = Column(String(36), nullable=False, unique=True)   # UUID，注册时分配
    name = Column(String(100), nullable=False)
    ip = Column(String(64))                                          # 注册时填，心跳可更新
    capabilities = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
                                                                    # ['internal','public','ports']
    reachable_subnets = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
                                                                    # ['192.168.0.0/24']
    status = Column(String(20), nullable=False, default="unknown", server_default="unknown")
                                                                    # 'online'/'offline'/'disabled'/'unknown'
    version = Column(String(32))
    running_tasks = Column(Integer, nullable=False, default=0, server_default="0")
    last_heartbeat = Column(DateTime(timezone=True))
    api_key_hash = Column(String(255))                              # API Key 哈希（不存明文）
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(String(50))                                  # v1.3 M-3：注册操作人，审计溯源
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_scanner_agents_status', 'status'),
        Index('idx_scanner_agents_enabled', 'enabled',
              postgresql_where=text('enabled = TRUE')),
    )

    def __repr__(self):
        return f"<ScannerAgent(id={self.scanner_id}, name={self.name}, status={self.status})>"


__all__ = [
    "ScannerTask",
    "ScanTarget",
    "ScanFinding",
    "ScannerAgent",
]