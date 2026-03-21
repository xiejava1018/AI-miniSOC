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
        menus = self.get_all_menus()
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

    def get_all_menus(self) -> List[Menu]:
        """获取所有菜单（平铺）"""
        return self.db.query(Menu).order_by(Menu.sort_order).all()

    def get_menu_by_id(self, menu_id: int) -> Menu:
        """根据ID获取菜单"""
        menu = self.db.query(Menu).filter(Menu.id == menu_id).first()
        if not menu:
            raise ValueError("菜单不存在")
        return menu

    def create_menu(self, menu_data) -> Menu:
        """
        创建菜单

        Args:
            menu_data: MenuCreate schema

        Returns:
            创建的菜单对象
        """
        menu = Menu(
            name=menu_data.name,
            path=menu_data.path,
            icon=menu_data.icon,
            parent_id=menu_data.parent_id,
            sort_order=menu_data.sort_order,
            is_visible=menu_data.is_visible
        )
        self.db.add(menu)
        self.db.commit()
        self.db.refresh(menu)
        return menu

    def update_menu(self, menu_id: int, menu_data) -> Menu:
        """
        更新菜单

        Args:
            menu_id: 菜单ID
            menu_data: MenuUpdate schema

        Returns:
            更新后的菜单

        Raises:
            ValueError: 菜单不存在或防止循环引用
        """
        menu = self.get_menu_by_id(menu_id)

        # 防止循环引用
        if menu_data.parent_id:
            if menu_data.parent_id == menu_id:
                raise ValueError("不能将自己设为父菜单")

        # 更新字段
        update_data = menu_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(menu, field, value)

        self.db.commit()
        self.db.refresh(menu)
        return menu

    def delete_menu(self, menu_id: int) -> None:
        """
        删除菜单

        Args:
            menu_id: 菜单ID

        Raises:
            ValueError: 菜单不存在或有子菜单
        """
        menu = self.get_menu_by_id(menu_id)

        # 检查是否有子菜单
        child_count = self.db.query(Menu).filter(Menu.parent_id == menu_id).count()
        if child_count > 0:
            raise ValueError(f"该菜单有 {child_count} 个子菜单，无法删除")

        self.db.delete(menu)
        self.db.commit()
