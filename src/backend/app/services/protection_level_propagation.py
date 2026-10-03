"""等保等级继承传播引擎（设计 §5 · T4 · D1-D4）

第一性原理：等保定级对象是业务系统（GB/T 22240-2020），资产等级是派生值。
权威源 = soc_business_systems.protection_level；资产侧就高继承（D3），
且只对 source='inherited' 的资产生效（D4）——人工裁定（manual）永不被传播覆盖。

调用约定：所有函数接收调用方（API 端点）的 db session，传播与业务动作同事务提交，
绝不开独立事务——避免"link 成功但传播失败"的分裂态。

档位序（D3）：level_5 > level_4 > level_3 > level_2 > level_1
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.business_system import AssetBusiness, BusinessSystem

logger = logging.getLogger(__name__)

# 档位序（D3）。集中定义，全项目等级比较禁止散落魔法字符串。
PL_RANK: Dict[str, int] = {
    "level_1": 1, "level_2": 2, "level_3": 3, "level_4": 4, "level_5": 5,
}


def strictest(levels: List[str]) -> Optional[str]:
    """取最高档位；空列表返回 None。非法值按 -1 处理（不参与比较）。"""
    best: Optional[str] = None
    best_rank = -1
    for lv in levels:
        r = PL_RANK.get(lv, -1)
        if r > best_rank:
            best_rank = r
            best = lv
    return best


def compute_inherited_level(db: Session, asset_id) -> Optional[str]:
    """返回该资产所有关联系统中的最高等级；无关联返回 None。"""
    rows = (
        db.query(BusinessSystem.protection_level)
        .join(AssetBusiness, AssetBusiness.system_id == BusinessSystem.id)
        .filter(AssetBusiness.asset_id == asset_id)
        .all()
    )
    return strictest([r[0] for r in rows])


def recompute_asset(db: Session, asset_id, *, allow_manual: bool) -> dict:
    """按 D4 语义重算单个资产的继承等级。

    - allow_manual=True（link 显式 inherit=true）：无条件传播就高档并置 source='inherited'
    - allow_manual=False：仅 source='inherited' 的资产重算（manual 跳过）
    - 无关联系统：值保留（不静默降回 level_2），source 置 'manual'（诚实降级：来源消失留人工复核）

    返回 {asset_id, changed, old, new, source}——调用方汇总落审计链。
    不 commit：事务归调用方。
    """
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset is None:
        return {"asset_id": str(asset_id), "changed": False, "old": None,
                "new": None, "source": None, "skipped": "asset_not_found"}

    old = asset.protection_level
    old_source = asset.protection_level_source

    target = compute_inherited_level(db, asset_id)

    if target is None:
        # 无关联系统：值保留，source → manual（D4 unlink 规则）
        if old_source == "inherited":
            asset.protection_level_source = "manual"
            return {"asset_id": str(asset.id), "changed": False, "old": old,
                    "new": old, "source": "manual", "event": "source_downgrade_kept_value"}
        return {"asset_id": str(asset.id), "changed": False, "old": old,
                "new": old, "source": old_source, "skipped": "no_links_manual"}

    if old_source == "manual" and not allow_manual:
        return {"asset_id": str(asset.id), "changed": False, "old": old,
                "new": old, "source": "manual", "skipped": "manual_protected"}

    # 就高传播：target 可能低于现值（另一更高系统被 unlink）——inherited 资产如实跟随
    asset.protection_level = target
    asset.protection_level_source = "inherited"
    changed = old != target
    return {"asset_id": str(asset.id), "changed": changed, "old": old,
            "new": target, "source": "inherited"}


def propagate_system_level_change(db: Session, system_id) -> dict:
    """系统等级变更后，批量重算其所有成员资产（D4：manual 跳过）。

    就高语义：资产可能另挂更高等级系统——逐资产 recompute 保证不被本系统降档拉低。
    返回 {system_id, affected, changed, details}。
    """
    asset_ids = [
        r[0] for r in
        db.query(AssetBusiness.asset_id)
        .filter(AssetBusiness.system_id == system_id)
        .all()
    ]
    details: List[dict] = []
    changed = 0
    for aid in asset_ids:
        result = recompute_asset(db, aid, allow_manual=False)
        details.append(result)
        if result.get("changed"):
            changed += 1
    return {"system_id": str(system_id), "affected": len(asset_ids),
            "changed": changed, "details": details}


def log_propagation_audit(db: Session, *, action: str, system_id,
                          current_user, result: dict) -> None:
    """传播结果作为一条汇总审计落 hash 链（设计 §5.2）——批量变更不游离在审计外。

    result 含 details 时截断（审计行不存全量明细，只存计数 + 变更项）。
    """
    from app.services.audit_log_service import AuditLogService
    changed_items = [
        {"asset_id": d["asset_id"], "old": d.get("old"), "new": d.get("new")}
        for d in result.get("details", []) if d.get("changed")
    ]
    summary = {
        "system_id": str(system_id),
        "affected": result.get("affected", 0),
        "changed": result.get("changed", len(changed_items)),
        "changed_items": changed_items[:50],  # 截断保护
    }
    svc = AuditLogService(db)
    svc.create_audit_log(
        user_id=getattr(current_user, "id", None) if current_user else None,
        username=getattr(current_user, "username", "system") if current_user else "system",
        action=action,
        resource_type="asset_protection_propagation",
        # resource_id 列是 BigInteger——UUID 存不进，system_id 放 new_values（summary）里
        resource_name=str(system_id),
        new_values=summary,
    )
