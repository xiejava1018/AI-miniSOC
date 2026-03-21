# src/backend/app/services/role_service.py
from typing import Tuple, List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.role import Role
from app.models.user import User
from app.models.menu import Menu
from app.schemas.role import RoleCreate, RoleUpdate


class RoleService:
    """角色服务层"""

    def __init__(self, db: Session):
        self.db = db

    def get_roles(
        self,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None
    ) -> Tuple[List[Role], int]:
        """
        获取角色列表

        Args:
            skip: 跳过记录数
            limit: 返回记录数
            search: 搜索关键词（名称或代码）

        Returns:
            (角色列表, 总数)
        """
        query = self.db.query(Role)

        if search:
            query = query.filter(
                (Role.name.ilike(f"%{search}%")) |
                (Role.code.ilike(f"%{search}%"))
            )

        total = query.count()
        roles = query.offset(skip).limit(limit).all()

        return roles, total

    def get_role_by_id(self, role_id: int) -> Role:
        """根据ID获取角色"""
        role = self.db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ValueError("角色不存在")
        return role

    def create_role(self, role_data: RoleCreate, creator_id: int) -> Role:
        """
        创建角色

        Args:
            role_data: 角色创建数据
            creator_id: 创建者ID

        Returns:
            创建的角色对象

        Raises:
            ValueError: 角色代码已存在
        """
        # 检查code唯一性
        existing = self.db.query(Role).filter(Role.code == role_data.code).first()
        if existing:
            raise ValueError("角色代码已存在")

        # 创建角色
        role = Role(
            name=role_data.name,
            code=role_data.code,
            description=role_data.description,
            is_system=False
        )
        self.db.add(role)
        self.db.flush()

        # 分配菜单权限
        if role_data.menu_ids:
            menus = self.db.query(Menu).filter(Menu.id.in_(role_data.menu_ids)).all()
            role.menus = menus

        self.db.commit()
        self.db.refresh(role)
        return role

    def update_role(self, role_id: int, role_data: RoleUpdate, updater_id: int) -> Role:
        """
        更新角色

        Args:
            role_id: 角色ID
            role_data: 更新数据
            updater_id: 更新者ID

        Returns:
            更新后的角色

        Raises:
            ValueError: 角色不存在或系统角色不能修改代码
        """
        role = self.get_role_by_id(role_id)

        # 系统角色不能修改code
        if role.is_system and hasattr(role_data, 'code') and role_data.code != role.code:
            raise ValueError("系统角色不能修改代码")

        # 更新字段
        if role_data.name:
            role.name = role_data.name
        if role_data.description is not None:
            role.description = role_data.description

        # 更新菜单权限
        if role_data.menu_ids is not None:
            menus = self.db.query(Menu).filter(Menu.id.in_(role_data.menu_ids)).all()
            role.menus = menus

        self.db.commit()
        self.db.refresh(role)
        return role

    def delete_role(self, role_id: int, deleter_id: int) -> None:
        """
        删除角色

        Args:
            role_id: 角色ID
            deleter_id: 删除者ID

        Raises:
            ValueError: 角色不存在、系统角色或正在被使用
        """
        role = self.get_role_by_id(role_id)

        # 系统角色不能删除
        if role.is_system:
            raise ValueError("系统角色不能删除")

        # 检查是否有用户使用
        user_count = self.db.query(User).filter(User.role_id == role_id).count()
        if user_count > 0:
            raise ValueError(f"该角色正在被 {user_count} 个用户使用，无法删除")

        self.db.delete(role)
        self.db.commit()

    def get_role_menus(self, role_id: int) -> List[Menu]:
        """获取角色的菜单列表"""
        role = self.get_role_by_id(role_id)
        return role.menus

    def assign_menus(self, role_id: int, menu_ids: List[int]) -> Role:
        """
        分配菜单权限

        Args:
            role_id: 角色ID
            menu_ids: 菜单ID列表

        Returns:
            更新后的角色
        """
        role = self.get_role_by_id(role_id)

        menus = self.db.query(Menu).filter(Menu.id.in_(menu_ids)).all()
        role.menus = menus

        self.db.commit()
        self.db.refresh(role)
        return role

    def get_role_users(self, role_id: int) -> List[User]:
        """获取使用该角色的用户列表"""
        role = self.get_role_by_id(role_id)
        return self.db.query(User).filter(User.role_id == role_id).all()
