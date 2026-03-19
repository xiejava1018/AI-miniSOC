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

# Import generate_random_password - will be implemented in Task 9
# For now, we'll use a placeholder
def generate_random_password(length: int = 12) -> str:
    """临时占位函数，将在Task 9中实现"""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


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

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        根据ID获取用户

        Args:
            user_id: 用户ID

        Returns:
            用户对象或None
        """
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """
        根据用户名获取用户

        Args:
            username: 用户名

        Returns:
            用户对象或None
        """
        return self.db.query(User).filter(User.username == username).first()

    def create_user(self, user_data: UserCreate, creator_id: int) -> User:
        """
        创建用户

        Args:
            user_data: 用户创建数据
            creator_id: 创建者ID

        Returns:
            创建的用户

        Raises:
            ValueError: 用户名或邮箱已存在
        """
        # 检查用户名唯一性
        if self.get_user_by_username(user_data.username):
            raise ValueError("用户名已存在")

        # 检查邮箱唯一性
        if user_data.email:
            existing = self.db.query(User).filter(User.email == user_data.email).first()
            if existing:
                raise ValueError("邮箱已被使用")

        # 创建用户
        user = User(
            username=user_data.username,
            password_hash=hash_password(user_data.password),
            email=user_data.email,
            full_name=user_data.full_name,
            phone=getattr(user_data, 'phone', None),
            department=getattr(user_data, 'department', None),
            role_id=user_data.role_id,
            status=UserStatus.ACTIVE
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        # 记录审计日志
        self.audit.log_action(
            user_id=creator_id,
            action="create_user",
            resource_type="user",
            resource_id=user.id,
            details=f"创建用户: {user.username}"
        )

        return user

    def update_user(
        self,
        user_id: int,
        user_data: UserUpdate,
        updater_id: int
    ) -> User:
        """
        更新用户

        Args:
            user_id: 用户ID
            user_data: 更新数据
            updater_id: 更新者ID

        Returns:
            更新后的用户

        Raises:
            ValueError: 用户不存在或邮箱已被使用
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("用户不存在")

        # 检查邮箱唯一性
        if user_data.email and user_data.email != user.email:
            existing = self.db.query(User).filter(
                and_(User.email == user_data.email, User.id != user_id)
            ).first()
            if existing:
                raise ValueError("邮箱已被使用")

        # 更新字段
        update_data_dict = user_data.model_dump(exclude_unset=True)
        for field, value in update_data_dict.items():
            setattr(user, field, value)

        self.db.commit()
        self.db.refresh(user)

        # 记录审计日志
        self.audit.log_action(
            user_id=updater_id,
            action="update_user",
            resource_type="user",
            resource_id=user.id,
            details=f"更新用户: {user.username}"
        )

        return user

    def delete_user(self, user_id: int, deleter_id: int) -> bool:
        """
        删除用户

        Args:
            user_id: 用户ID
            deleter_id: 删除者ID

        Returns:
            是否删除成功

        Raises:
            ValueError: 用户不存在或不能删除最后一个管理员
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("用户不存在")

        # 检查是否为最后一个管理员
        if user.is_admin:
            admin_count = self.db.query(User).join(User.role).filter(
                Role.code == "admin"
            ).count()
            if admin_count <= 1:
                raise ValueError("不能删除最后一个管理员")

        # 记录审计日志
        username = user.username
        self.audit.log_action(
            user_id=deleter_id,
            action="delete_user",
            resource_type="user",
            resource_id=user.id,
            details=f"删除用户: {username}"
        )

        self.db.delete(user)
        self.db.commit()

        return True

    def reset_password(
        self,
        user_id: int,
        admin_id: int,
        new_password: Optional[str] = None
    ) -> str:
        """
        重置用户密码

        Args:
            user_id: 用户ID
            admin_id: 管理员ID
            new_password: 新密码（None则自动生成）

        Returns:
            新密码
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("用户不存在")

        # 生成随机密码（如果未提供）
        if not new_password:
            new_password = generate_random_password()

        # 更新密码
        user.password_hash = hash_password(new_password)
        user.password_changed_at = datetime.now()
        user.failed_login_attempts = 0
        user.locked_until = None

        self.db.commit()

        # 记录审计日志
        self.audit.log_action(
            user_id=admin_id,
            action="reset_password",
            resource_type="user",
            resource_id=user.id,
            details=f"重置用户密码: {user.username}"
        )

        return new_password
