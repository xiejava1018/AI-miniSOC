#!/usr/bin/env python3
"""
初始化系统数据
"""
import sys
import os

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import engine, SessionLocal
from app.models import User, Role, Menu, RoleMenu, Dict, SystemConfig
from app.core.security import get_password_hash


def init_system_configs(db: Session):
    """初始化系统配置（幂等）"""
    print("初始化系统配置...")

    config_items = [
        # 基础信息
        {"category": "general", "key": "system_name", "value": "AI-miniSOC", "value_type": "string", "description": "系统显示名称"},
        {"category": "general", "key": "system_logo", "value": "", "value_type": "string", "description": "系统 Logo URL"},
        {"category": "general", "key": "system_copyright", "value": "© 2026 AI-miniSOC", "value_type": "string", "description": "系统版权信息"},
        {"category": "general", "key": "system_description", "value": "AI-driven mini Security Operation Center", "value_type": "string", "description": "系统描述"},

        # 安全策略
        {"category": "security", "key": "password_min_length", "value": "8", "value_type": "number", "description": "密码最小长度"},
        {"category": "security", "key": "password_require_uppercase", "value": "true", "value_type": "boolean", "description": "密码必须包含大写字母"},
        {"category": "security", "key": "password_require_digit", "value": "true", "value_type": "boolean", "description": "密码必须包含数字"},
        {"category": "security", "key": "session_timeout_minutes", "value": "60", "value_type": "number", "description": "会话超时时间(分钟)"},
        {"category": "security", "key": "max_login_attempts", "value": "5", "value_type": "number", "description": "最大登录失败次数"},
        {"category": "security", "key": "lockout_duration_minutes", "value": "30", "value_type": "number", "description": "账户锁定时长(分钟)"},

        # 验证码
        {"category": "captcha", "key": "captcha_enabled", "value": "true", "value_type": "boolean", "description": "是否启用登录验证码"},
        {"category": "captcha", "key": "captcha_expire_seconds", "value": "300", "value_type": "number", "description": "验证码有效期(秒)"},

        # 同步
        {"category": "sync", "key": "wazuh_api_url", "value": "", "value_type": "string", "description": "Wazuh API 地址"},
        {"category": "sync", "key": "sync_interval_minutes", "value": "30", "value_type": "number", "description": "自动同步间隔(分钟)"},
    ]

    for item_data in config_items:
        existing = db.query(SystemConfig).filter(
            SystemConfig.category == item_data["category"],
            SystemConfig.key == item_data["key"],
        ).first()
        if not existing:
            item = SystemConfig(**item_data)
            db.add(item)
            print(f"  ✅ 创建系统配置: {item_data['category']}.{item_data['key']}")

    db.commit()
    print("系统配置初始化完成！")


