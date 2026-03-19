"""
审计服务
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.audit_log import AuditLog


class AuditService:
    """审计业务逻辑类"""

    def __init__(self, db: Session):
        """
        初始化AuditService

        Args:
            db: 数据库会话
        """
        self.db = db
