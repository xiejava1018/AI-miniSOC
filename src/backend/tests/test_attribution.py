"""OH-UI.3 确认工作台 · AttributionReviewService 单测。

覆盖 spike §8：
  - needs_review 落表；同观测重复触发 bump（仍 1 行、occurrence=2）
  - 裁决 merge（含 IP 漂移，不产生重复资产）/ create / dismiss
  - 重复/并发裁决 → AttributionConflictError
  - 合并目标越界 / 候选已删除 → AttributionError
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.attribution_review import (
    STATUS_CREATED,
    STATUS_DISMISSED,
    STATUS_MERGED,
    STATUS_PENDING,
    AttributionReview,
)
from app.services.attribution_service import (
    AttributionConflictError,
    AttributionError,
    AttributionReviewService,
)
from app.services.identity_fusion import score_fusion
from app.services.sync_handlers.asset_sync_handler import AssetSyncHandler

NOW = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)


def _asset_count(db: Session) -> int:
    return db.query(func.count(Asset.id)).scalar() or 0


def _review_count(db: Session) -> int:
    return db.query(func.count(AttributionReview.id)).scalar() or 0


def _seed_candidate(db: Session, **kw) -> Asset:
    defaults = dict(
        name="host1",
        asset_ip="10.0.0.10",
        network_segment="default",
        wazuh_agent_id="010",
    )
    defaults.update(kw)
    a = Asset(**defaults)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _observation(**kw):
    # needs_review 场景（经评分核对，见 identity_fusion 冲突压制逻辑）：
    # IP + hostname 一致，wazuh_agent 不一致——agent 非强冲突因子，
    # confidence=.4/.6=.667 落在复核区间，且无强匹配，不会 auto_merge。
    obs = {
        "asset_ip": "10.0.0.10",
        "name": "host1",
        "wazuh_agent_id": "011",
    }
    obs.update(kw)
    return obs


def _scored(obs: dict, candidate: Asset):
    res = score_fusion(obs, candidate)
    assert res.decision == "needs_review"
    return [(candidate, res)], (candidate, res)


class TestCreateOrBump:
    def test_creates_review(self, db_session: Session):
        cand = _seed_candidate(db_session)
        obs = _observation()
        scored, best = _scored(obs, cand)

        review = AttributionReviewService(db_session).create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best, now=NOW,
        )

        assert review.status == STATUS_PENDING
        assert review.candidate_asset_id == cand.id
        assert review.occurrence_count == 1
        assert review.candidate_count == 1
        assert review.best_score["conflict"] is False
        assert _review_count(db_session) == 1

    def test_duplicate_bumps_instead_of_new_row(self, db_session: Session):
        cand = _seed_candidate(db_session)
        obs = _observation()
        scored, best = _scored(obs, cand)
        svc = AttributionReviewService(db_session)

        svc.create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best, now=NOW,
        )
        bumped = svc.create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best,
            now=datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc),
        )

        assert _review_count(db_session) == 1
        assert bumped.occurrence_count == 2

    def test_no_candidates_raises(self, db_session: Session):
        with pytest.raises(AttributionError):
            AttributionReviewService(db_session).create_or_bump_review(
                item=_observation(), source="wazuh", sync_task_id=None,
                candidates_scored=[], best=None, now=NOW,
            )


class TestResolveMerge:
    def test_merge_to_candidate(self, db_session: Session):
        cand = _seed_candidate(db_session)
        obs = _observation()
        scored, best = _scored(obs, cand)
        svc = AttributionReviewService(db_session)
        review = svc.create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best, now=NOW,
        )

        result = svc.resolve(
            review.id, decision="merge", username="operator1",
        )

        assert result.status == STATUS_MERGED
        assert result.asset_id == cand.id
        assert result.resolved_by == "operator1"
        # 复用合并路径：agent 已按观测同步，且无重复资产
        db_session.refresh(cand)
        assert cand.wazuh_agent_id == "011"
        assert str(cand.asset_ip) == "10.0.0.10"
        assert _asset_count(db_session) == 1

    def test_merge_target_out_of_candidates_rejected(self, db_session: Session):
        cand = _seed_candidate(db_session)
        other = _seed_candidate(
            db_session, name="other", asset_ip="10.0.0.30",
            wazuh_agent_id="030",
        )
        obs = _observation()
        scored, best = _scored(obs, cand)
        svc = AttributionReviewService(db_session)
        review = svc.create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best, now=NOW,
        )

        with pytest.raises(AttributionError):
            svc.resolve(
                review.id, decision="merge", username="op",
                target_asset_id=other.id,
            )

    def test_merge_deleted_candidate_rejected(self, db_session: Session):
        cand = _seed_candidate(db_session)
        obs = _observation()
        scored, best = _scored(obs, cand)
        svc = AttributionReviewService(db_session)
        review = svc.create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best, now=NOW,
        )

        db_session.delete(cand)
        db_session.commit()

        with pytest.raises(AttributionError):
            svc.resolve(review.id, decision="merge", username="op")


class TestResolveCreate:
    def test_create_new_asset(self, db_session: Session):
        cand = _seed_candidate(db_session)
        # 观测与候选 IP 相同：裁决为「不同实体」时，新资产落到另一个网段
        # （否则 (segment, ip) 唯一约束不允许），符合「同 IP 不同设备」语义
        obs = _observation(network_segment="guest")
        scored, best = _scored(obs, cand)
        svc = AttributionReviewService(db_session)
        review = svc.create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best, now=NOW,
        )
        before = _asset_count(db_session)

        result = svc.resolve(review.id, decision="create", username="op")

        assert result.status == STATUS_CREATED
        assert result.asset_id is not None
        assert result.asset_id != cand.id
        assert _asset_count(db_session) == before + 1


class TestResolveDismiss:
    def test_dismiss_no_asset_change(self, db_session: Session):
        cand = _seed_candidate(db_session)
        obs = _observation()
        scored, best = _scored(obs, cand)
        svc = AttributionReviewService(db_session)
        review = svc.create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best, now=NOW,
        )
        before = _asset_count(db_session)

        result = svc.resolve(
            review.id, decision="dismiss", username="op", note="测试流量",
        )

        assert result.status == STATUS_DISMISSED
        assert result.asset_id is None
        assert result.resolve_note == "测试流量"
        assert _asset_count(db_session) == before


class TestResolveGuards:
    def test_invalid_decision(self, db_session: Session):
        cand = _seed_candidate(db_session)
        obs = _observation()
        scored, best = _scored(obs, cand)
        svc = AttributionReviewService(db_session)
        review = svc.create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best, now=NOW,
        )
        with pytest.raises(AttributionError):
            svc.resolve(review.id, decision="bogus", username="op")

    def test_double_resolve_conflicts(self, db_session: Session):
        cand = _seed_candidate(db_session)
        obs = _observation()
        scored, best = _scored(obs, cand)
        svc = AttributionReviewService(db_session)
        review = svc.create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best, now=NOW,
        )

        svc.resolve(review.id, decision="dismiss", username="op1")
        with pytest.raises(AttributionConflictError):
            svc.resolve(review.id, decision="merge", username="op2")

    def test_resolved_fingerprint_can_reenter_pending(self, db_session: Session):
        cand = _seed_candidate(db_session)
        obs = _observation()
        scored, best = _scored(obs, cand)
        svc = AttributionReviewService(db_session)
        review = svc.create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best, now=NOW,
        )
        svc.resolve(review.id, decision="dismiss", username="op")

        new_review = svc.create_or_bump_review(
            item=obs, source="wazuh", sync_task_id=None,
            candidates_scored=scored, best=best,
            now=datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc),
        )
        assert new_review.id != review.id
        assert _review_count(db_session) == 2