def init_dicts(db: Session):
    """初始化字典数据"""
    print("初始化字典数据...")

    dict_items = [
        # 资产类型
        {"dict_type": "asset_type", "dict_code": "server", "dict_label": "服务器", "color": "primary", "sort_order": 1},
        {"dict_type": "asset_type", "dict_code": "workstation", "dict_label": "工作站", "color": "info", "sort_order": 2},
        {"dict_type": "asset_type", "dict_code": "network_device", "dict_label": "网络设备", "color": "warning", "sort_order": 3},
        {"dict_type": "asset_type", "dict_code": "security_device", "dict_label": "安全设备", "color": "danger", "sort_order": 4},
        {"dict_type": "asset_type", "dict_code": "other", "dict_label": "其他", "color": "info", "sort_order": 5},

        # 资产等级 / 重要性
        {"dict_type": "importance", "dict_code": "core", "dict_label": "核心", "color": "danger", "sort_order": 1},
        {"dict_type": "importance", "dict_code": "important", "dict_label": "重要", "color": "warning", "sort_order": 2},
        {"dict_type": "importance", "dict_code": "normal", "dict_label": "普通", "color": "info", "sort_order": 3},

        # 资产状态
        {"dict_type": "asset_status", "dict_code": "online", "dict_label": "在线", "color": "success", "sort_order": 1},
        {"dict_type": "asset_status", "dict_code": "offline", "dict_label": "离线", "color": "danger", "sort_order": 2},
        {"dict_type": "asset_status", "dict_code": "never_connected", "dict_label": "从未连接", "color": "info", "sort_order": 3},
        {"dict_type": "asset_status", "dict_code": "decommissioned", "dict_label": "已下线", "color": "info", "sort_order": 4},
        {"dict_type": "asset_status", "dict_code": "unknown", "dict_label": "未知", "color": "info", "sort_order": 5},

        # 网络区域（8 值方案，详见 docs/design/network-zone-redesign.md）
        # 历史 intranet/other 需合并生产环境的 soc_dict：合并逻辑见脚本末尾的 _migrate_dict_rows。
        {"dict_type": "network_zone", "dict_code": "public",      "dict_label": "公网区",   "color": "danger",  "sort_order": 1},
        {"dict_type": "network_zone", "dict_code": "dmz",         "dict_label": "DMZ",      "color": "warning", "sort_order": 2},
        {"dict_type": "network_zone", "dict_code": "production",  "dict_label": "生产内网",  "color": "primary", "sort_order": 3},
        {"dict_type": "network_zone", "dict_code": "office",      "dict_label": "办公网",    "color": "info",    "sort_order": 4},
        {"dict_type": "network_zone", "dict_code": "dev",         "dict_label": "开发测试网", "color": "info",    "sort_order": 5},
        {"dict_type": "network_zone", "dict_code": "management",  "dict_label": "管理网/带外","color": "info",    "sort_order": 6},
        {"dict_type": "network_zone", "dict_code": "isolated",    "dict_label": "隔离区",    "color": "danger",  "sort_order": 7},
        {"dict_type": "network_zone", "dict_code": "unknown",     "dict_label": "未分类",    "color": "info",    "sort_order": 8},

        # 数据来源
        {"dict_type": "data_source", "dict_code": "wazuh", "dict_label": "Wazuh", "color": "success", "sort_order": 1},
        {"dict_type": "data_source", "dict_code": "manual", "dict_label": "手动录入", "color": "info", "sort_order": 2},

        # 资产关键度（criticality）—— 4 级（决策1，2026-08-15）
        # 与 vulnerability_ai.CRITICALITY_SCORES 对齐：critical/high/medium/low
        # 存量 'normal' 已回填为 'medium'（scripts/backfill_vulnerability_contract.py）
        # 旧 3 级（core/important/normal）已废弃，回填脚本会清理存量字典项
        {"dict_type": "asset_criticality", "dict_code": "critical", "dict_label": "严重", "color": "danger", "sort_order": 1},
        {"dict_type": "asset_criticality", "dict_code": "high", "dict_label": "高", "color": "danger", "sort_order": 2},
        {"dict_type": "asset_criticality", "dict_code": "medium", "dict_label": "中", "color": "warning", "sort_order": 3},
        {"dict_type": "asset_criticality", "dict_code": "low", "dict_label": "低", "color": "info", "sort_order": 4},

        # 事件严重性（severity）—— 留给未来事件/告警前端用
        {"dict_type": "severity", "dict_code": "critical", "dict_label": "严重", "color": "danger", "sort_order": 1},
        {"dict_type": "severity", "dict_code": "high", "dict_label": "高", "color": "danger", "sort_order": 2},
        {"dict_type": "severity", "dict_code": "medium", "dict_label": "中", "color": "warning", "sort_order": 3},
        {"dict_type": "severity", "dict_code": "low", "dict_label": "低", "color": "info", "sort_order": 4},
    ]

    # === Step 1: 字典就地升级（必须先跑） ===
    # 如果有 intranet/other 行，直接改名 production/unknown。
    # flush 会把改名写进数据库（同一个事务），for 循环的 existing 查询就能看到。
    _migrate_network_zone_dict(db)
    db.flush()

    for item_data in dict_items:
        # 用原生 SQL INSERT ... ON CONFLICT DO NOTHING，避免 ORM session 缓存。
        # ON CONFLICT 处理 race：即使 _migrate 改名后的旧对象也在 session 里，新行会被丢弃。
        # 这同时避免我们额外调 expire_all 丢掉 _migrate 的内存修改。
        params = {
            "t": item_data["dict_type"],
            "c": item_data["dict_code"],
            "l": item_data["dict_label"],
            "col": item_data["color"],
            "s": item_data["sort_order"],
        }
        result = db.execute(text("""
            INSERT INTO soc_dicts
                (dict_type, dict_code, dict_label, color, sort_order, is_active, is_default, remark)
            VALUES (:t, :c, :l, :col, :s, true, false, null)
            ON CONFLICT (dict_type, dict_code) DO NOTHING
        """), params)
        if result.rowcount > 0:
            print(f"  ✅ 创建字典: {item_data['dict_type']} - {item_data['dict_label']}")

    db.commit()
    print("字典数据初始化完成！")


