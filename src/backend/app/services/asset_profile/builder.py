"""OH-2.1 八维画像 build_profile 编排器。

串行调用 8 个 loader，构造 AssetProfile 并填充 coverage/profile_confidence。
AHS 字段由 OH-2.2 落实公式，本任务只画框。

单点失败容忍：
- 任一 loader 抛异常 → 该维返回空 dataclass（@safe_load 兜底），其他维继续
- 最终 AssetProfile 仍可用，仅覆盖度下降
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Asset
from app.services.asset_profile._main import (
    AssetProfile,
    compute_coverage,
    compute_profile_confidence,
    profile_to_dict,
)
from app.services.asset_profile.loaders.identity import load_identity
from app.services.asset_profile.loaders.ownership_tech import load_ownership, load_technology
from app.services.asset_profile.loaders.risk_dims import load_exposure, load_vulnerability, load_threat
from app.services.asset_profile.loaders.compliance_behavior import load_compliance, load_behavior


def build_profile(db: Session, asset: Asset) -> AssetProfile:
    """从 ORM 构造一帧 AssetProfile。

    参数：
        db: SQLAlchemy Session
        asset: 资产 ORM 实例

    返回：
        AssetProfile（已含 coverage + profile_confidence；AHS 字段保留位）
    """
    identity = load_identity(db, asset)
    ownership = load_ownership(db, asset)
    technology = load_technology(db, asset)
    exposure = load_exposure(db, asset)
    vulnerability = load_vulnerability(db, asset)
    threat = load_threat(db, asset)
    compliance = load_compliance(db, asset)
    behavior = load_behavior(db, asset)

    # 第一次构造：算 coverage
    profile_with_cov = AssetProfile(
        asset_id=str(asset.id),
        identity=identity,
        ownership=ownership,
        technology=technology,
        exposure=exposure,
        vulnerability=vulnerability,
        threat=threat,
        compliance=compliance,
        behavior=behavior,
    )
    cov = compute_coverage(profile_with_cov)
    # frozen dataclass 要求：在 dataclass factory 阶段传入 computed field
    # → 用 object.__setattr__ 绕过 frozen（仅本框架内部使用，外面应走 profile_with_cov.profile_confidence）
    profile_conf = compute_profile_confidence(
        AssetProfile(
            asset_id=profile_with_cov.asset_id,
            identity=profile_with_cov.identity,
            ownership=profile_with_cov.ownership,
            technology=profile_with_cov.technology,
            exposure=profile_with_cov.exposure,
            vulnerability=profile_with_cov.vulnerability,
            threat=profile_with_cov.threat,
            compliance=profile_with_cov.compliance,
            behavior=profile_with_cov.behavior,
            coverage=cov,
        )
    )
    final = AssetProfile(
        asset_id=profile_with_cov.asset_id,
        identity=profile_with_cov.identity,
        ownership=profile_with_cov.ownership,
        technology=profile_with_cov.technology,
        exposure=profile_with_cov.exposure,
        vulnerability=profile_with_cov.vulnerability,
        threat=profile_with_cov.threat,
        compliance=profile_with_cov.compliance,
        behavior=profile_with_cov.behavior,
        coverage=cov,
        profile_confidence=profile_conf,
    )
    return final


def build_profile_dict(db: Session, asset: Asset) -> dict:
    """build_profile 的 JSON-ready 包装。"""
    profile = build_profile(db, asset)
    return profile_to_dict(profile)
