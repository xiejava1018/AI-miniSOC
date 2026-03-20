"""
测试配置和共享fixtures
"""

import pytest
from sqlalchemy.orm import Session
from typing import Generator
from fastapi.testclient import TestClient

from app.core.database import Base, get_db
from app.models.user import User, UserStatus
from app.models.role import Role
from app.main import app


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """
    创建测试数据库会话

    Returns:
        Session: 数据库会话
    """
    from app.core.database import engine, TestingSessionLocal

    # 创建测试表
    Base.metadata.create_all(bind=engine)

    # 创建会话
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        # 清理测试表
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """
    创建测试客户端

    Args:
        db_session: 数据库会话

    Returns:
        TestClient: FastAPI测试客户端
    """
    from fastapi.testclient import TestClient

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session: Session) -> User:
    """
    创建测试用户

    Args:
        db_session: 数据库会话

    Returns:
        创建的测试用户
    """
    from app.core.security import get_password_hash

    user = User(
        username="testuser",
        password_hash=get_password_hash("testpass123"),
        email="test@example.com",
        full_name="Test User",
        role_id=1,
        status=UserStatus.ACTIVE,
        is_locked=False
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """
    创建管理员用户

    Args:
        db_session: 数据库会话

    Returns:
        创建的管理员用户
    """
    from app.core.security import get_password_hash

    user = User(
        username="admin",
        password_hash=get_password_hash("admin123"),
        email="admin@example.com",
        full_name="Admin User",
        role_id=1,
        status=UserStatus.ACTIVE,
        is_locked=False,
        is_superuser=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user: User) -> str:
    """
    生成测试用的认证令牌

    Args:
        test_user: 测试用户

    Returns:
        JWT令牌
    """
    from app.core.auth import create_access_token

    return create_access_token(data={"sub": test_user.username})


@pytest.fixture
def sample_users(db_session: Session) -> list[User]:
    """
    创建示例用户用于测试

    Args:
        db_session: 数据库会话

    Returns:
        创建的用户列表
    """
    users = []
    for i in range(5):
        user = User(
            username=f"user{i}",
            password_hash="hash",
            email=f"user{i}@example.com",
            full_name=f"Test User {i}",
            role_id=1,
            status=UserStatus.ACTIVE
        )
        db_session.add(user)
        users.append(user)

    db_session.commit()
    for user in users:
        db_session.refresh(user)

    return users


@pytest.fixture
def admin_token(admin_user: User) -> str:
    """
    生成管理员用的认证令牌

    Args:
        admin_user: 管理员用户

    Returns:
        JWT令牌
    """
    from app.core.security import create_access_token

    return create_access_token(data={"sub": admin_user.username})


@pytest.fixture
def sample_role(db_session: Session):
    """
    创建示例角色用于测试

    Args:
        db_session: 数据库会话

    Returns:
        创建的角色对象
    """
    from app.models.role import Role
    role = Role(
        name="测试角色",
        code="test_role",
        description="用于测试的角色"
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role