def _migrate_network_zone_dict(db: Session):
    """将历史 network_zone 字典行 intranet/other 合并为 production/unknown。

    背景：CLAUDE.md §0 + 2026-XX-XX 立项的 network_zone 8 值改造。

    顺序关键：必须在本函数主 for 循环之前调用——主循环会创建 production/unknown 两行
    (全新 dict_code)；如果 production/unknown 已经被旧 intranet/other 改名占用，
    主循环会撞 UniqueViolation。

    幂等：
      - 库里有 intranet 行 → 改名 production
      - 库里没 intranet 行但有 production 行 → 跳过（说明已跑过迁移）
      - 同上 for other/unknown

    顺带：重排所有 network_zone 字典行的 sort_order 为连续 1-8，避免 office(原 sort=3)
    和 production(改名后 sort=3) 顺序重叠造成前端下拉难看。
    """
    for old_code, new_label, new_color, new_sort in (
        ("intranet",   "生产内网",  "primary", 3),
        ("other",      "未分类",    "info",    8),
    ):
        old_row = db.query(Dict).filter(
            Dict.dict_type == "network_zone",
            Dict.dict_code == old_code,
        ).first()
        if not old_row:
            # 已经没有旧 code 可迁移（已跑过 or 从库就是新的）
            continue
        old_row.dict_code = {
            "intranet": "production",
            "other":    "unknown",
        }[old_code]
        old_row.dict_label = new_label
        old_row.color = new_color
        old_row.sort_order = new_sort
        print(f"  ♻️  合并字典: network_zone/{old_code} → {old_row.dict_code}")

    # 整理 sort_order 为 1-8 连续（独立于上块迁移逻辑，即使已跑过也会执行）
    # 用原生 SQL 避免 ORM session 缓存问题。
    _sort_orders = [
        ("public",     1),
        ("dmz",        2),
        ("production", 3),
        ("office",     4),
        ("management", 5),
        ("dev",        6),
        ("isolated",   7),
        ("unknown",    8),
    ]
    from sqlalchemy import text as _sql_text
    for code, sort in _sort_orders:
        db.execute(_sql_text(
            "UPDATE soc_dicts SET sort_order = :s "
            "WHERE dict_type = 'network_zone' AND dict_code = :c"
        ), {"s": sort, "c": code})
    db.flush()
    print(f"  ↕️  重排 sort_order 为 1-8 连续")


def init_roles(db: Session):
    """初始化角色"""
    print("初始化角色...")

    roles = [
        {"name": "管理员", "code": "admin", "description": "系统管理员，拥有所有权限", "is_system": True},
        {"name": "普通用户", "code": "user", "description": "普通用户，可使用业务功能", "is_system": True},
        {"name": "只读用户", "code": "readonly", "description": "只读用户，仅可查看数据", "is_system": True}
    ]

    for role_data in roles:
        existing = db.query(Role).filter(Role.code == role_data["code"]).first()
        if not existing:
            role = Role(**role_data)
            db.add(role)
            print(f"  ✅ 创建角色: {role_data['name']}")

    db.commit()
    print("角色初始化完成！")


