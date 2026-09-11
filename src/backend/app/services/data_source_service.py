"""数据源 CRUD 服务（DataSourceService）

设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.4.1

特性：
- 设默认实例：事务内先清零同类型其他行（受部分唯一索引兜底）
- auth_secret 留空 / None 表示不修改原值；新建且 auth_type != none 时必填
- 写操作触发 ConfigAuditService.log + resolver.invalidate(source_type)
- 删除保护：v1 保守策略 —— 同类型唯一启用实例不允许删除
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.data_source import DataSource
from app.schemas.data_source import (
    DataSourceCreate,
    DataSourceUpdate,
)
from app.services.config_audit_service import ConfigAuditService
from app.services.data_source_resolver import data_source_resolver
from app.services.encryption_service import encryption_service

logger = logging.getLogger(__name__)


class DataSourceServiceError(Exception):
    """业务错误（API 层映射为 4xx）。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _derive_health_status(
    last_test_ok: Optional[bool], last_test_at: Optional[datetime]
) -> str:
    """根据 last_test_at / last_test_ok 派生 4 种健康状态。"""
    if last_test_at is None:
        return "untested"
    if last_test_ok is False:
        return "abnormal"
    # last_test_ok is True
    age_seconds = (datetime.utcnow() - last_test_at.replace(tzinfo=None)).total_seconds()
    if age_seconds > 24 * 3600:
        return "stale"
    return "normal"


def to_response(ds: DataSource) -> Dict:
    """ORM → dict（脱敏）。"""
    return {
        "id": ds.id,
        "source_code": ds.source_code,
        "source_type": ds.source_type,
        "name": ds.name,
        "endpoint": ds.endpoint,
        "auth_type": ds.auth_type,
        "auth_username": ds.auth_username,
        "has_secret": bool(ds.auth_secret),
        "secret_masked": "******" if ds.auth_secret else "",
        "verify_ssl": ds.verify_ssl,
        "timeout_seconds": ds.timeout_seconds,
        "retry_times": ds.retry_times,
        "retry_backoff_seconds": ds.retry_backoff_seconds,
        "enabled": ds.enabled,
        "is_default": ds.is_default,
        "config_json": ds.config_json or {},
        "last_test_at": ds.last_test_at,
        "last_test_ok": ds.last_test_ok,
        "last_test_message": ds.last_test_message,
        "health_status": _derive_health_status(ds.last_test_ok, ds.last_test_at),
        "created_at": ds.created_at,
        "updated_at": ds.updated_at,
        "updated_by": ds.updated_by,
    }


