"""
概览仪表板 API

前缀 /dashboard：
  GET /dashboard/summary  -> 一次返回 KPI 六数 + Δ 环比 + 数据源健康 + 新鲜度
                              + 夜间摘要 + 待办 + AI 洞察（设计 §5.2 聚合接口）
  GET /dashboard/trend    -> 告警簇趋势（复用 AlertGroupSnapshotService.get_trend，
                              distinct 指纹口径，勿动该服务）

RBAC 裁剪（设计 §5.2）：summary 按当前用户角色可见的菜单 path 裁剪返回体——
无对应菜单权限的模块，其 KPI 键从返回体里**删除**（隐藏而非置灰）。
菜单 path 对照（实测 soc_menus 顶级路径）：
  告警=/alerts、事件=/incidents、脆弱性=/vulnerabilities、
  行为=/browsing、资产=/assets
"""

from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.menu import Menu
from app.models.role import Role
from app.models.user import User
from app.services.alert_group_snapshot_service import AlertGroupSnapshotService
from app.services.dashboard_service import DashboardService

router = APIRouter()

# 模块 -> 菜单 path 前缀 + 该模块管辖的返回体键
# 说明：ai_insight 挂在告警治理（/alerts）下；night_summary 为复合摘要，
#       各分项随所属模块裁剪；collector 纳管数随资产（/assets）走。
MODULE_MENU_KEYS = {
    "alert": {
        "menu": "/alerts",
        "kpi": {"active_alert_groups"},
        "top": {"ai_insight"},
        "night": {"new_alert_groups"},
    },
    "incident": {
        "menu": "/incidents",
        "kpi": {"open_incidents", "incidents_today"},
        "top": set(),
        "night": {"new_incidents"},
    },
    "vulnerab": {
        "menu": "/vulnerabilities",
        "kpi": {"high_vulns"},
        "top": set(),
        "night": set(),
    },
    "browsing": {
        "menu": "/browsing",
        "kpi": {"browsing_anomalies_24h"},
        "top": set(),
        "night": {"browsing_anomalies"},
    },
    "asset": {
        "menu": "/assets",
        "kpi": {"asset_coverage"},
        "top": set(),
        "night": set(),
        "health_collector": True,  # sources_health.collector 纳管数随资产权限走
    },
}

# 待办条目 id -> 所属模块（无对应菜单权限的待办同样隐藏）
TODO_MODULE = {
    "asset_coverage": "asset",
    "incident_backlog": "incident",
    "browsing_review": "browsing",
    "ai_coverage": "alert",
}


def _user_menu_paths(db: Session, current_user: User) -> Optional[Set[str]]:
    """当前用户可见的菜单 path 集合；None 表示全量（admin / superuser）。

    与菜单树"按角色过滤"（MenuService.get_menu_tree）同口径：
    角色直接分配的菜单 + 已分配菜单的子菜单。
    """
    if current_user.is_superuser or current_user.is_admin:
        return None
    if not current_user.role_id:
        return set()
    role = db.query(Role).filter(Role.id == current_user.role_id).first()
    if role is None:
        return set()
    assigned_ids = {m.id for m in role.menus}
    if not assigned_ids:
        return set()
    menus = db.query(Menu).all()
    parent_ids = {m.parent_id for m in menus if m.id in assigned_ids}
    visible = [
        m for m in menus
        if m.id in assigned_ids
        or (m.parent_id is not None and m.parent_id in parent_ids)
    ]
    return {m.path for m in visible}


def _apply_rbac(summary: dict, paths: Optional[Set[str]]) -> dict:
    """按可见菜单 path 裁剪 summary：被裁剪的键直接删除（隐藏而非置灰）。

    paths 为 None（admin）时原样返回。
    """
    if paths is None:
        return summary

    # 无权限模块集合
    hidden_modules = {
        mod for mod, cfg in MODULE_MENU_KEYS.items() if cfg["menu"] not in paths
    }

    # KPI 子键
    kpi = summary.get("kpi")
    if isinstance(kpi, dict) and "error" not in kpi:
        for mod in hidden_modules:
            for key in MODULE_MENU_KEYS[mod]["kpi"]:
                kpi.pop(key, None)

    # 顶层键（ai_insight 等）
    for mod in hidden_modules:
        for key in MODULE_MENU_KEYS[mod].get("top", set()):
            summary.pop(key, None)

    # 夜间摘要分项
    night = summary.get("night_summary")
    if isinstance(night, dict) and "error" not in night:
        for mod in hidden_modules:
            for key in MODULE_MENU_KEYS[mod].get("night", set()):
                night.pop(key, None)

    # collector 纳管数（资产模块）
    if "asset" in hidden_modules:
        health = summary.get("sources_health")
        if isinstance(health, dict):
            health.pop("collector", None)

    # 待办条目按所属模块过滤
    todos = summary.get("todos")
    if isinstance(todos, list):
        summary["todos"] = [
            t for t in todos if TODO_MODULE.get(t.get("id")) not in hidden_modules
        ]
    return summary


@router.get("/summary")
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """概览仪表板聚合数据（设计 §5.2：一个接口驱动五区块，按菜单权限裁剪）。"""
    summary = DashboardService(db).get_summary()
    paths = _user_menu_paths(db, current_user)
    return _apply_rbac(summary, paths)


@router.get("/trend")
async def get_dashboard_trend(
    days: int = Query(14, ge=1, le=90, description="趋势跨度（天）"),
    db: Session = Depends(get_db),
):
    """告警簇趋势（复用已修复口径的 AlertGroupSnapshotService.get_trend）。"""
    svc = AlertGroupSnapshotService(db)
    return svc.get_trend(days=days)
