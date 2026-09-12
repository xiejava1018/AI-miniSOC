"""配置变更审计服务（ConfigAuditService）→ 统一写入 soc_audit_logs

设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.4.5

历史：
- v1：写到独立表 soc_config_change_log（不参与 hash 链）
- v2：改写到统一表 soc_audit_logs（参与 hash 链），用 resource_type='data_source' 区分

特性（保留自 v1）：
- 敏感字段值替换为 "***"
- 写入失败不得阻断主流程，仅 logger.exception
- 单调向后追加，不允许 update/delete

设计权衡（v2）：
- 类名保留为 ConfigAuditService：data_source_service.py 有 6 处调用点
  （create/update/delete/enable/set_default/test），保持命名以避免大改
- 内部转调 AuditLogService.create_audit_log：自动参与 hash 链
  修复了 v1 的"data_source 改动不在 hash 链审计中"的覆盖盲区
- soc_audit_logs 用 JSONB 存 old/new_values（v1 是 Text），因此 payload 里
  的 datetime/Decimal 等非 JSON 原生类型需走 _jsonify 转为 ISO 字符串
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional

from sqlalchemy.orm import Session

from app.services.audit_log_service import AuditLogService

logger = logging.getLogger(__name__)

# 触发脱敏的字段名后缀（不区分大小写）
_SENSITIVE_KEYS = (
    "auth_secret",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "access_key",
)


def _mask_sensitive(payload: Any) -> Any:
    """递归把 dict 中敏感字段的值替换为 "***"（保留结构以便字段名记录）。"""
    if isinstance(payload, dict):
        out: Dict[str, Any] = {}
        for k, v in payload.items():
            kl = str(k).lower()
            if any(s in kl for s in _SENSITIVE_KEYS):
                out[k] = "***"
            else:
                out[k] = _mask_sensitive(v)
        return out
    if isinstance(payload, list):
        return [_mask_sensitive(x) for x in payload]
    return payload


def _jsonify(payload: Any) -> Any:
    """递归把 datetime/Decimal/date 等非 JSON 原生类型转为字符串。

    soc_audit_logs.old_values/new_values 是 JSONB，
    直接 ORM add 会因为 datetime 不可序列化失败。
    """
    if isinstance(payload, dict):
        return {k: _jsonify(v) for k, v in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_jsonify(x) for x in payload]
    if isinstance(payload, (datetime, date)):
        return payload.isoformat()
    if isinstance(payload, Decimal):
        return float(payload)
    return payload


class ConfigAuditService:
    """配置中心写操作的审计入口。
    内部转调 AuditLogService.create_audit_log()，所有配置变更自动纳入
    soc_audit_logs 的 hash 链审计（与登录/用户/角色等其它资源一致）。
    """

    def __init__(self, db: Session):
        self.db = db
        # 延迟解析 username（按需查表，避免每次构造 service 都查）
        self._username_cache: Dict[int, str] = {}

    def _resolve_username(self, user_id: Optional[int]) -> str:
        """按 user_id 查 username；查不到或失败则回退 'system'。"""
        if user_id is None:
            return "system"
        if user_id in self._username_cache:
            return self._username_cache[user_id]
        try:
            from app.models.user import User

            u = self.db.query(User).filter(User.id == user_id).first()
            name = u.username if u else "system"
        except Exception as e:
            logger.warning("audit 查 username 失败（fallback system）: %s", e)
            name = "system"
        self._username_cache[user_id] = name
        return name

    @staticmethod
    def _extract_resource_id(before: Any, after: Any) -> Optional[int]:
        """从 before/after dict 里取 id 字段（如 data_source.id）。"""
        for payload in (after, before):
            if isinstance(payload, dict) and payload.get("id") is not None:
                try:
                    return int(payload["id"])
                except (TypeError, ValueError):
                    pass
        return None

    def log(
        self,
        target_type: str,
        target_key: str,
        action: str,
        before: Any = None,
        after: Any = None,
        changed_fields: Optional[Iterable[str]] = None,
        operator_id: Optional[int] = None,
        operator_ip: Optional[str] = None,
        result: str = "success",
    ) -> None:
        """记录一条配置变更审计。

        内部映射到 soc_audit_logs，字段对齐：
        - target_type → resource_type
        - target_key  → resource_name（如 data_source.source_code）
        - before/after (mask 后) → old_values/new_values（JSONB）
        - operator_id → user_id（同步查 username）
        - operator_ip → ip_address
        - result      → status

        changed_fields 不直接落表，但旧/新值对比已隐含字段差异。
        写入失败不得阻断主流程。
        """
        try:
            masked_before = _jsonify(_mask_sensitive(before))
            masked_after = _jsonify(_mask_sensitive(after))

            username = self._resolve_username(operator_id)
            resource_id = self._extract_resource_id(before, after)

            AuditLogService(self.db).create_audit_log(
                user_id=operator_id,
                username=username,
                action=action,
                resource_type=target_type,
                resource_id=resource_id,
                resource_name=target_key,
                old_values=masked_before,
                new_values=masked_after,
                ip_address=operator_ip,
                status=result if result in ("success", "failure") else "success",
            )
        except Exception as e:
            logger.exception("写入配置审计失败（已吞掉，不影响主流程）: %s", e)