class DataSourceService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = ConfigAuditService(db)

    # ---------------- 查询 ----------------

    def get_by_id(self, ds_id: int) -> DataSource:
        ds = self.db.query(DataSource).filter(DataSource.id == ds_id).first()
        if not ds:
            raise DataSourceServiceError(f"数据源 {ds_id} 不存在", status_code=404)
        return ds

    def get_by_code(self, source_code: str) -> Optional[DataSource]:
        return (
            self.db.query(DataSource)
            .filter(DataSource.source_code == source_code)
            .first()
        )

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        source_type: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[DataSource], int]:
        q = self.db.query(DataSource)
        if source_type:
            q = q.filter(DataSource.source_type == source_type)
        if search:
            pattern = f"%{search}%"
            q = q.filter(
                (DataSource.source_code.ilike(pattern))
                | (DataSource.name.ilike(pattern))
            )
        total = q.count()
        items = (
            q.order_by(
                DataSource.source_type, DataSource.is_default.desc(), DataSource.id
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    # ---------------- 创建 ----------------

    def create(
        self,
        data: DataSourceCreate,
        *,
        operator_id: Optional[int] = None,
        operator_ip: Optional[str] = None,
    ) -> DataSource:
        if self.get_by_code(data.source_code):
            raise DataSourceServiceError(
                f"数据源编码 {data.source_code} 已存在", status_code=409
            )
        if data.auth_type != "none" and not data.auth_secret:
            raise DataSourceServiceError(
                "非 none 认证方式必须填写密码/密钥", status_code=400
            )

        before = {"source_code": data.source_code}
        encrypted_secret = (
            encryption_service.encrypt(data.auth_secret)
            if data.auth_secret
            else None
        )

        ds = DataSource(
            source_code=data.source_code,
            source_type=data.source_type,
            name=data.name,
            endpoint=data.endpoint,
            auth_type=data.auth_type,
            auth_username=data.auth_username,
            auth_secret=encrypted_secret,
            verify_ssl=data.verify_ssl,
            timeout_seconds=data.timeout_seconds,
            retry_times=data.retry_times,
            retry_backoff_seconds=data.retry_backoff_seconds,
            enabled=data.enabled,
            is_default=False,  # 事务内再置
            config_json=data.config_json or {},
            updated_by=operator_id,
        )
        self.db.add(ds)
        try:
            self.db.flush()
        except IntegrityError as e:
            self.db.rollback()
            raise DataSourceServiceError(f"唯一约束冲突：{e.orig}", status_code=409)

        if data.is_default:
            self._set_default_in_tx(ds)

        self.db.commit()
        self.db.refresh(ds)

        self.audit.log(
            target_type="data_source",
            target_key=ds.source_code,
            action="create",
            before=before,
            after=to_response(ds),
            changed_fields=list(to_response(ds).keys()),
            operator_id=operator_id,
            operator_ip=operator_ip,
        )

        data_source_resolver.invalidate(ds.source_type)
        return ds

    # ---------------- 更新 ----------------

    def update(
        self,
        ds_id: int,
        data: DataSourceUpdate,
        *,
        operator_id: Optional[int] = None,
        operator_ip: Optional[str] = None,
    ) -> DataSource:
        ds = self.get_by_id(ds_id)
        before = to_response(ds)

        changed: List[str] = []
        payload = data.model_dump(exclude_unset=True, exclude_none=False)

        # secret 留空/None 表示不修改
        if "auth_secret" in payload and (payload["auth_secret"] in (None, "")):
            payload.pop("auth_secret")

        for k, v in payload.items():
            if k == "auth_secret":
                setattr(ds, k, encryption_service.encrypt(v))
            elif k == "is_default":
                continue  # 单独处理
            elif k == "config_json":
                if v is not None and v != ds.config_json:
                    ds.config_json = v
                    changed.append(k)
            else:
                if getattr(ds, k) != v:
                    setattr(ds, k, v)
                    changed.append(k)

        if data.is_default is True and not ds.is_default:
            self._set_default_in_tx(ds)
            changed.append("is_default")
        elif data.is_default is False and ds.is_default:
            ds.is_default = False
            changed.append("is_default")

        self.db.commit()
        self.db.refresh(ds)

        if changed:
            self.audit.log(
                target_type="data_source",
                target_key=ds.source_code,
                action="update",
                before=before,
                after=to_response(ds),
                changed_fields=changed,
                operator_id=operator_id,
                operator_ip=operator_ip,
            )
            data_source_resolver.invalidate(ds.source_type)
        return ds

    # ---------------- 删除 ----------------

    def delete(
        self,
        ds_id: int,
        *,
        operator_id: Optional[int] = None,
        operator_ip: Optional[str] = None,
    ) -> None:
        ds = self.get_by_id(ds_id)

        # 删除保护 v1：同类型唯一启用实例不允许删除
        if ds.enabled:
            enabled_count = (
                self.db.query(DataSource)
                .filter(
                    DataSource.source_type == ds.source_type,
                    DataSource.enabled.is_(True),
                )
                .count()
            )
            if enabled_count <= 1:
                raise DataSourceServiceError(
                    f"这是 {ds.source_type} 类型当前唯一启用的数据源，请先新建替代实例或停用后再删",
                    status_code=409,
                )

        before = to_response(ds)
        self.db.delete(ds)
        self.db.commit()

        self.audit.log(
            target_type="data_source",
            target_key=ds.source_code,
            action="delete",
            before=before,
            after=None,
            changed_fields=None,
            operator_id=operator_id,
            operator_ip=operator_ip,
        )
        data_source_resolver.invalidate(ds.source_type)

    # ---------------- 启停 / 设默认 ----------------

    def set_enabled(
        self,
        ds_id: int,
        enabled: bool,
        *,
        operator_id: Optional[int] = None,
        operator_ip: Optional[str] = None,
    ) -> DataSource:
        ds = self.get_by_id(ds_id)
        if ds.enabled == enabled:
            return ds
        before = to_response(ds)
        ds.enabled = enabled
        if not enabled:
            ds.is_default = False  # 停用后不能保留默认标记
        self.db.commit()
        self.db.refresh(ds)
        self.audit.log(
            target_type="data_source",
            target_key=ds.source_code,
            action="enable" if enabled else "disable",
            before=before,
            after=to_response(ds),
            changed_fields=["enabled"],
            operator_id=operator_id,
            operator_ip=operator_ip,
        )
        data_source_resolver.invalidate(ds.source_type)
        return ds

    def set_default(
        self,
        ds_id: int,
        *,
        operator_id: Optional[int] = None,
        operator_ip: Optional[str] = None,
    ) -> DataSource:
        ds = self.get_by_id(ds_id)
        if not ds.enabled:
            raise DataSourceServiceError(
                "停用实例不能设为默认，请先启用", status_code=400
            )
        before = to_response(ds)
        self._set_default_in_tx(ds)
        self.db.commit()
        self.db.refresh(ds)
        self.audit.log(
            target_type="data_source",
            target_key=ds.source_code,
            action="set_default",
            before=before,
            after=to_response(ds),
            changed_fields=["is_default"],
            operator_id=operator_id,
            operator_ip=operator_ip,
        )
        data_source_resolver.invalidate(ds.source_type)
        return ds

    def _set_default_in_tx(self, ds: DataSource) -> None:
        """事务内清零同类型其他行的 is_default，然后置本行 true。"""
        self.db.query(DataSource).filter(
            DataSource.source_type == ds.source_type,
            DataSource.id != ds.id,
        ).update({DataSource.is_default: False})
        ds.is_default = True
        try:
            self.db.flush()
        except IntegrityError as e:
            self.db.rollback()
            raise DataSourceServiceError(
                f"设默认失败（同类型已有默认）：{e.orig}", status_code=409
            )

    # ---------------- 测试连接结果回写 ----------------

    def record_test_result(
        self,
        ds_id: int,
        *,
        ok: bool,
        message: str,
    ) -> None:
        ds = self.get_by_id(ds_id)
        ds.last_test_at = datetime.utcnow()
        ds.last_test_ok = ok
        ds.last_test_message = (message or "")[:1000]
        self.db.commit()
        self.audit.log(
            target_type="data_source",
            target_key=ds.source_code,
            action="test",
            before=None,
            after={"ok": ok, "message": ds.last_test_message},
            changed_fields=None,
            result="success" if ok else "failure",
        )