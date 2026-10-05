"""归属确认服务（OH-UI.3 确认工作台）

职责：
  1. create_or_bump_review —— 供 AssetSyncHandler 在融合判定 needs_review 时调用，
     持久化待复核观测；同指纹 pending 去重（bump occurrence_count）。
  2. list / get —— 工作台查询。
  3. resolve —— 人工裁决（merge/create/dismiss），合并/新建复用
     AssetSyncHandler 的既有方法，不重写合并逻辑。

设计见 docs/design/2026-10-05-OH-UI.3-确认工作台-spike.md。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.attribution_review import (
    DECISION_CREATE,
    DECISION_DISMISS,
    DECISION_MERGE,
    KIND_IDENTITY_CONFLICT,
    STATUS_CREATED,
    STATUS_DISMISSED,
    STATUS_MERGED,
    STATUS_PENDING,
    VALID_DECISIONS,
    AttributionReview,
)

logger = logging.getLogger(__name__)


class AttributionError(Exception):
    """归属确认业务错误（消息可直接返回前端）。"""


class AttributionConflictError(AttributionError):
    """并发裁决冲突：review 已不是 pending。"""


# observation 落库白名单（剔除端口列表/长描述等易变大字段）
OBSERVATION_FIELDS = (
    "asset_ip",
    "mac_address",
    "name",
    "os_name",
    "os_version",
    "wazuh_agent_id",
    "network_segment",
    "network_zone",
    "hardware_info",
    "asset_type",
)

# 指纹用身份信号
_FINGERPRINT_FIELDS = ("asset_ip", "mac_address", "wazuh_agent_id", "name")


def compute_fingerprint(observation: Dict[str, Any]) -> str:
    payload = {k: _stringify(observation.get(k)) for k in _FINGERPRINT_FIELDS}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stringify(v: Any) -> Optional[str]:
    if v is None:
        return None
    return str(v)


def _filter_observation(item: Dict[str, Any]) -> Dict[str, Any]:
    return {k: item[k] for k in OBSERVATION_FIELDS if item.get(k) is not None}


def _candidate_payload(
    candidates_scored: List[Tuple[Asset, Any]],
) -> List[Dict[str, Any]]:
    return [
        {
            "asset_id": str(cand.id),
            "asset_ip": str(cand.asset_ip),
            "name": cand.name,
            "score": result.to_dict(),
        }
        for cand, result in candidates_scored
    ]


class AttributionReviewService:
    """归属确认读写服务。每次请求 / 每次同步调用 new 一个（绑定单 Session）。"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 写入：sync handler 调用
    # ------------------------------------------------------------------
    def create_or_bump_review(
        self,
        *,
        item: Dict[str, Any],
        source: str,
        sync_task_id: Any,
        candidates_scored: List[Tuple[Asset, Any]],
        best: Tuple[Asset, Any],
        now: datetime,
    ) -> AttributionReview:
        """needs_review 落表。

        同 observation_fingerprint 已有 pending → bump occurrence_count /
        last_occurred_at / 评分；否则新建。
        """
        if not candidates_scored or best is None:
            raise AttributionError("待复核记录需要至少一个候选资产")

        observation = _filter_observation(item)
        fingerprint = compute_fingerprint(item)
        best_asset, best_result = best
        candidates_json = _candidate_payload(candidates_scored)

        existing = (
            self.db.query(AttributionReview)
            .filter(
                AttributionReview.observation_fingerprint == fingerprint,
                AttributionReview.status == STATUS_PENDING,
            )
            .first()
        )

        if existing is not None:
            existing.occurrence_count += 1
            existing.last_occurred_at = now
            existing.source = source
            existing.sync_task_id = sync_task_id
            existing.candidate_asset_id = best_asset.id
            existing.best_score = best_result.to_dict()
            existing.candidates = candidates_json
            existing.candidate_count = len(candidates_json)
            self.db.flush()
            logger.info(
                "OH-UI.3 待复核 bump：fp=%s 候选=%s occurrence=%d",
                fingerprint[:12], best_asset.id, existing.occurrence_count,
            )
            return existing

        review = AttributionReview(
            status=STATUS_PENDING,
            review_kind=KIND_IDENTITY_CONFLICT,
            observation=observation,
            observation_fingerprint=fingerprint,
            source=source,
            sync_task_id=sync_task_id,
            candidate_asset_id=best_asset.id,
            best_score=best_result.to_dict(),
            candidates=candidates_json,
            candidate_count=len(candidates_json),
            occurrence_count=1,
            last_occurred_at=now,
        )
        self.db.add(review)
        self.db.flush()
        logger.info(
            "OH-UI.3 新增待复核：fp=%s 观测 IP=%s 候选=%s confidence=%.2f",
            fingerprint[:12], item.get("asset_ip"),
            best_asset.id, best_result.confidence,
        )
        return review

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def list_reviews(
        self,
        *,
        status: str = STATUS_PENDING,
        candidate_asset_id: Any = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        q = self.db.query(AttributionReview).filter(
            AttributionReview.status == status
        )
        if candidate_asset_id is not None:
            q = q.filter(AttributionReview.candidate_asset_id == candidate_asset_id)

        total = q.count()
        rows = (
            q.order_by(AttributionReview.created_at.desc())
            .offset(max(0, (page - 1) * page_size))
            .limit(page_size)
            .all()
        )

        pending_count = (
            self.db.query(AttributionReview)
            .filter(AttributionReview.status == STATUS_PENDING)
            .count()
        )

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pending_count": pending_count,
            "items": [self._list_dict(r) for r in rows],
        }

    def get_review(self, review_id: Any) -> AttributionReview:
        review = self.db.get(AttributionReview, review_id)
        if review is None:
            raise AttributionError("待复核记录不存在")
        return review

    # ------------------------------------------------------------------
    # 裁决
    # ------------------------------------------------------------------
    def resolve(
        self,
        review_id: Any,
        *,
        decision: str,
        username: str,
        target_asset_id: Any = None,
        note: Optional[str] = None,
    ) -> AttributionReview:
        if decision not in VALID_DECISIONS:
            raise AttributionError(f"非法裁决动作：{decision}")

        review = self.db.get(AttributionReview, review_id)
        if review is None:
            raise AttributionError("待复核记录不存在")

        # 条件锁定，防并发裁决
        if review.status != STATUS_PENDING:
            raise AttributionConflictError(
                f"该记录已被处理（{review.status}），不能重复裁决"
            )

        now = datetime.now(review.last_occurred_at.tzinfo) if review.last_occurred_at else datetime.utcnow()

        if decision == DECISION_DISMISS:
            review.status = STATUS_DISMISSED

        elif decision == DECISION_CREATE:
            new_asset = self._create_from_observation(review, now)
            review.status = STATUS_CREATED
            review.asset_id = new_asset.id

        else:  # merge
            target_id = target_asset_id or review.candidate_asset_id
            target = self._validate_merge_target(review, target_id)
            self._merge_into_target(review, target, now)
            review.status = STATUS_MERGED
            review.asset_id = target.id

        review.resolved_by = username
        review.resolved_at = now
        review.resolve_note = note
        self.db.flush()

        logger.info(
            "OH-UI.3 裁决：review=%s decision=%s by=%s asset=%s",
            review.id, decision, username, review.asset_id,
        )
        return review

    def _validate_merge_target(self, review: AttributionReview, target_id: Any) -> Asset:
        candidate_ids = {c.get("asset_id") for c in (review.candidates or [])}
        if str(target_id) not in candidate_ids:
            raise AttributionError("合并目标不在候选资产范围内")
        target = self.db.get(Asset, target_id)
        if target is None:
            raise AttributionError("候选资产已不存在，无法合并（可改为新建或忽略）")
        return target

    def _merge_into_target(self, review: AttributionReview, target: Asset, now: datetime) -> None:
        """复用 AssetSyncHandler 的合并路径（含 IP 漂移、来源记录、change log）。"""
        from app.services.sync_handlers.asset_sync_handler import AssetSyncHandler

        handler = AssetSyncHandler()
        item = dict(review.observation)
        handler._update_existing(
            target, review.source, item, review.sync_task_id, now, self.db,
            allow_ip_update=True,
        )

    def _create_from_observation(self, review: AttributionReview, now: datetime) -> Asset:
        """复用 AssetSyncHandler 的新建路径。"""
        from app.services.sync_handlers.asset_sync_handler import AssetSyncHandler

        handler = AssetSyncHandler()
        item = dict(review.observation)
        handler._create_new(review.source, item, review.sync_task_id, now, self.db)
        self.db.flush()
        asset = (
            self.db.query(Asset)
            .filter(Asset.asset_ip == item.get("asset_ip"))
            .order_by(Asset.created_at.desc())
            .first()
        )
        if asset is None:  # 理论不可达，防御
            raise AttributionError("新建资产失败")
        return asset

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------
    @staticmethod
    def _list_dict(r: AttributionReview) -> Dict[str, Any]:
        return {
            "id": str(r.id),
            "status": r.status,
            "review_kind": r.review_kind,
            "source": r.source,
            "candidate_asset_id": str(r.candidate_asset_id) if r.candidate_asset_id else None,
            "candidate_count": r.candidate_count,
            "confidence": r.best_score.get("confidence") if r.best_score else None,
            "conflict_factors": r.best_score.get("conflict_factors", []) if r.best_score else [],
            "observation": r.observation,
            "occurrence_count": r.occurrence_count,
            "last_occurred_at": r.last_occurred_at.isoformat() if r.last_occurred_at else None,
            "resolved_by": r.resolved_by,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    @staticmethod
    def detail_dict(r: AttributionReview) -> Dict[str, Any]:
        d = AttributionReviewService._list_dict(r)
        d["best_score"] = r.best_score
        d["candidates"] = r.candidates
        d["asset_id"] = str(r.asset_id) if r.asset_id else None
        d["resolve_note"] = r.resolve_note
        return d
