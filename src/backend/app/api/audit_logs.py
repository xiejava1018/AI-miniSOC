"""
审计日志API路由
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import csv
from io import StringIO

from app.core.database import get_db
from app.core.permissions import require_role
from app.schemas.user import UserResponse
from app.schemas.audit_log import AuditLogResponse, AuditLogListResponse, AuditLogExportRequest
from app.services.audit_log_service import AuditLogService


router = APIRouter(prefix="/audit-logs", tags=["审计日志管理"])


@router.get("", response_model=AuditLogListResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user_id: Optional[int] = Query(None, description="用户ID筛选"),
    username: Optional[str] = Query(None, description="用户名筛选"),
    action: Optional[str] = Query(None, description="操作类型筛选"),
    resource_type: Optional[str] = Query(None, description="资源类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    start_date: Optional[str] = Query(None, description="开始日期（ISO 8601格式）"),
    end_date: Optional[str] = Query(None, description="结束日期（ISO 8601格式）"),
    current_user: UserResponse = Depends(require_role("admin", "auditor")),
    db: Session = Depends(get_db)
):
    """
    获取审计日志列表

    需要权限: 管理员或审计人员（PRD X1：auditor 核心职能）
    """
    service = AuditLogService(db)
    skip = (page - 1) * page_size

    audit_logs, total = service.get_audit_logs(
        skip=skip,
        limit=page_size,
        user_id=user_id,
        username=username,
        action=action,
        resource_type=resource_type,
        status=status,
        start_date=start_date,
        end_date=end_date
    )

    return AuditLogListResponse(
        total=total,
        items=[AuditLogResponse.model_validate(log) for log in audit_logs],
        page=page,
        page_size=page_size
    )


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: int,
    current_user: UserResponse = Depends(require_role("admin", "auditor")),
    db: Session = Depends(get_db)
):
    """
    获取审计日志详情

    需要权限: 管理员或审计人员（PRD X1）
    """
    service = AuditLogService(db)
    audit_log = service.get_audit_log_by_id(log_id)

    if not audit_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计日志不存在"
        )

    return AuditLogResponse.model_validate(audit_log)


@router.post("/export")
async def export_audit_logs(
    filters: AuditLogExportRequest,
    current_user: UserResponse = Depends(require_role("admin", "auditor")),
    db: Session = Depends(get_db)
):
    """
    导出审计日志（CSV格式）

    需要权限: 仅管理员
    """
    service = AuditLogService(db)

    # 获取所有符合条件的数据（不分页）
    audit_logs, _ = service.get_audit_logs(
        skip=0,
        limit=10000,  # 导出上限
        user_id=filters.user_id,
        username=filters.username,
        action=filters.action,
        resource_type=filters.resource_type,
        status=filters.status,
        start_date=filters.start_date,
        end_date=filters.end_date
    )

    # 创建CSV内容
    output = StringIO()
    writer = csv.writer(output)

    # 写入表头
    writer.writerow([
        'ID', '用户名', '操作类型', '资源类型', '资源ID', '资源名称',
        'IP地址', '状态', '错误信息', '创建时间'
    ])

    # 写入数据
    for log in audit_logs:
        writer.writerow([
            log.id,
            log.username,
            log.action,
            log.resource_type or '',
            log.resource_id or '',
            log.resource_name or '',
            log.ip_address or '',
            log.status,
            log.error_message or '',
            log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else ''
        ])

    # 生成文件名
    filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    # 返回CSV文件
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
