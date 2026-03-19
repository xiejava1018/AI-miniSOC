"""
UserService单元测试
"""

import pytest
from sqlalchemy.orm import Session

from app.services.user_service import UserService


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
