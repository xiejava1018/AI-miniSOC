# src/backend/app/services/menu_service.py
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.menu import Menu


class MenuService:
    """菜单服务层"""

    def __init__(self, db: Session):
        self.db = db

    def get_menu_tree(self) -> List[Menu]:
        """
        获取菜单树

        Returns:
            树形结构的菜单列表
        """
        menus = self.db.query(Menu).filter(Menu.is_visible == True).all()
        return self._build_tree(menus)

    def _build_tree(self, menus: List[Menu]) -> List[Menu]:
        """构建树形结构"""
        menu_dict = {menu.id: menu for menu in menus}
        root_menus = []

        for menu in menus:
            if menu.parent_id is None:
                root_menus.append(menu)
            else:
                parent = menu_dict.get(menu.parent_id)
                if parent and hasattr(parent, 'children'):
                    parent.children.append(menu)

        # 排序
        for menu in root_menus:
            if hasattr(menu, 'children'):
                menu.children.sort(key=lambda x: x.sort_order or 0)

        return sorted(root_menus, key=lambda x: x.sort_order or 0)

    def get_menu_options(self) -> List[dict]:
        """
        获取菜单选项（用于下拉选择）

        Returns:
            扁平化的菜单列表，带parent_name
        """
        menus = self.db.query(Menu).order_by(Menu.sort_order).all()
        options = []

        for menu in menus:
            parent_name = ""
            if menu.parent_id:
                parent = self.db.query(Menu).filter(Menu.id == menu.parent_id).first()
                if parent:
                    parent_name = f"{parent.name} / "

            options.append({
                "id": menu.id,
                "name": f"{parent_name}{menu.name}",
                "path": menu.path
            })

        return options
