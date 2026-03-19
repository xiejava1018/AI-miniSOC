"""
UserService单元测试
"""

import pytest
from sqlalchemy.orm import Session

from app.services.user_service import UserService
from app.models.user import User, UserStatus
from app.models.role import Role
from app.schemas.user import UserCreate


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

    def test_get_user_by_id(self, db_session: Session, sample_users: list[User]):
        """测试根据ID获取用户"""
        service = UserService(db_session)
        user = sample_users[0]

        found = service.get_user_by_id(user.id)
        assert found is not None
        assert found.id == user.id
        assert found.username == user.username

    def test_get_user_by_id_not_found(self, db_session: Session):
        """测试获取不存在的用户"""
        service = UserService(db_session)
        found = service.get_user_by_id(99999)
        assert found is None

    def test_get_user_by_username(self, db_session: Session, sample_users: list[User]):
        """测试根据用户名获取用户"""
        service = UserService(db_session)
        user = sample_users[0]

        found = service.get_user_by_username(user.username)
        assert found is not None
        assert found.username == user.username


def test_create_user_success(db_session: Session, sample_role: Role):
    """测试成功创建用户"""
    service = UserService(db_session)
    user_data = UserCreate(
        username="testuser",
        password="Test123456",
        email="test@example.com",
        full_name="测试用户",
        role_id=sample_role.id
    )

    user = service.create_user(user_data, creator_id=1)

    assert user.id is not None
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.role_id == sample_role.id
    assert user.status == UserStatus.ACTIVE


def test_create_user_duplicate_username(db_session: Session, sample_users: list[User]):
    """测试创建重复用户名"""
    service = UserService(db_session)
    existing_user = sample_users[0]

    user_data = UserCreate(
        username=existing_user.username,
        password="Test123456",
        role_id=existing_user.role_id
    )

    with pytest.raises(ValueError, match="用户名已存在"):
        service.create_user(user_data, creator_id=1)


def test_create_user_duplicate_email(db_session: Session, sample_role: Role):
    """测试创建重复邮箱"""
    service = UserService(db_session)

    # 先创建一个用户
    user_data1 = UserCreate(
        username="user1",
        password="Test123456",
        email="duplicate@example.com",
        role_id=sample_role.id
    )
    service.create_user(user_data1, creator_id=1)

    # 尝试创建相同邮箱的用户
    user_data2 = UserCreate(
        username="user2",
        password="Test123456",
        email="duplicate@example.com",
        role_id=sample_role.id
    )

    with pytest.raises(ValueError, match="邮箱已被使用"):
        service.create_user(user_data2, creator_id=1)
