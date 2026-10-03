"""OH-2.1 T2 — ① 身份维 loader。

数据来源：
- ``soc_assets.wazuh_agent_id`` / ``data_source`` / ``mac_address`` / ``network_segment``
- ``soc_asset_sources``（多源身份绑定，按 asset_id 聚合）
- ``soc_identity_bindings``（DHCP/SSO 身份关联）
- 派生 hostname：``soc_assets.name`` 或 IdentityBinding.account

置信度：取 AssetSource 行数 + IdentityBinding 行数 / 2（≥1 即 0.8，2+ 即 1.0 上限 1.0）。
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, IdentityBinding
from app.models.asset_source import AssetSource
from app.services.asset_profile._main import AssetIdentity
from app.services.asset_profile._helpers import orm_evidence, safe_load


@safe_load(default=AssetIdentity())
def load_identity(db: Session, asset: Asset) -> AssetIdentity:
    """① 身份维：从 Asset + AssetSource + IdentityBinding 聚合多源身份。"""
    # db 可为 None（仅读 asset 字段的场景）
    def _scalar_count(stmt):
        """count 类查询：None 时返回 0（用于计算）。"""
        if db is None:
            return 0
        return db.scalar(stmt) or 0

    def _scalar_value(stmt):
        """值类查询：None 时返回 None（保留字段空值）。"""
        if db is None:
            return None
        return db.scalar(stmt)

    bindings_count = _scalar_count(
        select(func.count(IdentityBinding.id))
        .where(IdentityBinding.asset_id == asset.id)
    )

    sources_count = _scalar_count(
        select(func.count(AssetSource.id))
        .where(AssetSource.asset_id == asset.id)
    )

    # identity_confidence：多源覆盖度
    total_refs = bindings_count + sources_count
    if total_refs >= 3:
        identity_confidence = 1.0
    elif total_refs >= 1:
        identity_confidence = 0.8
    elif asset.wazuh_agent_id or asset.data_source:
        identity_confidence = 0.5
    else:
        identity_confidence = 0.0

    hostname = asset.name
    if not hostname and bindings_count > 0:
        # 取最近一条 binding 的 account 作为 fallback
        recent = _scalar_value(
            select(IdentityBinding.account)
            .where(IdentityBinding.asset_id == asset.id)
            .order_by(IdentityBinding.last_seen.desc())
            .limit(1)
        )
        hostname = recent

    # 取最近一条 AssetSource.source_id 作为 source_id（强身份锚）
    primary_source_id = _scalar_value(
        select(AssetSource.source_id)
        .where(AssetSource.asset_id == asset.id)
        .order_by(AssetSource.last_seen_at.desc())
        .limit(1)
    )

    evidence = [orm_evidence(db, asset, source="soc_assets")]
    if sources_count > 0:
        evidence.append(orm_evidence(db, asset, source="soc_asset_sources"))

    return AssetIdentity(
        source_id=primary_source_id,
        data_source=asset.data_source,
        wazuh_agent_id=asset.wazuh_agent_id,
        mac_address=str(asset.mac_address) if asset.mac_address else None,
        hostname=hostname,
        identity_confidence=identity_confidence,
        identity_bindings_count=bindings_count,
        evidence=evidence,
    )