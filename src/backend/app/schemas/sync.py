"""
同步相关Schemas
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID


class SyncTaskBase(BaseModel):
    """同步任务基础schema"""
    sync_type: str = Field(..., description="同步类型: manual, webhook, scheduled")
    status: str = Field(default="pending", description="状态: pending, running, completed, failed")


class SyncTaskCreate(SyncTaskBase):
    """创建同步任务"""
    pass


class SyncTaskResponse(SyncTaskBase):
    """同步任务响应"""
    id: UUID
    total_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    failed_count: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    @property
    def progress(self) -> str:
        """计算进度百分比"""
        if self.total_count == 0:
            return "0%"
        completed = self.created_count + self.updated_count + self.failed_count
        return f"{int(completed / self.total_count * 100)}%"

    model_config = {
        "from_attributes": True
    }


class SyncTaskList(BaseModel):
    """同步任务列表"""
    total: int
    items: list[SyncTaskResponse]


class ManualSyncResponse(BaseModel):
    """手动同步响应"""
    task_id: str
    status: str
    message: str


class WebhookPayload(BaseModel):
    """Webhook payload"""
    agent_id: str
    agent_name: Optional[str] = None
    rule_id: Optional[str] = None
    alert: Optional[Dict[str, Any]] = None


class WebhookResponse(BaseModel):
    """Webhook响应"""
    success: bool
    message: str
    asset_id: Optional[str] = None


class RouterSyncRequest(BaseModel):
    """路由器同步请求"""
    host: str = Field(..., description="路由器IP地址")
    username: str = Field(..., description="路由器管理用户名")
    password: str = Field(..., description="路由器管理密码")
    port: int = Field(default=80, description="路由器管理端口")


class RouterSyncResponse(BaseModel):
    """路由器同步响应"""
    message: str
    total: int
    created: int
    updated: int
    failed: int
