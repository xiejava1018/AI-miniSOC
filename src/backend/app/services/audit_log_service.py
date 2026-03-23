"""
审计日志服务业务逻辑类
"""

from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime
import hashlib
import json

from app.models.audit_log import AuditLog


class AuditLogService:
    """审计日志业务逻辑类"""

    def __init__(self, db: Session):
        """
        初始化AuditLogService

        Args:
            db: 数据库会话
        """
        self.db = db

    def get_audit_logs(
        self,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Tuple[List[AuditLog], int]:
        """
        获取审计日志列表

        Args:
            skip: 跳过数量
            limit: 限制数量
            user_id: 用户ID筛选
            username: 用户名筛选（模糊匹配）
            action: 操作类型筛选
            resource_type: 资源类型筛选
            status: 状态筛选
            start_date: 开始日期（ISO 8601格式）
            end_date: 结束日期（ISO 8601格式）

        Returns:
            (审计日志列表, 总数)
        """
        query = self.db.query(AuditLog)

        # 精确筛选条件
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)

        if action:
            query = query.filter(AuditLog.action == action)

        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)

        if status:
            query = query.filter(AuditLog.status == status)

        # 模糊筛选条件
        if username:
            username_pattern = f"%{username}%"
            query = query.filter(AuditLog.username.ilike(username_pattern))

        # 时间范围筛选
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                query = query.filter(AuditLog.created_at >= start_dt)
            except ValueError:
                pass  # 无效日期格式，忽略筛选

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                query = query.filter(AuditLog.created_at <= end_dt)
            except ValueError:
                pass  # 无效日期格式，忽略筛选

        # 总数
        total = query.count()

        # 分页并按时间倒序排列
        audit_logs = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()

        return audit_logs, total

    def get_audit_log_by_id(self, log_id: int) -> Optional[AuditLog]:
        """
        根据ID获取审计日志

        Args:
            log_id: 日志ID

        Returns:
            审计日志对象或None
        """
        return self.db.query(AuditLog).filter(AuditLog.id == log_id).first()

    def create_audit_log(
        self,
        user_id: Optional[int],
        username: str,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        resource_name: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[int] = None,
        request_id: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None
    ) -> AuditLog:
        """
        创建审计日志

        Args:
            user_id: 用户ID
            username: 用户名
            action: 操作类型（LOGIN/LOGOUT/CREATE/UPDATE/DELETE/QUERY/EXPORT）
            resource_type: 资源类型（user/role/menu/asset/incident/alert）
            resource_id: 资源ID
            resource_name: 资源名称
            old_values: 变更前的数据（JSON格式）
            new_values: 变更后的数据（JSON格式）
            ip_address: 客户端IP地址
            user_agent: 客户端用户代理
            session_id: 会话ID
            request_id: 请求ID
            status: 操作状态（success/failure）
            error_message: 错误信息

        Returns:
            创建的审计日志对象
        """
        # 获取上一条日志的哈希值（用于形成链式结构）
        prev_log_hash = None
        last_log = self.db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        if last_log:
            prev_log_hash = last_log.log_hash

        # 创建审计日志对象
        audit_log = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            request_id=request_id,
            status=status,
            error_message=error_message,
            prev_log_hash=prev_log_hash,
            created_at=datetime.utcnow()
        )

        # 保存到数据库
        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)

        # 计算当前日志的哈希值（用于完整性校验）
        log_data = f"{audit_log.id}|{audit_log.user_id}|{audit_log.username}|{audit_log.action}|{audit_log.status}|{audit_log.created_at.isoformat()}"
        audit_log.log_hash = hashlib.sha256(log_data.encode()).hexdigest()
        self.db.commit()

        return audit_log

    def log_login(
        self,
        user_id: int,
        username: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None
    ) -> AuditLog:
        """
        记录登录日志

        Args:
            user_id: 用户ID
            username: 用户名
            ip_address: 客户端IP地址
            user_agent: 客户端用户代理
            status: 操作状态（success/failure）
            error_message: 错误信息

        Returns:
            创建的审计日志对象
        """
        return self.create_audit_log(
            user_id=user_id,
            username=username,
            action="LOGIN",
            resource_type="auth",
            resource_name="用户登录",
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            error_message=error_message
        )

    def log_logout(
        self,
        user_id: int,
        username: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[int] = None
    ) -> AuditLog:
        """
        记录登出日志

        Args:
            user_id: 用户ID
            username: 用户名
            ip_address: 客户端IP地址
            user_agent: 客户端用户代理
            session_id: 会话ID

        Returns:
            创建的审计日志对象
        """
        return self.create_audit_log(
            user_id=user_id,
            username=username,
            action="LOGOUT",
            resource_type="auth",
            resource_name="用户登出",
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id
        )
