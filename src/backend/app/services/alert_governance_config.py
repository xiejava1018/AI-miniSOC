"""
告警治理系统配置读取

从 soc_system_config 读取 category='alert_governance' 的配置（带 60s 缓存），
目前承载：
  - triage_top_n：每日 AI 研判的 TopN 告警簇数量（默认 20，可在系统配置 UI 修改）

首次读取时若缺省配置不存在，自动写入默认值，便于系统配置界面展示与编辑。
"""
import logging
import time

from sqlalchemy.orm import Session

from app.models.system_config import SystemConfig
from app.services.system_config_service import SystemConfigService
from app.schemas.system_config import SystemConfigCreate, SystemConfigUpdate

logger = logging.getLogger(__name__)

CONFIG_CATEGORY = "alert_governance"
_CACHE_TTL = 60  # 秒

_DEFAULTS = {
    "triage_top_n": ("20", "number"),
}

_cache = {"value": None, "at": 0.0}


def _coerce_int(value, default: int = 20) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_triage_top_n(db: Session) -> int:
    """读取每日 AI 研判 TopN（默认 20）。带缓存，配置变更后 60s 内生效。"""
    now = time.time()
    if _cache["value"] is not None and (now - _cache["at"]) < _CACHE_TTL:
        return _cache["value"]

    row = (
        db.query(SystemConfig)
        .filter(SystemConfig.category == CONFIG_CATEGORY, SystemConfig.key == "triage_top_n")
        .first()
    )
    if row and row.value is not None:
        val = _coerce_int(row.value, default=20)
    else:
        val = 20
        # 首次：写入默认配置，供系统配置界面编辑
        try:
            svc = SystemConfigService(db)
            svc.create(
                SystemConfigCreate(
                    category=CONFIG_CATEGORY,
                    key="triage_top_n",
                    value="20",
                    value_type="number",
                    description="告警治理：每日 AI 研判的 TopN 告警簇数量（成本≈N 次/天调用）",
                ),
                user_id=None,
            )
        except Exception as e:  # 并发写入或已存在都无所谓
            logger.warning("写入默认告警治理配置失败（可忽略）: %s", e)

    _cache["value"] = val
    _cache["at"] = now
    return val


def set_triage_top_n(db: Session, value: int) -> None:
    """更新 TopN（系统配置界面 PUT 后调用，立即刷新缓存）。"""
    svc = SystemConfigService(db)
    row = (
        db.query(SystemConfig)
        .filter(SystemConfig.category == CONFIG_CATEGORY, SystemConfig.key == "triage_top_n")
        .first()
    )
    if row:
        svc.update(row.id, SystemConfigUpdate(value=str(int(value))))
    else:
        svc.create(
            SystemConfigCreate(
                category=CONFIG_CATEGORY,
                key="triage_top_n",
                value=str(int(value)),
                value_type="number",
                description="告警治理：每日 AI 研判的 TopN 告警簇数量（成本≈N 次/天调用）",
            )
        )
    invalidate()


def invalidate() -> None:
    _cache["value"] = None
    _cache["at"] = 0.0