def init_menus(db: Session):
    """初始化菜单"""
    print("初始化菜单...")

    # 业务菜单
    # 注：系统管理 path 早期为 ''（空 Layout 容器约定），
    # 但 menu 迁移（a0b1c2d3e4f5 等）/ 菜单 API 都按 path='/system' 定位父菜单，
    # 不一致会导致菜单种入迁移静默 0 行。已统一为 '/system'，
    # 历史 '' 行由 e2f3g4h5i6j7 兜底改写。
    menus = [
        {"name": "概览仪表板", "path": "/dashboard", "icon": "ri:bar-chart-box-line", "sort_order": 1, "is_visible": True},
        {"name": "资产管理", "path": "/assets", "icon": "ri:computer-line", "sort_order": 2, "is_visible": True},
        {"name": "事件管理", "path": "/incidents", "icon": "ri:alert-line", "sort_order": 3, "is_visible": True},
        {"name": "告警管理", "path": "/alerts", "icon": "ri:notification-3-line", "sort_order": 4, "is_visible": True},
        # T10（2026-08-15 脆弱性管理点亮）：新增一级菜单，排在告警之后、系统管理之前
        {"name": "脆弱性管理", "path": "/vulnerabilities", "icon": "ri:shield-check-line", "sort_order": 5, "is_visible": True},
        {"name": "系统管理", "path": "/system", "icon": "ri:settings-3-line", "sort_order": 6, "is_visible": True}
    ]

    for menu_data in menus:
        existing = db.query(Menu).filter(Menu.path == menu_data["path"], Menu.parent_id.is_(None)).first() if menu_data["path"] else db.query(Menu).filter(Menu.name == menu_data["name"], Menu.parent_id.is_(None)).first()
        if not existing:
            menu = Menu(**menu_data)
            db.add(menu)
            print(f"  ✅ 创建菜单: {menu_data['name']}")
        elif existing.sort_order != menu_data["sort_order"]:
            # 系统管理 5→6 等排序调整（幂等）
            existing.sort_order = menu_data["sort_order"]
            print(f"  ↻ 调整菜单排序: {menu_data['name']} → {menu_data['sort_order']}")

    db.commit()

    # 创建资产管理子菜单
    asset_menu = db.query(Menu).filter(Menu.name == "资产管理").first()
    if asset_menu:
        asset_sub_menus = [
            # 资产概览(2026-06-03 引入)放第一位作为高频入口
            {"parent_id": asset_menu.id, "name": "资产概览", "path": "overview", "icon": "ri:dashboard-2-line", "sort_order": 1, "is_visible": True, "component": "/asset/overview/index"},
            {"parent_id": asset_menu.id, "name": "资产列表", "path": "list", "icon": "ri:list-unordered", "sort_order": 2, "is_visible": True, "component": "/asset/list/index", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}, {"title": "Wazuh同步", "authMark": "sync"}]},
            {"parent_id": asset_menu.id, "name": "资产详情", "path": "detail/:id", "icon": "", "sort_order": 3, "is_visible": False, "component": "/asset/detail/index"}
        ]

        for menu_data in asset_sub_menus:
            existing = db.query(Menu).filter(Menu.path == menu_data["path"], Menu.parent_id == asset_menu.id).first()
            if not existing:
                menu = Menu(**menu_data)
                db.add(menu)
                print(f"  ✅ 创建资产管理子菜单: {menu_data['name']}")

    db.commit()

    # 创建脆弱性管理子菜单（T10，2026-08-15）
    vuln_menu = db.query(Menu).filter(Menu.name == "脆弱性管理", Menu.parent_id.is_(None)).first()
    if vuln_menu:
        vuln_sub_menus = [
            {"parent_id": vuln_menu.id, "name": "脆弱性概览", "path": "overview", "icon": "ri:dashboard-2-line", "sort_order": 1, "is_visible": True, "component": "/vulnerability/overview/index"},
            {"parent_id": vuln_menu.id, "name": "脆弱性列表", "path": "list", "icon": "ri:list-unordered", "sort_order": 2, "is_visible": True, "component": "/vulnerability/list/index", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "同步", "authMark": "sync"}, {"title": "修复状态更新", "authMark": "edit"}]}
        ]
        for menu_data in vuln_sub_menus:
            existing = db.query(Menu).filter(Menu.path == menu_data["path"], Menu.parent_id == vuln_menu.id).first()
            if not existing:
                menu = Menu(**menu_data)
                db.add(menu)
                print(f"  ✅ 创建脆弱性管理子菜单: {menu_data['name']}")

    db.commit()

    # 创建系统管理子菜单
    system_menu = db.query(Menu).filter(Menu.name == "系统管理").first()
    if system_menu:
        sub_menus = [
            {"parent_id": system_menu.id, "name": "用户管理", "path": "user", "icon": "ri:user-3-line", "sort_order": 1, "is_visible": True, "component": "/system/user", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]},
            {"parent_id": system_menu.id, "name": "角色管理", "path": "role", "icon": "ri:lock-line", "sort_order": 2, "is_visible": True, "component": "/system/role", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}, {"title": "分配权限", "authMark": "assign"}]},
            {"parent_id": system_menu.id, "name": "菜单管理", "path": "menu", "icon": "ri:menu-3-line", "sort_order": 3, "is_visible": True, "component": "/system/menu", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]},
            {"parent_id": system_menu.id, "name": "部门管理", "path": "department", "icon": "ri:building-2-line", "sort_order": 5, "is_visible": True, "component": "/system/department", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]},
            {"parent_id": system_menu.id, "name": "审计日志", "path": "audit-log", "icon": "ri:file-text-line", "sort_order": 4, "is_visible": True, "component": "/system/audit-log/index"},
            {"parent_id": system_menu.id, "name": "字典管理", "path": "dict", "icon": "ri:booklet-line", "sort_order": 6, "is_visible": True, "component": "/system/dict", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]},
            {"parent_id": system_menu.id, "name": "系统配置", "path": "system-config", "icon": "ri:settings-2-line", "sort_order": 7, "is_visible": True, "component": "/system/config", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]}
        ]

        for menu_data in sub_menus:
            existing = db.query(Menu).filter(Menu.path == menu_data["path"]).first()
            if not existing:
                menu = Menu(**menu_data)
                db.add(menu)
                print(f"  ✅ 创建系统管理子菜单: {menu_data['name']}")

    db.commit()
    print("菜单初始化完成！")


