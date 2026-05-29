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
from app.models import User, Role, Menu, RoleMenu
from app.core.security import get_password_hash


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

    # 创建系统管理子菜单
    system_menu = db.query(Menu).filter(Menu.name == "系统管理").first()
    if system_menu:
        sub_menus = [
            {"parent_id": system_menu.id, "name": "用户管理", "path": "users", "icon": "ri:user-3-line", "sort_order": 1, "is_visible": True, "component": "/system/user", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]},
            {"parent_id": system_menu.id, "name": "角色管理", "path": "roles", "icon": "ri:lock-line", "sort_order": 2, "is_visible": True, "component": "/system/role", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}, {"title": "分配权限", "authMark": "assign"}]},
            {"parent_id": system_menu.id, "name": "菜单管理", "path": "menus", "icon": "ri:menu-3-line", "sort_order": 3, "is_visible": True, "component": "/system/menu", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]},
            {"parent_id": system_menu.id, "name": "部门管理", "path": "departments", "icon": "ri:building-2-line", "sort_order": 5, "is_visible": True, "component": "/system/department", "permissions": [{"title": "查看", "authMark": "view"}, {"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]},
            {"parent_id": system_menu.id, "name": "审计日志", "path": "audit-logs", "icon": "ri:file-text-line", "sort_order": 4, "is_visible": True, "component": "/system/audit"}]
        ]

        for menu_data in sub_menus:
            existing = db.query(Menu).filter(Menu.path == menu_data["path"]).first()
            if not existing:
                menu = Menu(**menu_data)
                db.add(menu)
                print(f"  ✅ 创建子菜单: {menu_data['name']}")

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
