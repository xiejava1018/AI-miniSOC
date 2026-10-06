"""本体对齐 API（OH-1.4 映射层 + OH-UI.8 数据源）

端点：
  GET /assets/ontology/alignment   本体类 → ORM/图谱 对齐总览（含实例计数）
  GET /assets/ontology/validate    映射完整性校验
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_role
from app.models import User
from app.models.ontology_mapping import OntologyMapping

router = APIRouter()


@router.get("/ontology/alignment", summary="本体类对齐总览")
async def ontology_alignment(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator",
                                            "viewer", "auditor")),
):
    return OntologyMapping(db).class_alignment()


@router.get("/ontology/validate", summary="本体映射完整性校验")
async def ontology_validate(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator",
                                            "viewer", "auditor")),
):
    return OntologyMapping(db).validate()


@router.get("/ontology/owl", summary="导出 OWL/XML")
async def ontology_owl(
    current_user: User = Depends(require_role("admin", "operator",
                                            "viewer", "auditor")),
):
    """把资产本体导出为 OWL/XML（OH-1.5）。"""
    from app.core.asset_ontology_owl import export_owl
    xml = export_owl()
    return Response(
        content=xml,
        media_type="application/rdf+xml",
        headers={"Content-Disposition": 'attachment; filename="asset-ontology.owl"'},
    )
