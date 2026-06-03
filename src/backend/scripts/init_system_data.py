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

        # 网络区域
        {"dict_type": "network_zone", "dict_code": "intranet", "dict_label": "内网", "color": "primary", "sort_order": 1},
        {"dict_type": "network_zone", "dict_code": "dmz", "dict_label": "DMZ", "color": "warning", "sort_order": 2},
        {"dict_type": "network_zone", "dict_code": "office", "dict_label": "办公网", "color": "info", "sort_order": 3},
        {"dict_type": "network_zone", "dict_code": "management", "dict_label": "管理网", "color": "info", "sort_order": 4},
        {"dict_type": "network_zone", "dict_code": "other", "dict_label": "其他", "color": "info", "sort_order": 5},

        # 数据来源
        {"dict_type": "data_source", "dict_code": "wazuh", "dict_label": "Wazuh", "color": "success", "sort_order": 1},
        {"dict_type": "data_source", "dict_code": "manual", "dict_label": "手动录入", "color": "info", "sort_order": 2},

        # 资产重要性（criticality）—— 3 级
        # 与 severity 解耦: 严重性用于事件/告警/漏洞,重要性用于资产支撑业务的程度
        # dict_code 与 soc_assets.criticality 现存值一致 (core/important/normal)
        {"dict_type": "asset_criticality", "dict_code": "core", "dict_label": "核心", "color": "danger", "sort_order": 1},
        {"dict_type": "asset_criticality", "dict_code": "important", "dict_label": "重要", "color": "warning", "sort_order": 2},
        {"dict_type": "asset_criticality", "dict_code": "normal", "dict_label": "普通", "color": "info", "sort_order": 3},

        # 事件严重性（severity）—— 留给未来事件/告警前端用
        {"dict_type": "severity", "dict_code": "critical", "dict_label": "严重", "color": "danger", "sort_order": 1},
        {"dict_type": "severity", "dict_code": "high", "dict_label": "高", "color": "danger", "sort_order": 2},
        {"dict_type": "severity", "dict_code": "medium", "dict_label": "中", "color": "warning", "sort_order": 3},
        {"dict_type": "severity", "dict_code": "low", "dict_label": "低", "color": "info", "sort_order": 4},
    ]

    for item_data in dict_items:
        existing = db.query(Dict).filter(
            Dict.dict_type == item_data["dict_type"],
            Dict.dict_code == item_data["dict_code"],
        ).first()
        if not existing:
            item = Dict(**item_data)
            db.add(item)
            print(f"  ✅ 创建字典: {item_data['dict_type']} - {item_data['dict_label']}")

    db.commit()
    print("字典数据初始化完成！")


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
    menus = [
        {"name": "概览仪表板", "path": "/dashboard", "icon": "ri:bar-chart-box-line", "sort_order": 1, "is_visible": True},
        {"name": "资产管理", "path": "/assets", "icon": "ri:computer-line", "sort_order": 2, "is_visible": True},
        {"name": "事件管理", "path": "/incidents", "icon": "ri:alert-line", "sort_order": 3, "is_visible": True},
        {"name": "告警管理", "path": "/alerts", "icon": "ri:notification-3-line", "sort_order": 4, "is_visible": True},
        {"name": "系统管理", "path": "", "icon": "ri:settings-3-line", "sort_order": 5, "is_visible": True}
    ]

    for menu_data in menus:
        existing = db.query(Menu).filter(Menu.path == menu_data["path"]).first()
        if not existing:
            menu = Menu(**menu_data)
            db.add(menu)
            print(f"  ✅ 创建菜单: {menu_data['name']}")

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
