"""
数据库模型
"""

from .base import Base
from .asset import Asset
from .asset_port import AssetPort
from .asset_tag import AssetTag
from .incident import Incident
from .ai_analysis import AIAnalysis
from .asset_incident import AssetIncident
from .user import User, UserStatus
from .user_session import UserSession
from .role import Role, RoleCode
from .role_menu import RoleMenu
from .menu import Menu
from .department import Department
from .system_config import SystemConfig
from .password_history import PasswordHistory
from .password_reset_token import PasswordResetToken
from .audit_log import AuditLog
from .rate_limit import RateLimit
from .sync_task import SyncTask
from .asset_change_log import AssetChangeLog
from .dict import Dict
from .chat import ChatSession, ChatMessage
from .notification import Notification
from .asset_source import AssetSource
from .browsing_event import BrowsingEvent
from .browsing_blacklist import BrowsingBlacklist
from .browsing_baseline import BrowsingBaseline
from .alert_digest import AlertDigest
from .alert_group_snapshot import AlertGroupSnapshot
from .alert_group_analysis import AlertGroupAnalysis
from .cisa_kev import CisaKev
from .task_observability import SocTaskRegistry, SocTaskRun, TaskRunStatus
from .asset_risk import AssetRiskHistory
from .ai_feedback import AiFeedback
from .knowledge import Knowledge
from .eol_reference import EolReference
from .compliance import ComplianceRun, ComplianceFinding
from .asset_reconciliation import AssetReconciliation

# P4 数据可靠性 / 脆弱性 / SCA 模块。
# 这 4 个模块此前漏在这里导入，导致 alembic env.py 的 Base.metadata 缺失下面 8 张表，
# `alembic check` 每次都把它们误报成 remove_table——一旦有人照着 autogenerate 出迁移，
# 生成的就是 DROP 这 8 张表的脚本。表本身在迁移链里是齐全的（见 a1b2c3d4e5f7 /
# c3d4e5f6g7h8 / c6d7e8f9a0b1 / d7e8f9a0b1c2），缺的只是 metadata 注册。
from .vulnerability import Vulnerability, AssetVulnerability, ScanTask
from .sca import ScaCheck, AssetScaCheck
from .source_health import SourceHealth
from .sync_dead_letter import SyncDeadLetter

__all__ = [
    "Base",
    "Asset",
    "AssetPort",
    "AssetTag",
    "Incident",
    "AIAnalysis",
    "AssetIncident",
    "User",
    "UserStatus",
    "UserSession",
    "Role",
    "RoleCode",
    "RoleMenu",
    "Menu",
    "Department",
    "SystemConfig",
    "PasswordHistory",
    "PasswordResetToken",
    "AuditLog",
    "RateLimit",
    "SyncTask",
    "AssetReconciliation",
    "AssetChangeLog",
    "Dict",
    "ChatSession",
    "ChatMessage",
    "Notification",
    "AssetSource",
    "BrowsingEvent",
    "BrowsingBlacklist",
    "BrowsingBaseline",
    "AlertDigest",
    "AlertGroupSnapshot",
    "AlertGroupAnalysis",
    "SocTaskRegistry",
    "SocTaskRun",
    "TaskRunStatus",
    "AssetRiskHistory",
    "AiFeedback",
    "Knowledge",
    "EolReference",
    "ComplianceRun",
    "ComplianceFinding",
    # P4 / 脆弱性 / SCA
    "Vulnerability",
    "AssetVulnerability",
    "ScanTask",
    "ScaCheck",
    "AssetScaCheck",
    "SourceHealth",
    "SyncDeadLetter",
]