def init_admin_user(db: Session):
    """初始化管理员用户"""
    print("初始化管理员用户...")

    # 检查是否已存在admin用户
    existing = db.query(User).filter(User.username == "admin").first()
    if existing:
        print("  ⚠️  admin用户已存在，跳过创建")
        return existing

    # 获取管理员角色
    admin_role = db.query(Role).filter(Role.code == "admin").first()
    if not admin_role:
        print("  ❌ 错误：未找到管理员角色")
        return None

    # 创建管理员用户
    admin_user = User(
        username="admin",
        password_hash=get_password_hash("admin123"),
        email="admin@example.com",
        full_name="系统管理员",
        role_id=admin_role.id,
        is_superuser=True
    )

    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)

    print(f"  ✅ 创建管理员用户: admin / admin123")
    return admin_user


def assign_all_menus_to_admin(db: Session):
    """给管理员角色分配所有菜单权限"""
    print("给管理员角色分配菜单权限...")

    admin_role = db.query(Role).filter(Role.code == "admin").first()
    if not admin_role:
        print("  ❌ 错误：未找到管理员角色")
        return

    # 获取所有菜单
    all_menus = db.query(Menu).all()

    # 为管理员角色分配所有菜单
    for menu in all_menus:
        existing = db.query(RoleMenu).filter(
            RoleMenu.role_id == admin_role.id,
            RoleMenu.menu_id == menu.id
        ).first()

        if not existing:
            role_menu = RoleMenu(role_id=admin_role.id, menu_id=menu.id)
            db.add(role_menu)

    db.commit()
    print(f"  ✅ 已分配 {len(all_menus)} 个菜单权限给管理员角色")


def main():
    """主函数"""
    print("=== AI-miniSOC 系统数据初始化 ===\n")

    # 创建数据库会话
    db = SessionLocal()

    try:
        # 初始化字典数据
        init_dicts(db)

        # 初始化系统配置
        init_system_configs(db)

        # 初始化角色
        init_roles(db)

        # 初始化菜单
        init_menus(db)

        # 初始化管理员用户
        init_admin_user(db)

        # 给管理员分配所有菜单权限
        assign_all_menus_to_admin(db)

        print("\n✅ 系统数据初始化完成！")
        print("\n登录信息:")
        print("  用户名: admin")
        print("  密码: admin123")

    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
