"""menu_baseline — 补齐 11 个顶级菜单 + 61 行完整菜单树（空库首次部署必需）

背景（GitHub issue #12 · 2/3/4 条）：
`alembic upgrade head` 之后前端「所有页面 500」。根因不是前端 bug，而是
**菜单树从来没进过迁移链**——11 个顶级菜单 + 50 个子菜单在生产库是手工建的，
链上 90 个迁移里 0 处种顶级菜单。后果连锁：

1. 空库 upgrade head 在 y4z5a6b7c8d9 必挂（`parent_id=22` 硬编码，
   空库「行为分析」根本不存在 → FK violation）；
2. 就算绕过，前端 /api/v1/menus 返回空 → 动态路由一条都注册不上 →
   beforeEach 全部落到 `next({name:'Exception500'})` → 全站 500；
3. install.sh 也拿不到菜单。

本迁移一次性种入完整菜单树，作为**基线**（baseline）。
数据源 = 生产/测试库 soc_menus 实况（61 行），非手抄。

设计要点：
- **按 (parent_path, path) 定位父菜单，绝不硬编码 id**（CLAUDE.md §4.3 红线②）。
  空库与老库都能正确定位，且天然幂等。
- 排序：先父后子（parent_path 非空的排在后面），保证子菜单 INSERT 时父已存在。
- 幂等：`WHERE NOT EXISTS` + 同名同 path 跳过 → 已有菜单的库重跑零副作用，
  不会覆盖管理员在「菜单管理」页做过的调整（不 UPDATE，只补缺失）。
- 纯 SQL 字面量内联（非绑定参数）→ `alembic upgrade --sql` 离线 dry-run 可跑
  （CLAUDE.md §4.3 红线①）。值全为固定串/整数，无注入面。
- 后续各菜单迁移（y4z5a6b7c8d9 / c1d2e3f4g5h6 / …）在本基线之上做
  重命名/重排/授权，链序不变、行为不变。
- **链位**：紧跟建表基线 c5962ab1f662 —— 必须早于第一个按 id 定位父菜单的
  迁移（y4z5a6b7c8d9 用 `parent_id=22`），否则空库在那一迁移 FK violation 挂掉。

Revision ID: k0m1n2o3p4q5
Revises: c5962ab1f662
Create Date: 2026-10-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k0m1n2o3p4q5"
down_revision: Union[str, Sequence[str], None] = "c5962ab1f662"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (parent_path, name, title, path, icon, sort_order, is_visible, component, permissions)
# parent_path 为 NULL 表示顶级菜单。子菜单的 path 是相对名（'user'），
# 父菜单的 path 是绝对路径（'/system'）。
_MENUS = (
    (None, '概览仪表板', '概览仪表板', '/dashboard', 'ri:bar-chart-box-line', 1, True, '/dashboard/console', '[]'),
    (None, '资产管理', '资产管理', '/assets', 'ri:computer-line', 2, True, '/index/index', '[]'),
    (None, '脆弱性管理', '脆弱性管理', '/vulnerabilities', 'ri:shield-check-line', 3, True, None, '[]'),
    (None, '事件管理', '事件管理', '/incidents', 'ri:alert-line', 4, True, '/index/index', '[]'),
    (None, '告警管理', '告警管理', '/alerts', 'ri:notification-3-line', 5, True, '/index/index', '[]'),
    (None, '行为分析', '行为分析', '/browsing', 'ri:radar-line', 6, True, '/index/index', '[]'),
    (None, '安全报告', '安全报告', '/reports', 'ri:file-shield-2-line', 7, True, '', '[{"title": "查看", "authMark": "view"}, {"title": "生成报告", "authMark": "generate"}, {"title": "事件驱动检查", "authMark": "trigger"}]'),
    (None, 'scan', '资产扫描', '/scan', 'ri:scan-2-line', 8, True, '/index/index', '[{"title": "触发扫描", "authMark": "scan_run"}, {"title": "一键纳管/忽略", "authMark": "scan_finding_manage"}, {"title": "查看历史/发现", "authMark": "scan_view"}]'),
    (None, '配置中心', '配置中心', '/config', 'ri:settings-2-line', 9, True, '/index/index', '[]'),
    (None, '运维管理', '运维管理', '/ops', 'ri:tools-line', 10, True, '/index/index', '[]'),
    (None, '系统管理', '系统管理', '/system', 'ri:settings-3-line', 11, True, '/index/index', '[{"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]'),
    ('/alerts', 'alert-list', '告警列表', 'list', 'ri:file-list-3-line', 0, True, '/alert/list/index', '[]'),
    ('/alerts', 'alert-governance', '告警治理', 'governance', 'ri:filter-3-line', 1, True, '/alert/governance/index', '[]'),
    ('/alerts', 'ATT&CK 映射', 'ATT&CK 映射', 'attack-chain', 'ri:sword-line', 30, True, '/asset/attack-chain/index', '[{"title": "查看", "authMark": "view"}]'),
    ('/assets', '资产概览', None, 'overview', 'ri:dashboard-2-line', 1, True, '/asset/overview/index', '[]'),
    ('/assets', '资产列表', None, 'list', 'ri:list-unordered', 2, True, '/asset/list/index', '[]'),
    ('/assets', 'business-system', '业务系统', 'business-system', 'ri:briefcase-line', 3, True, '/asset/business-system/index', '[{"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]'),
    ('/assets', '资产详情', None, 'detail/:id', 'ri:information-line', 4, False, '/asset/detail/index', '[]'),
    ('/assets', '合规基线', '合规基线', 'compliance', 'ri:shield-check-line', 5, True, '/asset/compliance/index', '[{"title": "查看", "authMark": "view"}, {"title": "执行巡检", "authMark": "check"}, {"title": "AI 解读", "authMark": "interpret"}]'),
    ('/assets', '资产稽核', '资产稽核', 'reconciliation', 'ri:scales-3-line', 6, True, '/asset/reconciliation/index', '[{"title": "查看", "authMark": "view"}, {"title": "执行对账", "authMark": "reconcile"}, {"title": "处理差异", "authMark": "resolve"}, {"title": "AI 报告", "authMark": "report"}]'),
    ('/assets', '资产图谱', '资产图谱', 'graph', 'ri:share-circle-line', 7, True, '/asset/graph/index', '[{"title": "查看", "authMark": "view"}, {"title": "重建边", "authMark": "rebuild"}, {"title": "导出", "authMark": "export"}]'),
    ('/assets', 'exposure', '暴露面分析', 'exposure', 'ri:radar-line', 8, True, '/asset/exposure/index', '[]'),
    ('/assets', '图谱性能看板', '图谱性能看板', 'graph/perf-dashboard', 'ri:dashboard-2-line', 9, True, '/asset/graph/perf-dashboard/index', '[{"title": "查看", "authMark": "view"}, {"title": "重置采样", "authMark": "reset"}]'),
    ('/assets', '归属确认', '归属确认', 'attribution', 'ri:user-search-line', 10, True, '/asset/attribution-workbench/index', '[{"title": "查看", "authMark": "view"}, {"title": "裁决", "authMark": "resolve"}]'),
    ('/assets', '整改工单', '整改工单', 'remediation', 'ri:tools-line', 11, True, '/asset/remediation/index', '[{"title": "查看", "authMark": "view"}, {"title": "指派", "authMark": "assign"}, {"title": "流转", "authMark": "advance"}]'),
    ('/assets', '定级稽核', '定级稽核', 'rating-audit', 'ri:file-shield-2-line', 12, True, '/asset/rating-audit/index', '[{"title": "查看", "authMark": "view"}]'),
    ('/assets', '治理闭环', '治理闭环', 'governance-loop', 'ri:loop-left-line', 13, True, '/asset/governance-loop/index', '[{"title": "查看", "authMark": "view"}]'),
    ('/assets', '资产数字员工', '资产数字员工', 'agent-workbench', 'ri:robot-2-line', 14, True, '/asset/agent-workbench/index', '[{"title": "查看", "authMark": "view"}]'),
    ('/assets', '本体对齐', '本体对齐', 'ontology-view', 'ri:node-tree', 15, True, '/asset/ontology-view/index', '[{"title": "查看", "authMark": "view"}]'),
    ('/browsing', '行为统计', None, 'statistics', 'ri:bar-chart-grouped-line', 1, True, '/browsing/statistics/index', '[]'),
    ('/browsing', '行为画像', '行为画像', 'profile', 'ri:user-search-line', 2, True, '/browsing/profile/index', '[{"title": "实时刷新", "authMark": "refresh"}]'),
    ('/browsing', '异常事件', None, 'event', 'ri:eye-line', 3, True, '/browsing/event/index', '[]'),
    ('/browsing', '行为日志', None, 'logs', 'ri:file-search-line', 4, True, '/browsing/logs/index', '[]'),
    ('/browsing', 'baseline', '行为基线', 'baseline', 'ri:git-branch-line', 5, True, '/browsing/baseline/index', '[]'),
    ('/browsing', '黑名单管理', None, 'blacklist', 'ri:forbid-line', 6, True, '/browsing/blacklist/index', '[]'),
    ('/browsing', '规则配置', None, 'config', 'ri:settings-4-line', 7, True, '/browsing/config/index', '[]'),
    ('/browsing', '画像详情', '画像详情', 'profile/detail/:ip', 'ri:user-search-line', 9, False, '/browsing/profile/detail', '[]'),
    ('/config', 'configCenter', '配置管理', 'config-center', 'ri:equalizer-line', 1, True, '/system/config-center', '[{"title": "查看", "authMark": "view"}, {"title": "编辑", "authMark": "edit"}]'),
    ('/config', 'dataSource', '数据源管理', 'data-source', 'ri:database-2-line', 2, True, '/system/data-source', '[{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}, {"title": "连接测试", "authMark": "test"}]'),
    ('/config', 'aiProvider', 'AI 模型管理', 'ai-provider', 'ri:robot-2-line', 3, True, '/system/ai-provider', '[{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}, {"title": "连接测试", "authMark": "test"}]'),
    ('/incidents', 'incident-list', '事件列表', 'list', 'ri:file-list-3-line', 0, True, '/incidents/index', '[]'),
    ('/ops', 'TaskCenter', '任务中心', 'task-center', 'ri:list-check-2', 1, True, '/system/task-center/index', '[{"title": "查看", "authMark": "view"}, {"title": "手动触发", "authMark": "trigger"}, {"title": "取消", "authMark": "cancel"}, {"title": "启用/禁用", "authMark": "toggle"}, {"title": "查看历史", "authMark": "view_runs"}]'),
    ('/ops', '数据健康', '数据健康', 'data-health', 'ri:heart-pulse-line', 2, True, '/asset/data-health/index', '[{"title": "查看", "authMark": "view"}]'),
    ('/ops', '变更影响分析', '变更影响分析', 'impact-analysis', 'ri:flow-chart', 3, True, '/asset/impact-analysis/index', '[{"title": "查看", "authMark": "view"}, {"title": "发起分析", "authMark": "analyze"}]'),
    ('/ops', '知识库', '知识库', 'knowledge', 'ri:book-2-line', 4, True, '/knowledge/list/index', '[{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "验证", "authMark": "validate"}, {"title": "AI 提取", "authMark": "auto_extract"}]'),
    ('/reports', '报告列表', '报告列表', 'list', 'ri:file-list-2-line', 10, True, '/reports/list/index', '[{"title": "查看", "authMark": "view"}, {"title": "生成报告", "authMark": "generate"}, {"title": "事件驱动检查", "authMark": "trigger"}]'),
    ('/scan', 'scanners', '扫描器', 'scanners', 'ri:cpu-line', 1, True, '/scan/scanners/index', '[{"title": "查看", "authMark": "scan_view"}, {"title": "注册/编辑/注销", "authMark": "scanner_manage"}]'),
    ('/scan', 'tasks', '扫描任务', 'tasks', 'ri:list-check-2', 2, True, '/scan/tasks/index', '[{"title": "查看", "authMark": "scan_view"}, {"title": "触发/取消扫描", "authMark": "scan_run"}]'),
    ('/scan', 'findings', '发现清单', 'findings', 'ri:search-eye-line', 3, True, '/scan/findings/index', '[{"title": "查看", "authMark": "scan_view"}, {"title": "一键纳管/忽略", "authMark": "scan_finding_manage"}]'),
    ('/system', '用户管理', None, 'user', 'ri:user-3-line', 1, True, '/system/user', '[]'),
    ('/system', '角色管理', None, 'role', 'ri:lock-line', 2, True, '/system/role', '[]'),
    ('/system', '部门管理', None, 'department', 'ri:building-2-line', 3, True, '/system/department', '[{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]'),
    ('/system', '菜单管理', None, 'menu', 'ri:menu-3-line', 4, True, '/system/menu', '[]'),
    ('/system', '字典管理', None, 'dict', 'ri:booklet-line', 5, True, '/system/dict/index', '[{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]'),
    ('/system', '系统配置', '系统配置', 'system-config', 'ri:settings-2-line', 6, True, '/system/config/index', '[{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]'),
    ('/system', '审计日志', None, 'audit-log', 'ri:file-text-line', 7, True, '/system/audit-log/index', '[]'),
    ('/system', 'notificationChannels', '通知通道', 'notification-channels', 'ri:mail-line', 8, True, '/system/notification-channels', '[{"title": "查看", "authMark": "view"}]'),
    ('/system', 'notificationPrefs', '通知偏好', 'notification-preferences', 'ri:notification-3-line', 9, True, '/system/notification-preferences', '[{"title": "查看", "authMark": "view"}]'),
    ('/system', 'notificationDispatchLogs', '投递日志', 'notification-dispatch-logs', 'ri:file-list-3-line', 10, True, '/system/notification-dispatch-logs', '[{"title": "查看", "authMark": "view"}]'),
    ('/vulnerabilities', '脆弱性概览', None, 'overview', 'ri:dashboard-2-line', 1, True, '/vulnerability/overview/index', '[]'),
    ('/vulnerabilities', '脆弱性列表', None, 'list', 'ri:list-unordered', 2, True, '/vulnerability/list/index', '[{"title": "查看", "authMark": "view"}, {"title": "同步", "authMark": "sync"}, {"title": "修复状态更新", "authMark": "edit"}]')
)


def _q(value) -> str:
    """把 Python 值渲染成 SQL 字面量（NULL / 数字 / TRUE / 带引号转义的串）。

    注意：op.execute 会把字符串里的 ``:name`` 当 SQLAlchemy 绑定参数。
    菜单 path 存在路由参数（``detail/:id``），所以所有字面量里的 ``:``
    必须转义成 ``\\:``，否则报 "A value is required for bind parameter 'id'"。
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''").replace(":", "\\:") + "'"


