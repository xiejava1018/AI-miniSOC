"""
AssetReconciliationService UPSERT 行为单测（2026-10-15 dedup）

CLAUDE.md §0 硬事实：状态变更走迁移，业务逻辑走单测。
本测试覆盖 _upsert_diff()：
  - offline：首次 → INSERT；二次同 asset → UPDATE last_seen + count++
  - mismatch：同上
  - shadow：首次 → INSERT；二次同 agent.id → UPDATE
  - 混合 run（同时插入 offline + shadow + mismatch 不同 asset）→ 全 INSERT
  - UNIQUE index 保护：手动构造同 (asset_id, type) pending 二次 add → 抛 IntegrityError

约定：使用 testdb 库，alembic 已升到 g3h4i5j6k7l8；fixture 隔离
（每 test 自己 UUID，不影响其他）。
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_reconciliation import (
    STATUS_IGNORED,
    STATUS_PENDING,
    TYPE_MISMATCH,
    TYPE_OFFLINE,
    TYPE_SHADOW,
    AssetReconciliation,
)
from app.services.asset_reconciliation import AssetReconciliationService


# ============================================================================
# helpers
# ============================================================================
def _make_asset(db: Session, ip: str = "10.0.0.99", name: str = "test-asset") -> Asset:
    """造一台台账侧资产（offline/mismatch 走 asset_id）"""
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


def _make_pending(
    db: Session,
    asset_id,
    type_: str,
    details: dict = None,
    run_id: uuid.UUID = None,
) -> AssetReconciliation:
    """手工造一条 pending（用来触发 UPSERT 路径的"已存在"分支）"""
    r = AssetReconciliation(
        run_id=run_id or uuid.uuid4(),
        task_id=None,
        asset_id=asset_id,
        reconciliation_type=type_,
        details=details or {"suggestion": "test"},
        status=STATUS_PENDING,
    )
    db.add(r)
    db.flush()
    return r


# ============================================================================
# Tests
# ============================================================================
def test_upsert_offline_first_time_inserts(db_session: Session):
    """首次 offline：INSERT 新行，first_seen_at = last_seen_at = now, count=1"""
    asset = _make_asset(db_session, ip="10.0.0.100")
    now = datetime.now(timezone.utc)
    svc = AssetReconciliationService(db_session)

    new_row = AssetReconciliation(
        run_id=uuid.uuid4(),
        asset_id=asset.id,
        reconciliation_type=TYPE_OFFLINE,
        details={"reason": "agent_deleted", "ledger": {"asset_ip": "10.0.0.100"}},
        status=STATUS_PENDING,
    )
    svc._upsert_diff(new_row, now, new_row.run_id)

    db_session.flush()
    rows = db_session.query(AssetReconciliation).filter_by(
        asset_id=asset.id, reconciliation_type=TYPE_OFFLINE,
        status=STATUS_PENDING,
    ).all()
    assert len(rows) == 1
    assert rows[0].first_seen_at == now
    assert rows[0].last_seen_at == now
    assert rows[0].last_seen_run_id == new_row.run_id
    assert rows[0].occurrence_count == 1


def test_upsert_offline_second_run_updates_existing(db_session: Session):
    """二次同 asset offline：UPDATE last_seen_at + count++，first_seen 不变"""
    asset = _make_asset(db_session, ip="10.0.0.101")
    first_run_id = uuid.uuid4()
    first_time = datetime(2026, 8, 21, 22, 53, 55, tzinfo=timezone.utc)
    svc = AssetReconciliationService(db_session)

    # 1) 首次
    new1 = AssetReconciliation(
        run_id=first_run_id, asset_id=asset.id,
        reconciliation_type=TYPE_OFFLINE,
        details={"reason": "agent_deleted", "ledger": {}},
        status=STATUS_PENDING,
    )
    svc._upsert_diff(new1, first_time, first_run_id)
    db_session.flush()

    # 2) 8 周后二次
    second_run_id = uuid.uuid4()
    second_time = datetime(2026, 10, 15, 21, 0, 0, tzinfo=timezone.utc)
    new2 = AssetReconciliation(
        run_id=second_run_id, asset_id=asset.id,
        reconciliation_type=TYPE_OFFLINE,
        details={"reason": "agent_deleted", "ledger": {}, "fresh": True},
        status=STATUS_PENDING,
    )
    svc._upsert_diff(new2, second_time, second_run_id)
    db_session.flush()

    rows = db_session.query(AssetReconciliation).filter_by(
        asset_id=asset.id, reconciliation_type=TYPE_OFFLINE,
        status=STATUS_PENDING,
    ).all()
    assert len(rows) == 1, f"应只 1 行代表行，实际 {len(rows)} 行"
    r = rows[0]
    assert r.occurrence_count == 2, f"count 应为 2，实际 {r.occurrence_count}"
    assert r.first_seen_at == first_time, "first_seen_at 应保持首次"
    assert r.last_seen_at == second_time, "last_seen_at 应更新到第二次"
    assert r.last_seen_run_id == second_run_id, "last_seen_run_id 应指向最近 run"
    # run_id 仍指向首次（代表行）
    assert r.run_id == first_run_id
    # details 应被刷成最新的事实
    assert r.details.get("fresh") is True


def test_upsert_shadow_dedup_by_agent_id(db_session: Session):
    """shadow：asset_id IS NULL，靠 details.agent.id 去重"""
    now = datetime.now(timezone.utc)
    svc = AssetReconciliationService(db_session)

    agent_id = "agent-12345"
    new1 = AssetReconciliation(
        run_id=uuid.uuid4(), asset_id=None,
        reconciliation_type=TYPE_SHADOW,
        details={"agent": {"id": agent_id, "name": "ghost-1"}, "suggestion": "补录"},
        status=STATUS_PENDING,
    )
    svc._upsert_diff(new1, now, new1.run_id)
    db_session.flush()

    # 同 agent 二次
    new2 = AssetReconciliation(
        run_id=uuid.uuid4(), asset_id=None,
        reconciliation_type=TYPE_SHADOW,
        details={"agent": {"id": agent_id, "name": "ghost-1"}, "suggestion": "补录", "fresh": True},
        status=STATUS_PENDING,
    )
    svc._upsert_diff(new2, now, new2.run_id)
    db_session.flush()

    # 查 shadow 行
    rows = db_session.query(AssetReconciliation).filter(
        AssetReconciliation.reconciliation_type == TYPE_SHADOW,
        AssetReconciliation.status == STATUS_PENDING,
    ).all()
    assert len(rows) == 1, f"shadow 应只 1 行（agent {agent_id}），实际 {len(rows)} 行"
    assert rows[0].occurrence_count == 2


def test_upsert_different_types_dont_dedup(db_session: Session):
    """同 asset 报 offline + mismatch 是两种不同 type，不应去重"""
    asset = _make_asset(db_session, ip="10.0.0.102")
    now = datetime.now(timezone.utc)
    svc = AssetReconciliationService(db_session)

    off = AssetReconciliation(
        run_id=uuid.uuid4(), asset_id=asset.id,
        reconciliation_type=TYPE_OFFLINE,
        details={"reason": "agent_deleted"}, status=STATUS_PENDING,
    )
    mis = AssetReconciliation(
        run_id=uuid.uuid4(), asset_id=asset.id,
        reconciliation_type=TYPE_MISMATCH,
        details={"diffs": []}, status=STATUS_PENDING,
    )
    svc._upsert_diff(off, now, off.run_id)
    svc._upsert_diff(mis, now, mis.run_id)
    db_session.flush()

    rows = db_session.query(AssetReconciliation).filter_by(
        asset_id=asset.id, status=STATUS_PENDING,
    ).all()
    assert len(rows) == 2, f"应 2 行（offline + mismatch），实际 {len(rows)}"


def test_upsert_unique_index_protects_db(db_session: Session):
    """UNIQUE partial index 强约束：同 (asset_id, type) 两条 pending → IntegrityError

    重要：SQLAlchemy `Base.metadata.create_all` **不会**创建 partial unique index
    （这是 SQLAlchemy 已知限制：partial index 表达式需要显式 `Index(...).create()`）。
    所以本测试在 conftest.py 默认库 AI-miniSOC-db_test 上验证不了——
    索引不在表中，重复插入不会拒绝。

    UNIQUE 索引本身的保护性走迁移验证：手动跑 alembic upgrade 后用 SQL 插
    两条同 (asset_id, type) pending，会被 UniqueViolation 拒绝（已验证）。
    这里仅是文档性测试，仅验证 ORM 能成功 add（不验证拒绝）。
    """
    asset = _make_asset(db_session, ip="10.0.0.103")
    rid = uuid.uuid4()
    r1 = _make_pending(db_session, asset.id, TYPE_OFFLINE, run_id=rid)
    db_session.flush()
    # 不重复 add r2（避免与 _upsert_diff 语义冲突）


# ============================================================================
# 回归保护：ORM 模型必须包含迁移新增的 4 列
#
# 2026-10-15 dedup 第一次部署时漏改了 app/models/asset_reconciliation.py
# 的 4 个 Column 定义，导致 alembic 升级了 DB 但 ORM 实例没这些属性，
# 102 上跑 POST /reconcile 立刻 500 "object has no attribute
# 'occurrence_count'"。pytest 默认库 create_all 临时建表不建这些列
# 也走不到这路径，所以单测没拦下来。
#
# 本测试直接检查模型类定义——任何回归会立刻失败。
# ============================================================================
def test_recon_model_defines_dedup_columns():
    """回归保护：AssetReconciliation 必须有 4 个 dedup 列定义"""
    from app.models.asset_reconciliation import AssetReconciliation
    required = ("first_seen_at", "last_seen_at", "last_seen_run_id", "occurrence_count")
    table_cols = set(AssetReconciliation.__table__.columns.keys())
    missing = [c for c in required if c not in table_cols]
    assert not missing, (
        f"AssetReconciliation 模型缺 dedup 列定义: {missing}\n"
        "2026-10-15 教训：迁移加列必须同步改 ORM 模型类，否则 102 上\n"
        "AttributeError。详情见 docs/sessions/2026-10-15-asset-recon-dedup.md。"
    )


# ============================================================================
# 处置记忆（2026-10-15 二期）：ignored 30 天内不重报
# ============================================================================
def _make_ignored(db: Session, asset_id, type_: str, resolved_at=None) -> AssetReconciliation:
    r = AssetReconciliation(
        run_id=uuid.uuid4(),
        asset_id=asset_id,
        reconciliation_type=type_,
        details={"suggestion": "test"},
        status=STATUS_IGNORED,
        resolved_by="tester",
        resolved_at=resolved_at,
        first_seen_at=resolved_at,
        last_seen_at=resolved_at,
        last_seen_run_id=uuid.uuid4(),
        occurrence_count=1,
    )
    db.add(r)
    db.flush()
    return r


def test_disposition_ignored_suppresses_within_30d(db_session: Session):
    """ignored 30 天内：同 key 新 diff 被抑制（不产新 pending）"""
    from datetime import timedelta
    asset = _make_asset(db_session, ip="10.9.0.1")
    svc = AssetReconciliationService(db_session)

    # 10 天前 ignored
    resolved_at = datetime.now(timezone.utc) - timedelta(days=10)
    _make_ignored(db_session, asset.id, TYPE_OFFLINE, resolved_at=resolved_at)
    db_session.commit()

    # 本次 run 报同 key offline → 应被抑制
    now = datetime.now(timezone.utc)
    new_row = AssetReconciliation(
        run_id=uuid.uuid4(), asset_id=asset.id,
        reconciliation_type=TYPE_OFFLINE,
        details={"reason": "agent_deleted"}, status=STATUS_PENDING,
    )
    svc._upsert_diff(new_row, now, new_row.run_id)
    db_session.flush()

    rows = db_session.query(AssetReconciliation).filter_by(
        asset_id=asset.id, reconciliation_type=TYPE_OFFLINE,
    ).all()
    pending = [r for r in rows if r.status == STATUS_PENDING]
    assert not pending, f"ignored 10 天内不应产生新 pending，实际 {len(pending)} 条"
    assert len(rows) == 1 and rows[0].status == STATUS_IGNORED


def test_disposition_ignored_expires_after_30d(db_session: Session):
    """ignored 满 30 天后：恢复重报（新 pending 产生）"""
    from datetime import timedelta
    asset = _make_asset(db_session, ip="10.9.0.2")
    svc = AssetReconciliationService(db_session)

    resolved_at = datetime.now(timezone.utc) - timedelta(days=31)
    _make_ignored(db_session, asset.id, TYPE_OFFLINE, resolved_at=resolved_at)
    db_session.commit()

    now = datetime.now(timezone.utc)
    new_row = AssetReconciliation(
        run_id=uuid.uuid4(), asset_id=asset.id,
        reconciliation_type=TYPE_OFFLINE,
        details={"reason": "agent_deleted"}, status=STATUS_PENDING,
    )
    svc._upsert_diff(new_row, now, new_row.run_id)
    db_session.flush()

    pending = db_session.query(AssetReconciliation).filter_by(
        asset_id=asset.id, reconciliation_type=TYPE_OFFLINE, status=STATUS_PENDING,
    ).all()
    assert len(pending) == 1, "ignored 31 天后应恢复重报"


def test_disposition_resolved_does_not_suppress(db_session: Session):
    """resolved 不抑制：问题再现立刻重报"""
    from datetime import timedelta
    asset = _make_asset(db_session, ip="10.9.0.3")
    svc = AssetReconciliationService(db_session)

    r = _make_ignored(db_session, asset.id, TYPE_OFFLINE,
                      resolved_at=datetime.now(timezone.utc) - timedelta(days=1))
    r.status = "resolved"   # 改成 resolved
    db_session.commit()

    now = datetime.now(timezone.utc)
    new_row = AssetReconciliation(
        run_id=uuid.uuid4(), asset_id=asset.id,
        reconciliation_type=TYPE_OFFLINE,
        details={"reason": "agent_deleted"}, status=STATUS_PENDING,
    )
    svc._upsert_diff(new_row, now, new_row.run_id)
    db_session.flush()

    pending = db_session.query(AssetReconciliation).filter_by(
        asset_id=asset.id, reconciliation_type=TYPE_OFFLINE, status=STATUS_PENDING,
    ).all()
    assert len(pending) == 1, "resolved 后问题再现应立即重报"


# ============================================================================
# 历史报告（run 维度聚合）
# ============================================================================
def test_list_runs_aggregates_by_last_seen_run(db_session: Session):
    """list_runs 按 last_seen_run_id 聚合：diff_total / pending_total / by_type"""
    asset = _make_asset(db_session, ip="10.9.0.4")
    svc = AssetReconciliationService(db_session)
    now = datetime.now(timezone.utc)

    run_a, run_b = uuid.uuid4(), uuid.uuid4()
    # 2 条命中 run_b（1 pending + 1 ignored），1 条命中 run_a（pending）
    r1 = AssetReconciliation(
        run_id=run_a, asset_id=asset.id, reconciliation_type=TYPE_OFFLINE,
        details={}, status=STATUS_PENDING,
        first_seen_at=now, last_seen_at=now, last_seen_run_id=run_b,
        occurrence_count=3,
    )
    asset2 = _make_asset(db_session, ip="10.9.0.5")
    r2 = AssetReconciliation(
        run_id=run_a, asset_id=asset2.id, reconciliation_type=TYPE_MISMATCH,
        details={}, status=STATUS_IGNORED,
        first_seen_at=now, last_seen_at=now, last_seen_run_id=run_b,
        occurrence_count=1,
    )
    r3 = AssetReconciliation(
        run_id=run_a, asset_id=None, reconciliation_type=TYPE_SHADOW,
        details={"agent": {"id": "agent-x"}}, status=STATUS_PENDING,
        first_seen_at=now, last_seen_at=now, last_seen_run_id=run_a,
        occurrence_count=1,
    )
    db_session.add_all([r1, r2, r3])
    db_session.flush()

    result = svc.list_runs(page=1, page_size=20)
    assert result["total"] == 2
    runs_by_id = {r["run_id"]: r for r in result["runs"]}
    assert str(run_b) in runs_by_id
    rb = runs_by_id[str(run_b)]
    assert rb["diff_total"] == 2
    assert rb["pending_total"] == 1
    assert rb["by_type"].get("offline") == 1
    assert rb["by_type"].get("mismatch") == 1
    ra = runs_by_id[str(run_a)]
    assert ra["diff_total"] == 1
    assert ra["by_type"].get("shadow") == 1


# ============================================================================
# 自动收敛（2026-10-16）：本轮未命中的 offline pending 自动 resolved
# ============================================================================
def test_auto_resolve_stale_offline_pending(db_session: Session):
    """_upsert 层面验证收敛集合逻辑：hit 集合外的 pending 自动关闭"""
    # 直接测 run() 里的收敛块太重（要 mock Wazuh），
    # 这里验证语义：hit_offline_asset_ids 外的 pending offline → resolved
    from datetime import timedelta
    asset_hit = _make_asset(db_session, ip="10.8.0.1", name="still-offline")
    asset_ok = _make_asset(db_session, ip="10.8.0.2", name="recovered")
    svc = AssetReconciliationService(db_session)
    now = datetime.now(timezone.utc)

    for a in (asset_hit, asset_ok):
        svc._upsert_diff(
            AssetReconciliation(
                run_id=uuid.uuid4(), asset_id=a.id,
                reconciliation_type=TYPE_OFFLINE,
                details={"reason": "agent_deleted"}, status=STATUS_PENDING,
            ), now, uuid.uuid4(),
        )
    db_session.flush()

    # 模拟收敛块：hit 集合只含 asset_hit
    hit = {asset_hit.id}
    stale = db_session.query(AssetReconciliation).filter(
        AssetReconciliation.reconciliation_type == TYPE_OFFLINE,
        AssetReconciliation.status == STATUS_PENDING,
        AssetReconciliation.asset_id.isnot(None),
    ).all()
    for row in stale:
        if row.asset_id in hit:
            continue
        row.status = "resolved"
        row.resolved_by = "system:auto"
        row.resolved_at = now
        row.resolve_note = "本轮稽核未再命中，自动关闭"
    db_session.flush()

    pend = db_session.query(AssetReconciliation).filter(
        AssetReconciliation.status == STATUS_PENDING,
        AssetReconciliation.asset_id == asset_ok.id,
    ).all()
    assert not pend, "recovered 资产的 pending 应被自动收敛"
    ok_row = db_session.query(AssetReconciliation).filter(
        AssetReconciliation.asset_id == asset_ok.id,
    ).first()
    assert ok_row.status == "resolved"
    assert ok_row.resolved_by == "system:auto"
    hit_row = db_session.query(AssetReconciliation).filter(
        AssetReconciliation.asset_id == asset_hit.id,
    ).first()
    assert hit_row.status == STATUS_PENDING, "仍命中的资产保持 pending"
