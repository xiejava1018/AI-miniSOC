#!/usr/bin/env python3
"""
初始化「行为检测」菜单（写入 soc_menus)

幂等：已存在则跳过。

用法:
    cd src/backend
    ../../venv/bin/python scripts/init_browsing_menu.py
"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.models.menu import Menu

# 父菜单
PARENT = {
    "name": "行为检测",
    "path": "/browsing",
    "icon": "ri:radar-line",
    "sort_order": 5,  # 紧跟告警管理
}

# 子菜单
CHILDREN = [
    {"name": "异常事件", "path": "event", "component": "/browsing/event/index", "sort_order": 1},
    {"name": "行为统计", "path": "statistics", "component": "/browsing/statistics/index", "sort_order": 2},
    {"name": "行为日志", "path": "logs", "component": "/browsing/logs/index", "sort_order": 3},
    {"name": "黑名单管理", "path": "blacklist", "component": "/browsing/blacklist/index", "sort_order": 4},
    {"name": "规则配置", "path": "config", "component": "/browsing/config/index", "sort_order": 5},
]


def main():
    db = SessionLocal()
    try:
        parent = db.query(Menu).filter(Menu.path == PARENT["path"]).first()
        if not parent:
            parent = Menu(**PARENT)
            db.add(parent)
            db.flush()
            print(f"✅ 新增父菜单 id={parent.id} {parent.name}")
        else:
            print(f"ℹ️  父菜单已存在 id={parent.id} {parent.name}")

        created = 0
        for child in CHILDREN:
            full_path = f"{PARENT['path']}/{child['path']}"
            exists = db.query(Menu).filter(Menu.path == child["path"], Menu.parent_id == parent.id).first()
            if exists:
                continue
            db.add(Menu(parent_id=parent.id, **child))
            created += 1

        # 给管理员角色授权新菜单（role_code=admin 的 role_menu）
        try:
            from app.models.role import Role
            from app.models.role_menu import RoleMenu
            admin = db.query(Role).filter(Role.code == "admin").first()
            if admin:
                # 收集所有 browsing 菜单 id
                browsing_menus = (
                    db.query(Menu)
                    .filter((Menu.path == "/browsing") | (Menu.parent_id == parent.id))
                    .all()
                )
                for m in browsing_menus:
                    exists = db.query(RoleMenu).filter(
                        RoleMenu.role_id == admin.id, RoleMenu.menu_id == m.id
                    ).first()
                    if not exists:
                        db.add(RoleMenu(role_id=admin.id, menu_id=m.id, permissions=[]))
        except Exception:
            print("⚠️  授权管理员失败（可手动在角色管理中分配）")

        db.commit()
        print(f"✅ 新增子菜单 {created} 条，菜单初始化完成")
        # 打印结果
        for m in db.query(Menu).filter(Menu.parent_id == parent.id).order_by(Menu.sort_order).all():
            print(f"   {m.name}: /browsing/{m.path} → {m.component}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
