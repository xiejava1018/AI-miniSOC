"""
Pydantic Schemas
"""

from .asset import AssetBase, AssetCreate, AssetUpdate, AssetResponse
from .incident import IncidentBase, IncidentCreate, IncidentUpdate, IncidentResponse
from .ai_analysis import AIAnalysisBase, AIAnalysisCreate, AIAnalysisResponse

from .auth import (
    LoginRequest, ChangePasswordRequest, TokenResponse,
    UserMeResponse, RefreshTokenRequest
)
from .user import (
    UserBase, UserCreate, UserUpdate, UserResponse, UserListResponse,
    ResetPasswordRequest, LockUserRequest
)
from .role import (
    RoleBase, RoleCreate, RoleUpdate, RoleResponse,
    RoleMenusUpdate, RoleWithMenusResponse
)
from .menu import (
    MenuBase, MenuCreate, MenuUpdate, MenuResponse, MenuTreeResponse
)
from .config import (
    ConfigItem, ConfigResponse, ConfigUpdate,
    TestSmtpRequest, TestWebhookRequest
)

__all__ = [
    # Asset schemas
    "AssetBase", "AssetCreate", "AssetUpdate", "AssetResponse",
    # Incident schemas
    "IncidentBase", "IncidentCreate", "IncidentUpdate", "IncidentResponse",
    # AI Analysis schemas
    "AIAnalysisBase", "AIAnalysisCreate", "AIAnalysisResponse",
    # Auth schemas
    "LoginRequest", "ChangePasswordRequest", "TokenResponse",
    "UserMeResponse", "RefreshTokenRequest",
    # User schemas
    "UserBase", "UserCreate", "UserUpdate", "UserResponse", "UserListResponse",
    "ResetPasswordRequest", "LockUserRequest",
    # Role schemas
    "RoleBase", "RoleCreate", "RoleUpdate", "RoleResponse",
    "RoleMenusUpdate", "RoleWithMenusResponse",
    # Menu schemas
    "MenuBase", "MenuCreate", "MenuUpdate", "MenuResponse", "MenuTreeResponse",
    # Config schemas
    "ConfigItem", "ConfigResponse", "ConfigUpdate",
    "TestSmtpRequest", "TestWebhookRequest"
]
