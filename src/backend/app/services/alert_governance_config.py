"""
告警治理系统配置读取

从 soc_system_config 读取 category='alert_governance' 的配置（带 60s 缓存）。
承载：
  - triage_top_n      : 每日 AI 研判的 TopN 告警簇数量（默认 20）
  - suppress_rule_ids : 噪声抑制规则 ID 列表（逗号分隔，默认空）
  - min_group_count   : 告警簇最小条数阈值（默认 1，即不过滤）

首次读取时若缺省配置不存在，自动写入默认值，便于系统配置界面展示与编辑。

Phase 2 新增（2026-08-13）：
  - get_min_group_count / get_suppress_rule_ids 及对应 setter
  - filter_noise_groups(): 统一噪声过滤（digest / triage 共用，命中的簇移出必处理清单）
"""
import logging
import time
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models.system_config import SystemConfig
from app.services.system_config_service import SystemConfigService
from app.schemas.system_config import SystemConfigCreate, SystemConfigUpdate

logger = logging.getLogger(__name__)

CONFIG_CATEGORY = "alert_governance"
_CACHE_TTL = 60  # 秒

# key -> (默认值, value_type, 描述)
_DEFAULTS = {
    "triage_top_n": ("20", "number", "告警治理：每日 AI 研判的 TopN 告警簇数量（成本≈N 次/天调用）"),
    "suppress_rule_ids": ("", "string", "告警治理：噪声抑制规则 ID 列表（逗号分隔，命中的簇移出必处理清单）"),
    "min_group_count": ("1", "number", "告警治理：告警簇最小条数阈值（少于该值的簇不进入摘要/研判）"),
}

# 缓存整个 category 的 {key: value}
_cache = {"value": None, "at": 0.0}


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_all(db: Session) -> dict:
    """读取 category='alert_governance' 全部配置，缺失的自动建默认行。返回 {key: value}。"""
    rows = db.query(SystemConfig).filter(SystemConfig.category == CONFIG_CATEGORY).all()
    by_key = {r.key: r.value for r in rows}
    # 自动补默认行（让系统配置界面能一次性展示/编辑全部项）
    svc = SystemConfigService(db)
    for k, (default_val, vtype, desc) in _DEFAULTS.items():
        if k not in by_key:
            try:
                svc.create(
                    SystemConfigCreate(
                        category=CONFIG_CATEGORY,
                        key=k,
                        value=default_val,
                        value_type=vtype,
                        description=desc,
                    ),
                    user_id=None,
                )
                by_key.setdefault(k, default_val)
            except Exception as e:  # 并发写入或已存在都无所谓
                logger.warning("写入默认告警治理配置 %s 失败（可忽略）: %s", k, e)
                by_key.setdefault(k, default_val)
    return by_key


def _get_cached(db: Session) -> dict:
    """带 60s 缓存地读取全部 alert_governance 配置。"""
    now = time.time()
    if _cache["value"] is not None and (now - _cache["at"]) < _CACHE_TTL:
        return _cache["value"]
    values = _load_all(db)
    _cache["value"] = values
    _cache["at"] = now
    return values


def get_triage_top_n(db: Session) -> int:
    """读取每日 AI 研判 TopN（默认 20）。带缓存，配置变更后 60s 内生效。"""
    values = _get_cached(db)
    return _coerce_int(values.get("triage_top_n"), default=20)


def get_min_group_count(db: Session) -> int:
    """读取告警簇最小条数阈值（默认 1，即不过滤）。"""
    values = _get_cached(db)
    return max(1, _coerce_int(values.get("min_group_count"), default=1))


def get_suppress_rule_ids(db: Session) -> set:
    """读取噪声抑制规则 ID 集合（默认空集）。"""
    values = _get_cached(db)
    raw = values.get("suppress_rule_ids") or ""
    return {s.strip() for s in raw.split(",") if s.strip()}


def _upsert_config(db: Session, key: str, value: str) -> None:
    svc = SystemConfigService(db)
    row = (
        db.query(SystemConfig)
        .filter(SystemConfig.category == CONFIG_CATEGORY, SystemConfig.key == key)
        .first()
    )
    default_val, vtype, desc = _DEFAULTS[key]
    if row:
        svc.update(row.id, SystemConfigUpdate(value=value))
    else:
        svc.create(
            SystemConfigCreate(
                category=CONFIG_CATEGORY,
                key=key,
                value=value,
                value_type=vtype,
                description=desc,
            )
        )


def set_triage_top_n(db: Session, value: int) -> None:
    """更新 TopN（系统配置界面 PUT 后调用，立即刷新缓存）。"""
    _upsert_config(db, "triage_top_n", str(int(value)))
    invalidate()


def set_min_group_count(db: Session, value: int) -> None:
    """更新告警簇最小条数阈值，立即刷新缓存。"""
    _upsert_config(db, "min_group_count", str(max(1, int(value))))
    invalidate()


def set_suppress_rule_ids(db: Session, rule_ids: List[str]) -> None:
    """更新噪声抑制规则 ID 列表，立即刷新缓存。"""
    _upsert_config(
        db, "suppress_rule_ids", ",".join(str(s).strip() for s in rule_ids if str(s).strip())
    )
    invalidate()


def filter_noise_groups(groups: List[dict], db: Session) -> Tuple[List[dict], int]:
    """统一噪声过滤：移除 rule_id 命中 suppress 名单的簇。

    簇最小条数过滤(min_group_count)由调用方传给
    AlertQueryService.get_alert_groups 的 min_count 参数在源头完成；
    本函数只处理 suppress 名单。

    返回 (过滤后的簇列表, 被抑制的簇数量)。
    """
    suppress = get_suppress_rule_ids(db)
    if not suppress:
        return groups, 0
    kept = [g for g in groups if str(g.get("rule_id")) not in suppress]
    return kept, len(groups) - len(kept)


def invalidate() -> None:
    _cache["value"] = None
    _cache["at"] = 0.0
