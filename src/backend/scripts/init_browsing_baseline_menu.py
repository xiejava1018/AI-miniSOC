"""
行为基线查看页菜单初始化（一次性，幂等）

依据：docs/design/2026-08-16-行为基线查看页-执行工单.md T3
- soc_menus 插入 parent_id=22(行为检测) 子菜单 baseline
- 必须关联 admin 角色(id=1)，否则菜单树按 role 过滤后侧边栏不可见
"""
from app.core.database import SessionLocal
from app.models.menu import Menu
from app.models.role import Role

db = SessionLocal()

# 幂等检查
exists = db.query(Menu).filter(Menu.parent_id == 22, Menu.name == 'baseline').first()
if exists:
    print(f"已存在菜单 id={exists.id}，跳过插入")
    menu = exists
else:
    menu = Menu(
        parent_id=22,
        name='baseline',
        title='行为基线',
        path='baseline',
        component='/browsing/baseline/index',  # 必须与 views 文件路径严格一致
        icon='ri:git-branch-line',
        sort_order=6,
        is_visible=True,
    )
    db.add(menu)
    db.commit()
    print(f"已插入菜单 id={menu.id}")

# admin 角色关联（幂等）
admin = db.query(Role).filter(Role.id == 1).first()
if menu not in admin.menus:
    admin.menus.append(menu)
    db.commit()
    print(f"已关联 admin 角色(id=1)")
else:
    print("admin 角色已关联，跳过")

# 验证输出
row = db.query(Menu).filter(Menu.parent_id == 22, Menu.name == 'baseline').first()
print("\n=== 验证 ===")
print(f"菜单: id={row.id} parent={row.parent_id} name={row.name} title={row.title}")
print(f"component={row.component} path={row.path} icon={row.icon} sort={row.sort_order} visible={row.is_visible}")
linked = any(r.id == 1 for r in row.roles)
print(f"admin 角色关联: {linked}")

print("\n行为检测(id=22) 下全部子菜单:")
for m in db.query(Menu).filter(Menu.parent_id == 22).order_by(Menu.sort_order).all():
    admin_has = any(r.id == 1 for r in m.roles)
    print(f"  sort={m.sort_order} {m.name:12} {m.title or m.name:10} admin可见={admin_has}")
db.close()
