"""OH-2.1 T3 — ② 归属维 + ③ 技术维 loader。

数据来源：
- 归属：``soc_assets`` (owner/owner_contact/business_unit/business_impact/data_sensitivity/protection_level)
       + ``soc_asset_business`` + ``soc_business_systems``
- 技术：``soc_assets`` (os_name/os_version/hardware_info)
       + ``soc_asset_ports`` (open_ports_count + service 去重)
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, AssetPort, AssetBusiness, BusinessSystem
from app.services.asset_profile._main import AssetOwnership, AssetTechnology
from app.services.asset_profile._helpers import orm_evidence, safe_load


@safe_load(default=AssetOwnership())
def load_ownership(db: Session, asset: Asset) -> AssetOwnership:
    """② 归属维：从 Asset + BusinessSystem 聚合。"""
    biz_rows = db.execute(
        select(BusinessSystem.name, BusinessSystem.code)
        .join(AssetBusiness, AssetBusiness.system_id == BusinessSystem.id)
        .where(AssetBusiness.asset_id == asset.id)
    ).all()
    business_systems = [r.name for r in biz_rows]
    business_system_codes = [r.code for r in biz_rows]

    evidence = [orm_evidence(db, asset, source="soc_assets")]

    return AssetOwnership(
        owner=asset.owner,
        owner_contact=asset.owner_contact,
        business_unit=asset.business_unit,
        business_impact=asset.business_impact,
        data_sensitivity=asset.data_sensitivity,
        protection_level=asset.protection_level,
        business_systems=business_systems,
        business_system_codes=business_system_codes,
        evidence=evidence,
    )


@safe_load(default=AssetTechnology())
def load_technology(db: Session, asset: Asset) -> AssetTechnology:
    """③ 技术维：从 Asset + AssetPort 聚合 OS/硬件/端口/服务。"""
    rows = db.execute(
        select(AssetPort.service, func.count(AssetPort.id))
        .where(AssetPort.asset_id == asset.id, AssetPort.state == "open")
        .group_by(AssetPort.service)
    ).all()
    services = sorted([r.service for r in rows if r.service])

    open_count = db.scalar(
        select(func.count(AssetPort.id))
        .where(AssetPort.asset_id == asset.id, AssetPort.state == "open")
    ) or 0

    evidence = [orm_evidence(db, asset, source="soc_assets")]

    return AssetTechnology(
        os_name=asset.os_name,
        os_version=asset.os_version,
        hardware_info=asset.hardware_info or {},
        open_ports_count=open_count,
        services=services,
        components=[],  # SBOM 占位：OH-2.1 SBOM 表尚未建
        evidence=evidence,
    )