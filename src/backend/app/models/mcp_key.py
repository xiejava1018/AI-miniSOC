"""
MCP Key 模型（PR1 用户中心重构 + MCP Key 管理）

设计文档：docs/design/2026-10-12-用户中心重构与MCP-Key管理设计.md §3.1

- Key 是用户的第二种凭证，权限完全继承用户角色（同 GitHub PAT 模式）
- 只存 SHA-256 哈希，永不存明文（沿用 soc_scan_agents.api_key_hash 先例）
- 过期是运行时判定（now() > expires_at），不落库状态列——避免过期清理任务
- 注销/过期是终态，不复用记录；重新申请 = 新记录，历史留档满足审计
- ON DELETE CASCADE：删除用户自动清 Key，无孤儿凭证
"""

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.models.base import Base


class SOCMCPKey(Base):
    """MCP 接入凭证表 soc_mcp_keys"""

    __tablename__ = "soc_mcp_keys"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("soc_users.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(50), nullable=False)  # 用途标识，active 内同 user 应用层唯一
    key_prefix = Column(String(16), nullable=False)  # 明文前缀 "sk-mcp-"+4位，列表辨认用
    key_hash = Column(String(255), nullable=False, unique=True)  # SHA-256 hex
    status = Column(String(20), nullable=False, default="active")  # active / revoked
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    revoke_reason = Column(String(100))  # user_revoked / admin_revoked
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<SOCMCPKey(id={self.id}, user_id={self.user_id}, name={self.name}, status={self.status})>"
