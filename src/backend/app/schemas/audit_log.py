"""Audit Log Schemas"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class AuditLogResponse(BaseModel):
    """审计日志响应"""
    id: int = Field(..., description="日志ID")
    user_id: Optional[int] = Field(None, description="用户ID")
    username: str = Field(..., description="用户名")
    action: str = Field(..., description="操作类型")
    resource_type: Optional[str] = Field(None, description="资源类型")
    resource_id: Optional[int] = Field(None, description="资源ID")
    resource_name: Optional[str] = Field(None, description="资源名称")
    old_values: Optional[Dict[str, Any]] = Field(None, description="变更前数据")
    new_values: Optional[Dict[str, Any]] = Field(None, description="变更后数据")
    ip_address: Optional[str] = Field(None, description="IP地址")
    user_agent: Optional[str] = Field(None, description="用户代理")
    session_id: Optional[int] = Field(None, description="会话ID")
    request_id: Optional[str] = Field(None, description="请求ID")
    status: str = Field(..., description="状态")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """审计日志列表响应"""
    total: int = Field(..., description="总数")
    items: List[AuditLogResponse] = Field(..., description="审计日志列表")
    page: int = Field(..., description="页码")
    page_size: int = Field(..., description="每页数量")


class AuditLogExportRequest(BaseModel):
    """审计日志导出请求"""
    user_id: Optional[int] = Field(None, description="用户ID筛选")
    username: Optional[str] = Field(None, description="用户名筛选")
    action: Optional[str] = Field(None, description="操作类型筛选")
    resource_type: Optional[str] = Field(None, description="资源类型筛选")
    status: Optional[str] = Field(None, description="状态筛选")
    start_date: Optional[str] = Field(None, description="开始日期")
    end_date: Optional[str] = Field(None, description="结束日期")
