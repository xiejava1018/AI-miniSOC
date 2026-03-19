"""
UserService单元测试
"""

import pytest
from sqlalchemy.orm import Session

from app.services.user_service import UserService
from app.models.user import User, UserStatus


class TestUserService:
    """UserService测试类"""

    def test_user_service_initialization(self, db_session: Session):
        """
        测试UserService初始化

        Args:
            db_session: 测试数据库会话
        """
        # 创建UserService实例
        user_service = UserService(db_session)

        # 验证实例属性
        assert user_service.db is db_session
        assert user_service.audit is not None
        assert hasattr(user_service.audit, 'db')

    def test_get_users(self, db_session: Session, sample_users: list[User]):
        """测试获取用户列表"""
        service = UserService(db_session)
        users, total = service.get_users(skip=0, limit=10)

        assert total == len(sample_users)
        assert len(users) == min(10, len(sample_users))
        assert all(isinstance(u, User) for u in users)

    def test_get_users_with_search(self, db_session: Session, sample_users: list[User]):
        """测试搜索用户"""
        service = UserService(db_session)
        users, total = service.get_users(skip=0, limit=10, search="admin")

        assert total >= 0
        assert all("admin" in u.username.lower() for u in users)

    def test_get_users_with_filters(self, db_session: Session, sample_users: list[User]):
        """测试筛选用户"""
        service = UserService(db_session)
        users, total = service.get_users(
            skip=0,
            limit=10,
            role_id=1,
            status="active"
        )

        assert all(u.role_id == 1 for u in users)
        assert all(u.status == UserStatus.ACTIVE for u in users)
