"""EntityResolver API（底座 P1 统一实体锚，D-2 拍板后落地）

  GET  /assets/entity-resolver/resolve?alias=...&alias_type=...
  GET  /assets/entity-resolver/coverage
  POST /assets/entity-resolver/backfill        （OH-P1.T6 事件回填）
  GET  /assets/entity-resolver/alignment-report（OH-P1.T6 告警对齐报告）
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.audit_decorator import log_audit
from app.core.database import get_db
from app.core.permissions import require_role
from app.models.user import User
from app.services.entity_resolver import (
    EntityResolver,
    alert_alignment_report,
    backfill_events_alignment,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/entity-resolver/resolve", summary="标识符→asset_id 统一解析")
async def resolve_alias(
    alias: str = Query(..., min_length=1, max_length=100,
                       description="asset_ip / wazuh_agent_id / mac / 日志 IP"),
    alias_type: str = Query(
        None,
        description="wazuh_agent_id / asset_ip / mac_address / log_ip；缺省自动判定",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator",
                                              "viewer", "auditor")),
):
    resolver = EntityResolver(db)
    return resolver.resolve(alias, alias_type=alias_type)


@router.get("/entity-resolver/coverage", summary="实体锚覆盖率快照（分段）")
async def resolver_coverage(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator",
                                              "viewer", "auditor")),
):
    return EntityResolver(db).coverage()


@router.post("/entity-resolver/backfill", summary="事件 dst_ip 全量锚定回填")
@log_audit(action="UPDATE", resource_type="entity_resolver")
async def resolver_backfill(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    """幂等回填（只处理 NULL 行）；未命中保持 NULL（S8 影子候选）。"""
    return backfill_events_alignment(db)


@router.get("/entity-resolver/alignment-report",
            summary="告警 agent.ip 对齐报告（只读）")
async def resolver_alert_report(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator",
                                              "viewer", "auditor")),
):
    return alert_alignment_report(db, days=days)
