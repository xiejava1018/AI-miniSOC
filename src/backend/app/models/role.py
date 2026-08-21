"""
角色模型
"""

from enum import Enum
from sqlalchemy import Column, String, Text, BigInteger, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class RoleCode(str, Enum):
    """角色代码枚举（PRD P3 / X1 权限矩阵）

    ADMIN     : 全部权限
    OPERATOR  : 运维：资产读写、对账、AI 查询/报告生成/知识编辑/EOL 覆盖（不可改系统配置）
    VIEWER    : 只读用户：可看资产/告警/报告/知识，不可写任何东西
    AUDITOR   : 审计：与 viewer 类似但额外开放「审计日志」菜单
    USER      : 历史遗留，默认等同于 VIEWER（保留兼容）
    READONLY  : 历史遗留，默认等同于 VIEWER（保留兼容）
    """
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    AUDITOR = "auditor"
    USER = "user"
    READONLY = "readonly"


class Role(Base):
    """角色表"""
    __tablename__ = "soc_roles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    is_system = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    users = relationship("User", back_populates="role")
    menus = relationship("Menu", secondary="soc_role_menus", back_populates="roles")

    def __repr__(self):
        return f"<Role(id={self.id}, name={self.name}, code={self.code})>"
