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
