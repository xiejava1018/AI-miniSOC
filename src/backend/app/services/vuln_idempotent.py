"""
脆弱性写入幂等工具（P2-T5）

PG 唯一约束已就位：
- soc_vulnerabilities.cve_id UNIQUE
- soc_asset_vulnerabilities (asset_id, vulnerability_id, scanner) UNIQUE

提供 ON CONFLICT 的原子化 upsert，避免 Python 层先查再 add/update 在并发下不安全的问题。
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.vulnerability import Vulnerability, AssetVulnerability
from app.schemas.vulnerability import SeverityEnum, ScannerEnum, VulnerabilityStatusEnum

logger = logging.getLogger(__name__)


def upsert_vulnerability(
    db: Session,
    *,
    cve_id: str,
    title: str,
    severity: str,
    type_: str = "scap",
    description: Optional[str] = None,
    cvss_score: Optional[float] = None,
    cvss_vector: Optional[str] = None,
    affected_packages: Optional[dict] = None,
    fix_suggestion: Optional[str] = None,
    references: Optional[List[str]] = None,
    published_date: Optional[Any] = None,
    has_exploit: bool = False,
    discovered_at: Optional[datetime] = None,
) -> Vulnerability:
    """原子化 upsert Vulnerability by cve_id（P2-T5：保证重跑同步不重复）。

    Returns: 已落库的 Vulnerability ORM 对象（cve_id 唯一约束保证）。
    """
    values = dict(
        type=type_,
        cve_id=cve_id,
        title=title,
        description=description,
        cvss_score=cvss_score,
        cvss_vector=cvss_vector,
        severity=severity,
        affected_packages=affected_packages,
        fix_suggestion=fix_suggestion,
        references=references,
        published_date=published_date,
        has_exploit=has_exploit,
    )
    if discovered_at is not None:
        values["discovered_at"] = discovered_at

    stmt = pg_insert(Vulnerability).values(**values).on_conflict_do_update(
        index_elements=["cve_id"],
        set_={
            # 只在传入值非 None 时更新，避免覆盖更新的字段
            k: v for k, v in values.items() if v is not None and k not in ("cve_id", "type")
        },
    )
    db.execute(stmt)
    db.flush()

    # 再查回 ORM 对象
    vuln = db.query(Vulnerability).filter(Vulnerability.cve_id == cve_id).first()
    return vuln


def upsert_asset_vulnerability(
    db: Session,
    *,
    asset_id,
    vulnerability_id,
    scanner: str = "wazuh",
    status: str = "open",
    detected_at: Optional[datetime] = None,
    due_date: Optional[datetime] = None,
) -> AssetVulnerability:
    """原子化 upsert AssetVulnerability by (asset_id, vuln_id, scanner)。

    ON CONFLICT DO UPDATE：重跑同步不增长关联数。
    """
    values = dict(
        asset_id=asset_id,
        vulnerability_id=vulnerability_id,
        scanner=scanner,
        status=status,
        detected_at=detected_at or datetime.utcnow(),
        due_date=due_date,
    )
    stmt = pg_insert(AssetVulnerability).values(**values).on_conflict_do_update(
        index_elements=["asset_id", "vulnerability_id", "scanner"],
        set_={
            "status": values["status"],
            "detected_at": values["detected_at"],
            "due_date": values["due_date"],
        },
    )
    db.execute(stmt)
    db.flush()
    assoc = (
        db.query(AssetVulnerability)
        .filter(
            AssetVulnerability.asset_id == asset_id,
            AssetVulnerability.vulnerability_id == vulnerability_id,
            AssetVulnerability.scanner == scanner,
        )
        .first()
    )
    return assoc