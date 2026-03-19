"""
审计日志服务
提供完整的操作审计功能，支持哈希链防篡改
"""

from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import json
import hashlib
from datetime import datetime

from app.models.audit_log import AuditLog


class AuditService:
    """审计日志服务"""

    @staticmethod
    def log(
        db: Session,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        action: str = "",
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        resource_name: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[int] = None,
        request_id: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        记录审计日志

        Args:
            db: 数据库会话
            user_id: 用户ID
            username: 用户名
            action: 操作类型（LOGIN, LOGOUT, CREATE, UPDATE, DELETE等）
            resource_type: 资源类型
            resource_id: 资源ID
            resource_name: 资源名称
            ip_address: IP地址
            user_agent: 用户代理
            session_id: 会话ID
            request_id: 请求ID
            status: 状态（success, failure）
            error_message: 错误消息
            old_values: 变更前值（JSONB字典）
            new_values: 变更后值（JSONB字典）
            details: 额外详情

        Returns:
            AuditLog: 创建的审计日志记录
        """
        # 获取前一条日志的哈希
        previous_hash = AuditService._get_previous_hash(db, user_id)

        # 创建审计日志
        audit_log = AuditLog(
            user_id=user_id,
            username=username if username else "",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            request_id=request_id,
            status=status,
            error_message=error_message,
            old_values=old_values,
            new_values=new_values,
            prev_log_hash=previous_hash
        )

        # 获取当前时间戳用于哈希计算
        # created_at 由数据库自动设置，但我们需要它的值来计算哈希
        current_timestamp = datetime.utcnow()

        # 计算当前哈希
        audit_log.log_hash = AuditService._calculate_hash(
            previous_hash=previous_hash,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            timestamp=current_timestamp
        )

        db.add(audit_log)
        db.commit()
        db.refresh(audit_log)

        return audit_log

    @staticmethod
    def _get_previous_hash(db: Session, user_id: Optional[int]) -> Optional[str]:
        """
        获取前一条日志的哈希值

        Args:
            db: 数据库会话
            user_id: 用户ID（None表示系统操作）

        Returns:
            Optional[str]: 前一条日志的哈希值，如果没有则返回None
        """
        if user_id:
            # 获取该用户最近的一条日志
            last_log = db.query(AuditLog).filter(
                AuditLog.user_id == user_id
            ).order_by(AuditLog.created_at.desc()).first()
        else:
            # 获取系统最近的一条日志
            last_log = db.query(AuditLog).filter(
                AuditLog.user_id.is_(None)
            ).order_by(AuditLog.created_at.desc()).first()

        return last_log.log_hash if last_log else None

    @staticmethod
    def _calculate_hash(
        previous_hash: Optional[str],
        user_id: Optional[int],
        action: str,
        resource_type: Optional[str],
        resource_id: Optional[int],
        status: str,
        timestamp: datetime
    ) -> str:
        """
        计算审计日志的哈希值

        Args:
            previous_hash: 前一条日志的哈希
            user_id: 用户ID
            action: 操作类型
            resource_type: 资源类型
            resource_id: 资源ID
            status: 状态
            timestamp: 时间戳

        Returns:
            str: SHA256哈希值（十六进制字符串）
        """
        # 构建哈希输入
        hash_input = (
            f"{previous_hash or ''}:"
            f"{user_id or ''}:"
            f"{action}:"
            f"{resource_type or ''}:"
            f"{resource_id or ''}:"
            f"{status}:"
            f"{timestamp.isoformat()}"
        )

        # 计算SHA256哈希
        return hashlib.sha256(hash_input.encode()).hexdigest()

    @staticmethod
    def verify_chain(db: Session, user_id: Optional[int] = None) -> bool:
        """
        验证哈希链的完整性

        Args:
            db: 数据库会话
            user_id: 用户ID（None验证所有系统操作）

        Returns:
            bool: 哈希链是否完整，True表示完整，False表示被篡改
        """
        # 获取所有相关日志按时间排序
        if user_id:
            logs = db.query(AuditLog).filter(
                AuditLog.user_id == user_id
            ).order_by(AuditLog.created_at.asc()).all()
        else:
            logs = db.query(AuditLog).order_by(AuditLog.created_at.asc()).all()

        expected_prev_hash: Optional[str] = None

        for log in logs:
            # 检查前一个哈希是否匹配
            if log.prev_log_hash != expected_prev_hash:
                return False

            # 重新计算当前哈希并检查是否匹配
            calculated_hash = AuditService._calculate_hash(
                previous_hash=log.prev_log_hash,
                user_id=log.user_id,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                status=log.status,
                timestamp=log.created_at
            )

            if calculated_hash != log.log_hash:
                return False

            expected_prev_hash = log.log_hash

        return True
