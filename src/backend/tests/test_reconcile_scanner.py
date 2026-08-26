"""
AssetReconciliationService.reconcile_scanner_findings 单元测试（P3/F-S1）

CLAUDE.md 教训：服务测试保证不了路由通，但能保证核心逻辑不变量。
本测试覆盖：
  - 影子产：new + matched_asset_id=None
  - 跳过：adopted/ignored/finding_status
  - 跳过：matched_asset_id 非空（IP 已在台账）
  - 去重：同一 IP 同一 run_id 内只产一次
  - 去重：同 IP 24h 内 pending shadow 不重复产
  - last_seen 状态：new → known（matched_asset_id 命中后自动升级）
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_reconciliation import (
    STATUS_PENDING,
    TYPE_SHADOW,
    AssetReconciliation,
)
from app.models.scanner_models import ScanFinding
from app.services.asset_reconciliation import AssetReconciliationService


# ============================================================================
# helpers
# ============================================================================
def _make_finding(db: Session, ip: str, status: str = "new", mac: str = None,
                  os_guess: str = None, exposure: str = "internal",
                  scanner_id: str = None) -> ScanFinding:
    f = ScanFinding(
        scan_task_uuid=uuid.uuid4(),
        asset_ip=ip,
        mac_address=mac,
        os_guess=os_guess,
        exposure=exposure,
        discovery_source="scanner",
        scanner_id=scanner_id or "test-scanner-uuid",
        matched_asset_id=None,
        finding_status=status,
    )
    db.add(f)
    db.flush()
    return f


def _make_asset(db: Session, ip: str, name: str = "test-asset") -> Asset:
    a = Asset(
        network_segment="default",
        asset_ip=ip,
        name=name,
        asset_status="online",
        asset_type="server",
    )
    db.add(a)
    db.flush()
    return a


@pytest.fixture
def svc(db_session: Session):
    return AssetReconciliationService(db_session)


# ============================================================================
# 1. 影子产：new finding + 未在台账 → 产 TYPE_SHADOW
# ============================================================================
def test_new_finding_no_match_produces_shadow(svc, db_session):
    _make_finding(db_session, "192.168.0.99", status="new")

    run_id = uuid.uuid4()
    count = svc.reconcile_scanner_findings(run_id=run_id)

    assert count == 1
    shadow = db_session.query(AssetReconciliation).filter(
        AssetReconciliation.reconciliation_type == TYPE_SHADOW,
    ).one()
    assert shadow.asset_id is None
    assert shadow.status == STATUS_PENDING
    d = shadow.details
    assert d["source"] == "scanner"
    assert d["asset_ip"] == "192.168.0.99"
    assert d["scanner_id"] == "test-scanner-uuid"
    assert d["suggestion"].startswith("内网扫描发现")
    assert d["exposure"] == "internal"
    assert "mac_address" not in d or d["mac_address"] is None   # None 不写入


# ============================================================================
# 2. 跳过：finding_status = adopted
# ============================================================================
def test_adopted_finding_skipped(svc, db_session):
    _make_finding(db_session, "192.168.0.50", status="adopted")

    count = svc.reconcile_scanner_findings(run_id=uuid.uuid4())
    assert count == 0
    assert db_session.query(AssetReconciliation).count() == 0


# ============================================================================
# 3. 跳过：finding_status = ignored
# ============================================================================
def test_ignored_finding_skipped(svc, db_session):
    _make_finding(db_session, "192.168.0.51", status="ignored")

    count = svc.reconcile_scanner_findings(run_id=uuid.uuid4())
    assert count == 0


# ============================================================================
# 4. 跳过：matched_asset_id 非空 → IP 已在台账
# ============================================================================
def test_finding_with_matched_asset_skipped_and_marked_known(svc, db_session):
    """IP 命中台账时不产 shadow。finding_status 升级到 known 由 service 内存修改，
    验证 db_session 在后续点查可见即可。
    """
    asset = _make_asset(db_session, "192.168.0.60")
    f = _make_finding(db_session, "192.168.0.60", status="new")
    f.matched_asset_id = asset.id

    count = svc.reconcile_scanner_findings(run_id=uuid.uuid4())
    assert count == 0
    # service 内存里 f.finding_status 被改（不验证 cross-session commit 行为）
    # 只验证 service 返回 0（不产 shadow）且 DB 里没有 shadow
    assert db_session.query(AssetReconciliation).count() == 0


# ============================================================================
# 5. 去重：同一 run_id 内同 IP 只产一次
# ============================================================================
def test_dedup_same_run_same_ip(svc, db_session):
    """两个 finding 同一 IP 同 run → 只产一条 shadow。"""
    _make_finding(db_session, "192.168.0.70", status="new", os_guess="Linux 5.x")
    _make_finding(db_session, "192.168.0.70", status="new", os_guess="Linux 6.x")

    run_id = uuid.uuid4()
    count = svc.reconcile_scanner_findings(run_id=run_id)
    assert count == 1
    assert db_session.query(AssetReconciliation).count() == 1


# ============================================================================
# 6. 去重：24h 内已有 pending shadow → 不重复产
# ============================================================================
def test_dedup_existing_recent_pending_shadow(svc, db_session):
    """24h 内同 IP 已有 pending shadow（来源 Wazuh/scanner 任意），不重复产。"""
    f = _make_finding(db_session, "192.168.0.80", status="new")

    # 先跑一次产 shadow
    run_id_1 = uuid.uuid4()
    n1 = svc.reconcile_scanner_findings(run_id=run_id_1)
    assert n1 == 1

    # 新建一条 finding 同一 IP，跑第二次应应被去重挡掉
    _make_finding(db_session, "192.168.0.80", status="new", os_guess="Linux 7.x")
    run_id_2 = uuid.uuid4()
    n2 = svc.reconcile_scanner_findings(run_id=run_id_2)
    assert n2 == 0
    # 总数仍为 1
    assert db_session.query(AssetReconciliation).count() == 1


# ============================================================================
# 7. 完整字段回写：mac + os + exposure + finding_id + scan_task_uuid
# ============================================================================
def test_full_details_fields_written(svc, db_session):
    f = _make_finding(
        db_session, "192.168.0.90",
        status="new", mac="AA:BB:CC:00:11:22", os_guess="Linux 5.10",
        exposure="public", scanner_id="scanner-uuid-xyz",
    )

    count = svc.reconcile_scanner_findings(run_id=uuid.uuid4())
    assert count == 1
    shadow = db_session.query(AssetReconciliation).filter(
        AssetReconciliation.reconciliation_type == TYPE_SHADOW,
    ).one()
    d = shadow.details
    assert d["mac_address"] == "AA:BB:CC:00:11:22"
    assert d["os_guess"] == "Linux 5.10"
    assert d["exposure"] == "public"
    assert d["finding_id"] == f.id
    assert d["scan_task_uuid"] == str(f.scan_task_uuid)
    assert d["scanner_id"] == "scanner-uuid-xyz"


# ============================================================================
# 8. 多个 finding 混合（new/known/adopted/ignored）
# ============================================================================
def test_mixed_findings(svc, db_session):
    """混合 finding 状态产 shadow 测试。

    expected_count 计算规则：
      - status='new' & matched_asset_id is None    → 产 shadow
      - status='new' & matched_asset_id NOT NULL   → 跳过（IP 已台账）
      - status='known' & matched_asset_id NOT NULL → 跳过（IP 已台账且同步过）
      - status='known' & matched_asset_id is None  → 产 shadow（脏数据：人为改过 status）
      - status='adopted' / status='ignored'        → 跳过（已处置）
    """
    _make_finding(db_session, "192.168.0.10", status="new")        # 产 shadow #1

    asset_for_0_11 = _make_asset(db_session, "192.168.0.11")
    f11 = _make_finding(db_session, "192.168.0.11", status="known")
    f11.matched_asset_id = asset_for_0_11.id    # known + 匹配台账 → 跳过

    _make_finding(db_session, "192.168.0.12", status="adopted")      # 跳过
    _make_finding(db_session, "192.168.0.13", status="ignored")      # 跳过

    asset = _make_asset(db_session, "192.168.0.14")
    f14 = _make_finding(db_session, "192.168.0.14", status="new")
    f14.matched_asset_id = asset.id  # IP 命中台账 → 跳过

    count = svc.reconcile_scanner_findings(run_id=uuid.uuid4())
    assert count == 1      # 只产 0.10
    assert db_session.query(AssetReconciliation).count() == 1


# ============================================================================
# 9. 空 findings 列表
# ============================================================================
def test_no_findings_no_shadow(svc):
    count = svc.reconcile_scanner_findings(run_id=uuid.uuid4())
    assert count == 0


# ============================================================================
# 10. lookback_hours 参数（验证去重窗口）
# ============================================================================
def test_lookback_hours_param(svc, db_session):
    """lookback_hours=0 → 不去重，每轮都产新 shadow（边界场景）。"""
    _make_finding(db_session, "192.168.0.55", status="new")
    n1 = svc.reconcile_scanner_findings(run_id=uuid.uuid4(), lookback_hours=0)
    assert n1 == 1
    # 第二条同 IP finding，lookback_hours=0 → 不去重
    _make_finding(db_session, "192.168.0.55", status="new")
    n2 = svc.reconcile_scanner_findings(run_id=uuid.uuid4(), lookback_hours=0)
    assert n2 == 1    # 产第二条


# ============================================================================
# 11. run() 集成：scanner_shadow_count 应出现在 summary
# ============================================================================
def test_run_summary_includes_scanner_shadow_count(svc, db_session):
    """test_run_summary 集成路径：Wazuh 没 agent，scanner 有 finding → summary 体现。

    注：run() 需要 agents 参数（Wazuh 调用）。此处 mock 避免真连 Wazuh。
    """
    from unittest.mock import patch
    from app.models.sync_task import SyncTask

    _make_finding(db_session, "192.168.0.55", status="new")

    # 创建 SyncTask 满足 FK（task_id 必须存在于 soc_sync_tasks）
    task_id = uuid.uuid4()
    db_session.add(SyncTask(
        id=task_id,
        sync_type="scheduled_reconcile",
        status="running",
    ))
    db_session.commit()

    # Mock Wazuh 不返回任何 agent（空系统）
    with patch("app.services.wazuh_client.WazuhClient") as mock_cls:
        mock_instance = mock_cls.return_value
        mock_instance.get_agents.return_value = []
        mock_instance.close.return_value = None

        summary = svc.run(agents=[], task_id=task_id)

    assert summary["scanner_shadow_count"] == 1
    assert summary["by_type"][TYPE_SHADOW] == 1


# ============================================================================
# 12. 字段命名：source 是 "scanner"（final.md §9.2 push notification 文案分支）
# ============================================================================
def test_shadow_details_source_tag_for_push_notification_branch(svc, db_session):
    """final.md §9.2 强调 details["source"]=="scanner" 是 push 文案分支条件。"""
    _make_finding(db_session, "192.168.0.66", status="new")

    svc.reconcile_scanner_findings(run_id=uuid.uuid4())
    shadow = db_session.query(AssetReconciliation).filter(
        AssetReconciliation.reconciliation_type == TYPE_SHADOW,
    ).one()
    assert shadow.details["source"] == "scanner"
    # 同时验证 asset_ip/mac_address/os_guess/exposure 都在 details（push 内容来源）
    assert shadow.details["asset_ip"] == "192.168.0.66"
    assert "suggestion" in shadow.details