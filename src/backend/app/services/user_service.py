"""
用户服务业务逻辑类
"""

from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from datetime import datetime, timedelta

from app.models.user import User, UserStatus
from app.models.role import Role
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import hash_password
from app.services.audit_service import AuditService


class UserService:
    """用户业务逻辑类"""

    def __init__(self, db: Session):
        """
        初始化UserService

        Args:
            db: 数据库会话
        """
        self.db = db
        self.audit = AuditService(db)

    def get_users(
        self,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        role_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> Tuple[List[User], int]:
        """
        获取用户列表

        Args:
            skip: 跳过数量
            limit: 限制数量
            search: 搜索关键词（用户名/邮箱/姓名）
            role_id: 角色ID筛选
            status: 状态筛选

        Returns:
            (用户列表, 总数)
        """
        query = self.db.query(User)

        # 搜索条件
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    User.username.ilike(search_pattern),
                    User.email.ilike(search_pattern),
                    User.full_name.ilike(search_pattern)
                )
            )

        # 角色筛选
        if role_id:
            query = query.filter(User.role_id == role_id)

        # 状态筛选
        if status:
            query = query.filter(User.status == status)

        # 总数
        total = query.count()

        # 分页
        users = query.offset(skip).limit(limit).all()

        return users, total
