"""
审计日志服务测试
"""

import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.audit import AuditService
from app.models.audit_log import AuditLog


class TestAuditService:
    """审计日志服务测试"""

    def test_log_basic(self, db: Session):
        """测试基本的日志记录"""
        audit_log = AuditService.log(
            db=db,
            user_id=1,
            username="testuser",
            action="LOGIN",
            ip_address="192.168.1.1",
            status="success"
        )

        assert audit_log.id is not None
        assert audit_log.user_id == 1
        assert audit_log.username == "testuser"
        assert audit_log.action == "LOGIN"
        assert audit_log.ip_address == "192.168.1.1"
        assert audit_log.status == "success"
        assert audit_log.log_hash is not None
        assert len(audit_log.log_hash) == 64  # SHA256 hex length

    def test_log_with_resource(self, db: Session):
        """测试记录资源操作"""
        audit_log = AuditService.log(
            db=db,
            user_id=1,
            username="admin",
            action="UPDATE",
            resource_type="User",
            resource_id=2,
            resource_name="Test User",
            old_values={"email": "old@example.com"},
            new_values={"email": "new@example.com"},
            status="success"
        )

        assert audit_log.resource_type == "User"
        assert audit_log.resource_id == 2
        assert audit_log.resource_name == "Test User"
        assert audit_log.old_values == {"email": "old@example.com"}
        assert audit_log.new_values == {"email": "new@example.com"}

    def test_log_failure(self, db: Session):
        """测试记录失败操作"""
        audit_log = AuditService.log(
            db=db,
            user_id=1,
            username="testuser",
            action="DELETE",
            resource_type="Document",
            resource_id=10,
            status="failure",
            error_message="Permission denied"
        )

        assert audit_log.status == "failure"
        assert audit_log.error_message == "Permission denied"

    def test_previous_hash_chain(self, db: Session):
        """测试哈希链链接"""
        # 创建第一条日志
        log1 = AuditService.log(
            db=db,
            user_id=1,
            username="testuser",
            action="CREATE",
            resource_type="Document",
            status="success"
        )

        # 第一条日志的 prev_log_hash 应该为 None
        assert log1.prev_log_hash is None

        # 创建第二条日志
        log2 = AuditService.log(
            db=db,
            user_id=1,
            username="testuser",
            action="UPDATE",
            resource_type="Document",
            status="success"
        )

        # 第二条日志的 prev_log_hash 应该等于第一条的 log_hash
        assert log2.prev_log_hash == log1.log_hash

        # 创建第三条日志
        log3 = AuditService.log(
            db=db,
            user_id=1,
            username="testuser",
            action="DELETE",
            resource_type="Document",
            status="success"
        )

        # 第三条日志的 prev_log_hash 应该等于第二条的 log_hash
        assert log3.prev_log_hash == log2.log_hash

    def test_hash_calculation(self, db: Session):
        """测试哈希计算"""
        audit_log = AuditService.log(
            db=db,
            user_id=1,
            username="testuser",
            action="TEST",
            status="success"
        )

        # 重新计算哈希
        calculated_hash = AuditService._calculate_hash(
            previous_hash=audit_log.prev_log_hash,
            user_id=audit_log.user_id,
            action=audit_log.action,
            resource_type=audit_log.resource_type,
            resource_id=audit_log.resource_id,
            status=audit_log.status,
            timestamp=audit_log.created_at
        )

        assert calculated_hash == audit_log.log_hash

    def test_verify_chain_valid(self, db: Session):
        """测试验证完整的哈希链"""
        # 创建一条哈希链
        log1 = AuditService.log(
            db=db,
            user_id=1,
            username="testuser",
            action="CREATE",
            status="success"
        )

        log2 = AuditService.log(
            db=db,
            user_id=1,
            username="testuser",
            action="UPDATE",
            status="success"
        )

        log3 = AuditService.log(
            db=db,
            user_id=1,
            username="testuser",
            action="DELETE",
            status="success"
        )

        # 验证哈希链应该成功
        assert AuditService.verify_chain(db, user_id=1) is True

    def test_system_log(self, db: Session):
        """测试系统操作日志（无用户ID）"""
        audit_log = AuditService.log(
            db=db,
            user_id=None,
            username="system",
            action="BACKUP",
            resource_type="Database",
            status="success"
        )

        assert audit_log.user_id is None
        assert audit_log.username == "system"

        # 系统日志应该有独立的哈希链
        log2 = AuditService.log(
            db=db,
            user_id=None,
            username="system",
            action="CLEANUP",
            status="success"
        )

        assert log2.prev_log_hash == audit_log.log_hash

    def test_multiple_users_separate_chains(self, db: Session):
        """测试不同用户的独立哈希链"""
        # 用户1的日志
        user1_log1 = AuditService.log(
            db=db,
            user_id=1,
            username="user1",
            action="LOGIN",
            status="success"
        )

        # 用户2的日志
        user2_log1 = AuditService.log(
            db=db,
            user_id=2,
            username="user2",
            action="LOGIN",
            status="success"
        )

        # 两个用户的第一条日志都应该没有 prev_log_hash
        assert user1_log1.prev_log_hash is None
        assert user2_log1.prev_log_hash is None

        # 用户1的第二条日志
        user1_log2 = AuditService.log(
            db=db,
            user_id=1,
            username="user1",
            action="LOGOUT",
            status="success"
        )

        # 应该链接到用户1的第一条日志
        assert user1_log2.prev_log_hash == user1_log1.log_hash