# 子菜单：父菜单按 path 反查（绝不硬编码 id），(父 path + 自身 path) 判重幂等
_INSERT_CHILD = """
INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order,
                       is_visible, component, permissions)
SELECT p.id, {name}, {title}, {path}, {icon}, {sort_order},
       {is_visible}, {component}, CAST({permissions} AS jsonb)
FROM soc_menus p
WHERE p.path = {parent_path} AND p.parent_id IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM soc_menus m
      WHERE m.parent_id = p.id AND m.path = {path}
  )
"""

# 顶级菜单：按 (path, parent_id IS NULL) 判重幂等
_INSERT_ROOT = """
INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order,
                       is_visible, component, permissions)
SELECT NULL, {name}, {title}, {path}, {icon}, {sort_order},
       {is_visible}, {component}, CAST({permissions} AS jsonb)
WHERE NOT EXISTS (
    SELECT 1 FROM soc_menus WHERE path = {path} AND parent_id IS NULL
)
"""


def upgrade() -> None:
    # _MENUS 已按 (parent_path, sort_order) 排序：顶级在前、子菜单在后，
    # 保证子菜单 INSERT 时其父菜单已存在。
    #
    # 字面量内联而非绑定参数：alembic 离线模式（--sql）不会绑定运行期参数，
    # 会把 :name/:path 渲染成 NULL（WHERE path = NULL 永不匹配），
    # 且真在离线模式执行会写空值。值全为固定串/整数，无注入面。
    # （同 c1d2e3f4g5h6 的处理，CLAUDE.md §4.3 红线①）
    for parent_path, name, title, path, icon, sort_order, is_visible, component, permissions in _MENUS:
        fields = {
            "parent_path": _q(parent_path),
            "name": _q(name),
            "title": _q(title),
            "path": _q(path),
            "icon": _q(icon),
            "sort_order": _q(sort_order),
            "is_visible": _q(is_visible),
            "component": _q(component),
            "permissions": _q(permissions),
        }
        template = _INSERT_ROOT if parent_path is None else _INSERT_CHILD
        op.execute(template.format(**fields))


def downgrade() -> None:
    # 本基线只补缺失、不 UPDATE 已有行，故 downgrade 不删任何行：
    # 删掉会连带后续迁移写入的授权与管理员在「菜单管理」页的调整。
    # 空库回滚到 base 由 `alembic downgrade base` 的 drop_all 语义兜底。
    pass
