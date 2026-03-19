"""
测试配置和共享fixtures
"""

import pytest
from sqlalchemy.orm import Session
from typing import Generator

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
