"""菜单补齐 + 行数断言（根治 2026-11-10 生产事故）

事故背景
--------
生产库（192.168.0.102 / AI-miniSOC-db）上「图谱性能看板」「归属确认」
「整改工单」三个子菜单缺失，但 alembic_version 与 dev 完全一致（都是
head）。排查结论：

  1. 三个菜单种子迁移（b6c7d8e9f0a1 / e9f0a1b2c3d4 / g3b4c5d6e7f8）
     用的是 ``INSERT INTO soc_menus (...) SELECT p.id, ... FROM soc_menus p
     WHERE p.path = '/assets' AND p.parent_id IS NULL``。
     **INSERT...SELECT 在源查询返回 0 行时静默插入 0 行且不报错**
     （CLAUDE.md §4.3 红线 2：「不存在时静默 0 行」）。
  2. 生产库的 schema 是手工建的（2026-06 起逐批手工补菜单），
     随后用 ``alembic stamp head`` 一次性把全部迁移标成「已应用」。
     stamp 不执行任何迁移体 → 那三个 INSERT **从未在生产库上执行过**。
     建表的 DDL 同理被跳过，但 soc_attribution_reviews /
     soc_remediation_tickets / soc_graph_perf_alerts 这几张表后来被
     其他迁移补建，所以呈现「表在、菜单不在」的诡异状态。
  3. CLAUDE.md §4.3 红线 6 已经预警过：「生产库能用只因 schema 是手工建的，
     **不代表迁移链完整**」。本次事故是该预警的第二次应验。

本迁移做什么
------------
把 /assets 下的**全部**子菜单作为一份显式清单重新播种一遍（幂等），
并在每一步之后**断言实际影响行数**：

  - 菜单已存在 → 插入 0 行，这是合法的「幂等跳过」
  - 菜单不存在 → 必须插入 1 行
  - 若插入 0 行但目标菜单并不存在 → **raise 异常，事务回滚**

这样「静默 0 行」变成「响亮失败」，杜绝同类事故再次无声发生。

同时把父菜单定位从「path + parent_id IS NULL」改成**带断言的显式校验**，
父菜单缺失时立即报错而不是静默跳过。

为什么不直接改那三个旧迁移
--------------------------
旧迁移已在生产库被 stamp 跳过，改它们对生产库无效（也不会重跑），
且会破坏迁移链的不可变性（已发布的迁移文件不应修改）。新迁移挂在
当前唯一 head 下游，是唯一安全的补齐方式。

幂等性
------
- 菜单插入用 ``NOT EXISTS`` 守卫（parent_id + path 唯一判定）
- 角色授权用 ``NOT EXISTS`` 守卫（role_id + menu_id 唯一判定）
- 重复执行本迁移 = 全部跳过 + 断言通过 = 无副作用

依据
----
- CLAUDE.md §4.3 红线 2：禁硬编码 id，业务种子必须 JOIN 菜单/角色表
- CLAUDE.md §4.3 红线 4：JSONB 用 CAST(:x AS jsonb)
- CLAUDE.md §4.3 红线 6：空库 upgrade head 必须能跑通
- CLAUDE.md §4.4：icon 必须 iconify ri:* 格式且真实存在
- CLAUDE.md §1.3：子菜单须自身被授权，父菜单只是容器

Revision ID: m1n2o3p4q5r7
Revises: f4a5b6c7d8e9
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m1n2o3p4q5r7"
down_revision: Union[str, Sequence[str], None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --------------------------------------------------------------------------
# /assets 子菜单全量清单
#   (path, name, title, icon, sort_order, component, menu_permissions, role_perms)
#   role_perms: {角色 code: [authMark, ...]}
#
# 清单来源：k0m1n2o3p4q5_menu_baseline（基础树）
#         + b6c7d8e9f0a1 / e9f0a1b2c3d4 / g3b4c5d6e7f8（三个曾被跳过的种子）
#         + 其余历史菜单迁移（定级稽核 / 治理闭环 / 资产数字员工 / 本体对齐 /
#           exposure / business-system / graph / 资产列表 / 资产详情 /
#           资产概览 / 合规基线 / 资产稽核）
# --------------------------------------------------------------------------
_ASSET_MENUS: list[tuple[str, str, str, str, int, str, str, dict[str, list[str]]]] = [
    # (path, name, title, icon, sort_order, component, menu_perms, role_perms)
    (
        "overview", "资产概览", "资产概览", "ri:pie-chart-2-line", 1,
        "/asset/overview/index", "[]",
        {"admin": [], "operator": [], "viewer": [], "auditor": []},
    ),
    (
        "list", "资产列表", None, "ri:list-unordered", 2,
        "/asset/list/index", "[]",
        {"admin": [], "operator": [], "viewer": [], "auditor": []},
    ),
    (
        "business-system", "business-system", "业务系统", "ri:briefcase-line", 3,
        "/asset/business-system/index",
        '[{"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"},'
        ' {"title": "删除", "authMark": "delete"}]',
        {"admin": ["add", "edit", "delete"], "operator": ["add", "edit", "delete"],
         "viewer": [], "auditor": []},
    ),
    (
        # is_visible=False：详情页是列表点进来的，不占菜单位
        "detail/:id", "资产详情", None, "ri:information-line", 4,
        "/asset/detail/index", "[]",
        {"admin": [], "operator": [], "viewer": [], "auditor": []},
    ),
    (
        "compliance", "合规基线", "合规基线", "ri:shield-check-line", 5,
        "/asset/compliance/index",
        '[{"title": "查看", "authMark": "view"}, {"title": "执行巡检", "authMark": "check"}]',
        {"admin": ["view", "check"], "operator": ["view", "check"],
         "viewer": ["view"], "auditor": ["view"]},
    ),
    (
        "reconciliation", "资产稽核", "资产稽核", "ri:search-eye-line", 6,
        "/asset/reconciliation/index",
        '[{"title": "查看", "authMark": "view"}]',
        {"admin": ["view"], "operator": ["view"], "viewer": ["view"], "auditor": ["view"]},
    ),
    (
        "graph", "资产图谱", "资产图谱", "ri:git-branch-line", 7,
        "/asset/graph/index",
        '[{"title": "查看", "authMark": "view"}]',
        {"admin": ["view"], "operator": ["view"], "viewer": ["view"], "auditor": ["view"]},
    ),
    (
        "exposure", "exposure", "暴露面", "ri:eye-line", 8,
        "/asset/exposure/index",
        '[{"title": "查看", "authMark": "view"}]',
        {"admin": ["view"], "operator": ["view"], "viewer": ["view"], "auditor": ["view"]},
    ),
    (
        # ↓↓↓ 本次事故的三个缺失菜单 ↓↓↓
        "graph/perf-dashboard", "图谱性能看板", "图谱性能看板", "ri:dashboard-2-line", 9,
        "/asset/graph/perf-dashboard/index",
        '[{"title": "查看", "authMark": "view"}, {"title": "重置采样", "authMark": "reset"}]',
        {"admin": ["view", "reset"], "operator": ["view"], "viewer": ["view"], "auditor": ["view"]},
    ),
    (
        "attribution", "归属确认", "归属确认", "ri:user-search-line", 10,
        "/asset/attribution-workbench/index",
        '[{"title": "查看", "authMark": "view"}, {"title": "裁决", "authMark": "resolve"}]',
        {"admin": ["view", "resolve"], "operator": ["view", "resolve"],
         "viewer": ["view"], "auditor": ["view"]},
    ),
    (
        "remediation", "整改工单", "整改工单", "ri:tools-line", 11,
        "/asset/remediation/index",
        '[{"title": "查看", "authMark": "view"}, {"title": "指派", "authMark": "assign"},'
        ' {"title": "流转", "authMark": "advance"}]',
        {"admin": ["view", "assign", "advance"], "operator": ["view", "assign", "advance"],
         "viewer": ["view"], "auditor": ["view"]},
    ),
    (
        # ↑↑↑ 本次事故的三个缺失菜单 ↑↑↑
        "rating-audit", "定级稽核", "定级稽核", "ri:bar-chart-box-line", 12,
        "/asset/rating-audit/index",
        '[{"title": "查看", "authMark": "view"}]',
        {"admin": ["view"], "operator": ["view"], "viewer": ["view"], "auditor": ["view"]},
    ),
    (
        "governance-loop", "治理闭环", "治理闭环", "ri:loop-right-line", 13,
        "/asset/governance-loop/index",
        '[{"title": "查看", "authMark": "view"}]',
        {"admin": ["view"], "operator": ["view"], "viewer": ["view"], "auditor": ["view"]},
    ),
    (
        "agent-workbench", "资产数字员工", "资产数字员工", "ri:robot-2-line", 14,
        "/asset/agent-workbench/index",
        '[{"title": "查看", "authMark": "view"}]',
        {"admin": ["view"], "operator": ["view"], "viewer": ["view"], "auditor": ["view"]},
    ),
    (
        "ontology-view", "本体对齐", "本体对齐", "ri:node-tree", 15,
        "/asset/ontology-view/index",
        '[{"title": "查看", "authMark": "view"}]',
        {"admin": ["view"], "operator": ["view"], "viewer": ["view"], "auditor": ["view"]},
    ),
]

_X1_ROLE_CODES = ("admin", "operator", "viewer", "auditor")


def _assert_parent_menu(bind) -> int:
    """定位 /assets 顶级菜单，找不到直接 raise（绝不静默跳过）。"""
    row = bind.execute(
        sa.text(
            "SELECT id FROM soc_menus "
            "WHERE path = '/assets' AND parent_id IS NULL "
            "ORDER BY id LIMIT 1"
        )
    ).fetchone()
    if row is None:
        raise RuntimeError(
            "菜单补齐失败：顶级菜单 /assets 不存在。"
            "请先执行 k0m1n2o3p4q5_menu_baseline（空库菜单树基线）。"
        )
    return int(row[0])


def _menu_exists(bind, parent_id: int, path: str) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM soc_menus WHERE parent_id = :pid AND path = :path LIMIT 1"
        ),
        {"pid": parent_id, "path": path},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    parent_id = _assert_parent_menu(bind)

    for (
        path, name, title, icon, sort_order, component, menu_perms, role_perms
    ) in _ASSET_MENUS:
        # ---- 1) 菜单本体（幂等插入）----
        result = bind.execute(
            sa.text(
                "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
                "  is_visible, component, permissions) "
                "SELECT :pid, :name, :title, :path, :icon, :sort_order, "
                "  TRUE, :component, CAST(:perms AS jsonb) "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM soc_menus WHERE parent_id = :pid AND path = :path)"
            ),
            {
                "pid": parent_id,
                "name": name,
                "title": title,
                "path": path,
                "icon": icon,
                "sort_order": sort_order,
                "component": component,
                "perms": menu_perms,
            },
        )

        # ---- 2) 断言：要么幂等跳过(0 行且已存在)，要么插入 1 行 ----
        inserted = result.rowcount
        exists = _menu_exists(bind, parent_id, path)
        if inserted == 0 and not exists:
            # 这是「静默 0 行」的危险形态 —— 事务必须失败，不能放过
            raise RuntimeError(
                f"菜单补齐失败：path={path!r} 插入 0 行且菜单不存在。"
                "疑似 INSERT...SELECT 源查询为空（父菜单/字段不匹配）。"
            )
        if inserted > 1:
            raise RuntimeError(
                f"菜单补齐异常：path={path!r} 插入了 {inserted} 行，期望最多 1 行"
            )

        # ---- 3) 角色授权（幂等插入）----
        for role_code in _X1_ROLE_CODES:
            marks = role_perms.get(role_code, [])
            perms_json = "[" + ", ".join(f'"{m}"' for m in marks) + "]"
            bind.execute(
                sa.text(
                    "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
                    "SELECT r.id, m.id, CAST(:perms AS jsonb) "
                    "FROM soc_roles r "
                    "JOIN soc_menus m ON m.parent_id = :pid AND m.path = :path "
                    "WHERE r.code = :code "
                    "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
                    "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"
                ),
                {
                    "pid": parent_id,
                    "path": path,
                    "code": role_code,
                    "perms": perms_json,
                },
            )

    # ---- 4) 终态断言：清单里每个菜单都必须存在 ----
    missing = [
        path for (path, *_rest) in _ASSET_MENUS
        if not _menu_exists(bind, parent_id, path)
    ]
    if missing:
        raise RuntimeError(f"菜单补齐终态断言失败，以下菜单仍缺失：{missing}")

    # ---- 5) 终态断言：每个菜单 × 每个 X1 角色都必须有授权 ----
    #      角色不存在（如历史库缺 auditor）不算失败 —— 那不是本迁移的职责，
    #      但已存在的角色必须有授权行，否则说明授权插入被静默跳过。
    bad_pairs = bind.execute(
        sa.text(
            "SELECT m.path, r.code FROM soc_menus m "
            "CROSS JOIN soc_roles r "
            "WHERE m.parent_id = :pid "
            "  AND m.path = ANY(:paths) "
            "  AND r.code = ANY(:codes) "
            "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
            "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"
        ),
        {
            "pid": parent_id,
            "paths": [m[0] for m in _ASSET_MENUS],
            "codes": list(_X1_ROLE_CODES),
        },
    ).fetchall()
    if bad_pairs:
        raise RuntimeError(
            "菜单授权终态断言失败，以下 (菜单, 角色) 组合缺少授权："
            f"{[(p, c) for p, c in bad_pairs]}"
        )


def downgrade() -> None:
    """回滚只删本迁移新增的三个菜单 + 其授权。

    ⚠️ 不删 /assets 下其余 12 个菜单 —— 它们由各自的原始迁移负责，
    本迁移只是幂等补齐，downgrade 时无法区分「本来就有的」和
    「本迁移补的」，误删会破坏生产菜单树。

    实现方式：只删这三个菜单路径 + 对应 role_menus，
    删完后立刻断言「菜单数 == 12」，数量不对就 raise。
    """
    bind = op.get_bind()
    parent_id = _assert_parent_menu(bind)

    target_paths = ["graph/perf-dashboard", "attribution", "remediation"]
    baseline_count = len(_ASSET_MENUS) - len(target_paths)

    # 先删授权（自下而上，避免孤儿）
    bind.execute(
        sa.text(
            "DELETE FROM soc_role_menus rm USING soc_menus m "
            "WHERE rm.menu_id = m.id AND m.parent_id = :pid AND m.path = ANY(:paths)"
        ),
        {"pid": parent_id, "paths": target_paths},
    )
    # 再删菜单
    bind.execute(
        sa.text(
            "DELETE FROM soc_menus "
            "WHERE parent_id = :pid AND path = ANY(:paths)"
        ),
        {"pid": parent_id, "paths": target_paths},
    )

    remaining = bind.execute(
        sa.text("SELECT count(*) FROM soc_menus WHERE parent_id = :pid"),
        {"pid": parent_id},
    ).scalar()
    if remaining != baseline_count:
        raise RuntimeError(
            f"downgrade 终态断言失败：/assets 子菜单数 = {remaining}，"
            f"期望 {baseline_count}"
        )
