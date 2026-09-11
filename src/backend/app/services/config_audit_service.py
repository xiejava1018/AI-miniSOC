"""配置变更审计服务（ConfigAuditService）

设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.4.5

特性：
- 敏感字段值替换为 "***"
- 写入失败不得阻断主流程，仅 logger.exception
- 单调向后追加，不允许 update/delete
"""

import logging
from typing import Any, Dict, Iterable, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.config_change_log import ConfigChangeLog

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


def _stringify_masked(payload: Any) -> Optional[str]:
    """将 mask 后的 payload 序列化为字符串；None 直接返回 None。"""
    if payload is None:
        return None
    try:
        import json

        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning("audit payload 序列化失败: %s", e)
        return str(payload)


class ConfigAuditService:
    def __init__(self, db: Session):
        self.db = db

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
        """记录一条审计事件。

        写入失败不得阻断主流程。
        """
        try:
            before_str = _stringify_masked(_mask_sensitive(before))
            after_str = _stringify_masked(_mask_sensitive(after))
            changed_list = (
                [f for f in changed_fields if f] if changed_fields else None
            )
            entry = ConfigChangeLog(
                target_type=target_type,
                target_key=target_key,
                action=action,
                before_value=before_str,
                after_value=after_str,
                changed_fields=changed_list,
                operator_id=operator_id,
                operator_ip=operator_ip,
                result=result,
            )
            self.db.add(entry)
            self.db.commit()
        except Exception as e:
            logger.exception("写入配置审计失败（已吞掉，不影响主流程）: %s", e)
            try:
                self.db.rollback()
            except Exception:
                pass