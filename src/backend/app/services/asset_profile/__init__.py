"""OH-2.1 八维画像 ORM 装载器子包（公共 loader 函数）。

**目录结构**（避免循环 import）：
    asset_profile/              ← 本子包（统一对外接口）
        __init__.py            ← 入口文件（re-export 所有公共符号）
        _main.py               ← 8 dataclass + 纯计算（向后兼容历史 import）
        _helpers.py            ← 公共工具（orm_evidence, safe_load, EVIDENCE_CONFIDENCE）
        builder.py             ← build_profile 编排器
        loaders/
            __init__.py
            identity.py
            ownership_tech.py
            risk_dims.py
            compliance_behavior.py

**强约束**（来自 OH-2.1 §强约束 #1）：
- 8 dataclass 已在 ``_main.py`` 落地，本子包只负责从 ORM 取数据填充
- 所有 loader 签名统一为 ``load_<dim>(db, asset) -> DimDataclass``
- evidence.source 必填，取 ORM 表名（如 "soc_assets"）；observed_at 取主表 updated_at
- confidence 默认 0.8（直接 ORM 读）；Fusion 类（Identity）由 fusion_confidence 取
- loader 异常 → 返回"该维空 dataclass"，不抛错（保证 build_profile 不被单维失败阻塞）
"""
# loader 直接 import：主模块 _main.py 已被先 import（避免循环）
from app.services.asset_profile.loaders.identity import load_identity
from app.services.asset_profile.loaders.ownership_tech import load_ownership, load_technology
from app.services.asset_profile.loaders.risk_dims import load_exposure, load_vulnerability, load_threat
from app.services.asset_profile.loaders.compliance_behavior import load_compliance, load_behavior
from app.services.asset_profile.builder import build_profile, build_profile_dict

# re-export 8 dataclass + 计算函数（兼容历史 ``from app.services.asset_profile import AssetProfile``）
from app.services.asset_profile._main import (
    AssetProfile, AssetIdentity, AssetOwnership, AssetTechnology, AssetExposure,
    AssetVulnerability, AssetThreat, AssetCompliance, AssetBehavior,
    EvidenceItem, CoverageInfo, DIMENSIONS,
    compute_coverage, compute_profile_confidence, profile_to_dict, empty_profile,
)

__all__ = [
    # loader 函数
    "load_identity",
    "load_ownership",
    "load_technology",
    "load_exposure",
    "load_vulnerability",
    "load_threat",
    "load_compliance",
    "load_behavior",
    "build_profile",
    "build_profile_dict",
    # 8 dataclass + 计算
    "AssetProfile",
    "AssetIdentity",
    "AssetOwnership",
    "AssetTechnology",
    "AssetExposure",
    "AssetVulnerability",
    "AssetThreat",
    "AssetCompliance",
    "AssetBehavior",
    "EvidenceItem",
    "CoverageInfo",
    "DIMENSIONS",
    "compute_coverage",
    "compute_profile_confidence",
    "profile_to_dict",
    "empty_profile",
]