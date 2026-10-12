"""
MCP Key Service（PR1 用户中心重构 + MCP Key 管理）

设计文档：docs/design/2026-10-12-用户中心重构与MCP-Key管理设计.md §3/§4/§5

职责：
- MCPKeyService：申请 / 延期 / 注销 / 校验（API 层 B 与 MCP 中间件 C 共用）
- 模块级 get_config / validate_key_cached / invalidate_key_cache / touch_last_used：
  进程内共享，读 soc_system_config（category='mcp'，带 60s 缓存，
  模式对齐 app/services/alert_governance_config.py）

安全要点：
- 明文只在 create_key 返回值中出现一次，库里只有 SHA-256
- Key 撤销 → 同步清缓存 → MCP 中间件下一请求立即 401（无窗口期，
  见设计文档 §5.2 v1.2 修正——MCP mint 的 JWT 不出服务端，无需黑名单联动）
"""

import hashlib
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.mcp_key import SOCMCPKey
from app.models.system_config import SystemConfig
from app.models.user import User, UserStatus

logger = logging.getLogger(__name__)

# ============================================================================
# 配置读取（soc_system_config，category='mcp'，带 60s 缓存）
# ============================================================================

CONFIG_CATEGORY = "mcp"
_CONFIG_CACHE_TTL = 60  # 配置本身的缓存秒数

# key -> (默认值, value_type, 描述)   key 为去掉 "mcp." 前缀后的短键
_DEFAULTS = {
    "auth.required": ("false", "boolean", "MCP 传输层是否强制要求 Bearer Key（生产置 true，本地 dev 免打扰）"),
    "key.max_per_user": ("5", "number", "每用户 active MCP Key 上限"),
    "key.max_validity_days": ("365", "number", "MCP Key 有效期上限（天）"),
    "key.min_validity_days": ("1", "number", "MCP Key 有效期下限（天）"),
    "key.cache_ttl_seconds": ("60", "number", "MCP Key 校验缓存 TTL（秒），注销/禁用主动失效，TTL 兜底"),
    "key.failure_lock_threshold": ("10", "number", "MCP Key 校验连续失败锁定阈值（按 IP）"),
    "key.failure_lock_minutes": ("15", "number", "MCP Key 校验失败锁定时长（分钟）"),
}

# 配置缓存：{"value": {key: value_str}, "at": ts}
_config_cache: dict[str, Any] = {"value": None, "at": 0.0}
_config_lock = threading.Lock()

# Key 校验结果缓存：key_hash -> (result_dict, expire_ts)
# result_dict 含 ok=True 的正向条目与 ok=False 的负向条目（如 key_invalid），
# 负向条目也缓存以抗爆破（TTL 同正向，由配置项控制）。
_key_cache: dict[str, Tuple[dict, float]] = {}
_key_cache_lock = threading.Lock()


def _coerce_bool(value: str, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off"):
        return False
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _load_mcp_configs(db: Session) -> dict:
    """读取 category='mcp' 全部配置；缺行不自动建（种子由 alembic 迁移幂等写入）。"""
    try:
        rows = db.query(SystemConfig).filter(SystemConfig.category == CONFIG_CATEGORY).all()
        return {r.key: r.value for r in rows}
    except Exception as e:  # noqa: BLE001
        logger.warning("读取 mcp 配置失败（用默认值兜底）: %s", e)
        try:
            db.rollback()  # 必须 rollback，否则失败的事务毒化同一 Session 的后续查询
        except Exception:  # noqa: BLE001
            pass
        return {}


def _get_config_values(db: Optional[Session] = None) -> dict:
    """带 60s 缓存地读取全部 mcp.* 配置（合并默认值）。"""
    now = time.time()
    with _config_lock:
        if _config_cache["value"] is not None and (now - _config_cache["at"]) < _CONFIG_CACHE_TTL:
            return _config_cache["value"]
    values = {k: v[0] for k, v in _DEFAULTS.items()}
    if db is not None:
        values.update(_load_mcp_configs(db))
    else:
        # 无 Session 时（如中间件热路径）用短 Session 读一次
        try:
            from app.core.database import SessionLocal
            sess = SessionLocal()
            try:
                values.update(_load_mcp_configs(sess))
            finally:
                sess.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("mcp 配置懒加载失败（用默认值兜底）: %s", e)
    with _config_lock:
        _config_cache["value"] = values
        _config_cache["at"] = now
    return values


def get_config(key: str, default: Any = None, db: Optional[Session] = None) -> Any:
    """读取 mcp.* 配置项（key 形如 "mcp.auth.required"），按默认值类型返回。

    bool 项返回 bool，数字项返回 int，其余返回 str。
    """
    short_key = key[len("mcp."):] if key.startswith("mcp.") else key
    values = _get_config_values(db)
    raw = values.get(short_key)
    if raw is None:
        return default
    if isinstance(default, bool):
        return _coerce_bool(raw, default)
    if isinstance(default, int) and not isinstance(default, bool):
        return _coerce_int(raw, default)
    return str(raw)


def _config_int(short_key: str, default: int, db: Optional[Session] = None) -> int:
    """读 int 配置；有 Session 时用它（测试隔离关键：不走 app 连接池）。"""
    values = _get_config_values(db)
    return _coerce_int(values.get(short_key), default)


# ============================================================================
# Key 校验缓存（C 的 MCP 中间件热路径）
# ============================================================================

def invalidate_key_cache(key_hash: Optional[str] = None, user_id: Optional[int] = None) -> None:
    """主动失效：单 Key 注销/延期清该 hash；用户禁用/删除清该 user 名下全部。

    由 service 的写操作自动调用，API/中间件无需关心。
    """
    with _key_cache_lock:
        if key_hash is not None:
            _key_cache.pop(key_hash, None)
        if user_id is not None:
            # 缓存值里带 user_id，按归属批量清（避免维护反向索引）
            for h in [h for h, (r, _) in _key_cache.items() if r.get("user_id") == user_id]:
                _key_cache.pop(h, None)


def _validate_key_uncached(plaintext: str, db: Session) -> dict:
    """真实校验一次 Key（DB 点查 key_hash 唯一索引）。"""
    key_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    row = db.query(SOCMCPKey).filter(SOCMCPKey.key_hash == key_hash).first()
    if row is None:
        return {"ok": False, "error": "key_invalid", "user_id": None, "username": None, "role_code": None, "key_id": None}
    if row.status != "active":
        return {"ok": False, "error": "key_revoked", "user_id": None, "username": None, "role_code": None, "key_id": None}
    now = datetime.now(timezone.utc)
    exp = row.expires_at
    if exp.tzinfo is None:  # naive 兼容
        exp = exp.replace(tzinfo=timezone.utc)
    if now >= exp:
        return {"ok": False, "error": "key_expired", "user_id": None, "username": None, "role_code": None, "key_id": None}
    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None or str(user.status) not in (UserStatus.ACTIVE.value, UserStatus.ACTIVE):
        return {"ok": False, "error": "user_disabled", "user_id": None, "username": None, "role_code": None, "key_id": None}
    role_code = user.role.code if user.role else None
    return {
        "ok": True,
        "error": None,
        "user_id": user.id,
        "username": user.username,
        "role_code": role_code,
        "key_id": row.id,
    }


def validate_key_cached(plaintext: str, db: Optional[Session] = None) -> dict:
    """带 TTL 缓存的 Key 校验（MCP 中间件每请求调用）。

    缓存条目含 user_id，供 invalidate_key_cache(user_id=...) 批量失效。
    """
    key_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    ttl = max(1, _config_int("key.cache_ttl_seconds", 60, db))
    now = time.time()
    with _key_cache_lock:
        hit = _key_cache.get(key_hash)
        if hit is not None and hit[1] > now:
            return hit[0]

    def _run(session: Session) -> dict:
        result = _validate_key_uncached(plaintext, session)
        with _key_cache_lock:
            _key_cache[key_hash] = (result, now + ttl)
        return result

    if db is not None:
        return _run(db)
    try:
        from app.core.database import SessionLocal
        sess = SessionLocal()
        try:
            return _run(sess)
        finally:
            sess.close()
    except Exception as e:  # noqa: BLE001
        logger.error("validate_key_cached DB 异常: %s", e)
        return {"ok": False, "error": "key_invalid", "user_id": None, "username": None, "role_code": None, "key_id": None}


def touch_last_used(key_id: int) -> None:
    """后台写回 last_used_at，失败静默（不阻塞 MCP 请求路径）。

    独立 Session + 独立线程安全（可由调用方放线程池，也可直接调）。
    """
    try:
        from app.core.database import SessionLocal
        sess = SessionLocal()
        try:
            row = sess.query(SOCMCPKey).filter(SOCMCPKey.id == key_id).first()
            if row is not None:
                row.last_used_at = datetime.now(timezone.utc)
                sess.commit()
        finally:
            sess.close()
    except Exception as e:  # noqa: BLE001
        logger.debug("touch_last_used(%s) 失败（静默）: %s", key_id, e)


# ============================================================================
# Key 管理 Service（B 的 API 层用）
# ============================================================================

def _gen_key() -> Tuple[str, str, str]:
    """生成 (明文, key_prefix, key_hash)。明文 sk-mcp- + 40 位随机。"""
    plaintext = "sk-mcp-" + secrets.token_urlsafe(32)[:40]
    key_prefix = plaintext[:11]  # "sk-mcp-" + 4 位
    key_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return plaintext, key_prefix, key_hash


class MCPKeyService:
    def __init__(self, db: Session):
        self.db = db

    # ---------- 查询 ----------

    def list_keys(self, user_id: int) -> list:
        """用户的 Key 列表（新→旧；不含明文）。"""
        return (
            self.db.query(SOCMCPKey)
            .filter(SOCMCPKey.user_id == user_id)
            .order_by(SOCMCPKey.id.desc())
            .all()
        )

    def get_key(self, user_id: int, key_id: int) -> SOCMCPKey:
        row = (
            self.db.query(SOCMCPKey)
            .filter(SOCMCPKey.id == key_id, SOCMCPKey.user_id == user_id)
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="MCP Key 不存在")
        return row

    # ---------- 写操作 ----------

    def create_key(self, user_id: int, name: str, validity_days: int) -> Tuple[SOCMCPKey, str]:
        """申请新 Key，返回 (记录, 明文一次性)。"""
        name = (name or "").strip()
        if not 1 <= len(name) <= 50:
            raise HTTPException(status_code=422, detail="Key 名称长度须为 1-50 字符")

        min_days = _config_int("key.min_validity_days", 1, self.db)
        max_days = _config_int("key.max_validity_days", 365, self.db)
        if not (min_days <= validity_days <= max_days):
            raise HTTPException(
                status_code=422,
                detail=f"有效期须在 {min_days}-{max_days} 天之间",
            )

        max_per_user = _config_int("key.max_per_user", 5, self.db)
        active_count = (
            self.db.query(SOCMCPKey)
            .filter(SOCMCPKey.user_id == user_id, SOCMCPKey.status == "active")
            .count()
        )
        if active_count >= max_per_user:
            raise HTTPException(
                status_code=409,
                detail=f"已达上限（{max_per_user} 个），请先注销不用的 Key",
            )

        same_name = (
            self.db.query(SOCMCPKey)
            .filter(
                SOCMCPKey.user_id == user_id,
                SOCMCPKey.name == name,
                SOCMCPKey.status == "active",
            )
            .first()
        )
        if same_name is not None:
            raise HTTPException(status_code=409, detail=f"名称 {name!r} 已被使用中的 Key 占用")

        plaintext, key_prefix, key_hash = _gen_key()
        row = SOCMCPKey(
            user_id=user_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(days=validity_days),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row, plaintext

    def extend_key(self, user_id: int, key_id: int, new_validity_days: int) -> SOCMCPKey:
        """延期（仅 active 可延期；新到期时间 = now + days；清缓存）。"""
        row = self.get_key(user_id, key_id)
        if row.status != "active":
            raise HTTPException(status_code=409, detail="Key 已注销，不可延期")
        min_days = _config_int("key.min_validity_days", 1, self.db)
        max_days = _config_int("key.max_validity_days", 365, self.db)
        if not (min_days <= new_validity_days <= max_days):
            raise HTTPException(
                status_code=422,
                detail=f"有效期须在 {min_days}-{max_days} 天之间",
            )
        row.expires_at = datetime.now(timezone.utc) + timedelta(days=new_validity_days)
        self.db.commit()
        self.db.refresh(row)
        invalidate_key_cache(key_hash=row.key_hash)
        return row

    def revoke_key(self, user_id: int, key_id: int, reason: str = "user_revoked") -> SOCMCPKey:
        """注销自己的 Key（幂等：已 revoked 直接返回；清缓存即时生效）。"""
        row = self.get_key(user_id, key_id)
        if row.status != "active":
            return row
        row.status = "revoked"
        row.revoked_at = datetime.now(timezone.utc)
        row.revoke_reason = reason
        self.db.commit()
        self.db.refresh(row)
        invalidate_key_cache(key_hash=row.key_hash)
        return row

    def admin_revoke_key(self, key_id: int) -> SOCMCPKey:
        """admin 强制注销任意 Key（reason=admin_revoked；清缓存）。"""
        row = self.db.query(SOCMCPKey).filter(SOCMCPKey.id == key_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="MCP Key 不存在")
        if row.status != "active":
            return row
        row.status = "revoked"
        row.revoked_at = datetime.now(timezone.utc)
        row.revoke_reason = "admin_revoked"
        self.db.commit()
        self.db.refresh(row)
        invalidate_key_cache(key_hash=row.key_hash)
        return row

    def purge_key(self, user_id: int, key_id: int) -> None:
        """硬删除已注销的 Key（仅 status=revoked 可调用；active 强制 revoke 后再走这一步）。

        设计动机：避免已注销记录无限积累。
        安全约束：
          1) active Key 不许 purge（必须先 revoke 以留审计 trace，避免静默删造成失联无追）
          2) 双步走：revoke 落 audit hash 链 → purge 只物理 DELETE 不进 hash 链（单独记录在 soc_audit_logs）
          3) 清缓存避免中间件有遗留条目
        返回被删除记录的快照（给审计用）。
        """
        row = self.db.query(SOCMCPKey).filter(
            SOCMCPKey.id == key_id, SOCMCPKey.user_id == user_id
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="MCP Key 不存在")
        if row.status != "revoked":
            # active 强制走 revoke，不允许绕过。已 expired（active 状态但 days_remaining==0）仍属 active。
            raise HTTPException(
                status_code=409,
                detail="仅可彻底删除已注销的 Key；请先「注销」该 Key"
            )
        # 提关键信息留 audit（key_hash 记上，便于追溯是哪一条 hash 被删；key_prefix 已记）
        snapshot = {
            "id": row.id,
            "user_id": row.user_id,
            "name": row.name,
            "key_prefix": row.key_prefix,
            "key_hash": row.key_hash,
            "status": row.status,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
            "revoke_reason": row.revoke_reason,
        }
        # 清缓存
        invalidate_key_cache(key_hash=row.key_hash)
        # 物理删除
        self.db.delete(row)
        self.db.commit()
        # 快照返回后由调用方落审计（保持 service 与审计系统解耦）

    def admin_purge_key(self, key_id: int) -> dict:
        """admin 硬删除任意用户的已注销 Key。返回快照供审计。"""
        row = self.db.query(SOCMCPKey).filter(SOCMCPKey.id == key_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="MCP Key 不存在")
        if row.status != "revoked":
            raise HTTPException(
                status_code=409,
                detail="仅可彻底删除已注销的 Key；请先「强制注销」该 Key"
            )
        snapshot = {
            "id": row.id,
            "user_id": row.user_id,
            "name": row.name,
            "key_prefix": row.key_prefix,
            "key_hash": row.key_hash,
            "status": row.status,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
            "revoke_reason": row.revoke_reason,
        }
        invalidate_key_cache(key_hash=row.key_hash)
        self.db.delete(row)
        self.db.commit()
        return snapshot

    # ---------- 校验（与模块级 validate_key_cached 等价的直查版）----------

    def validate_key(self, plaintext: str) -> dict:
        """直查校验（不走缓存），返回契约规定的 dict。"""
        return _validate_key_uncached(plaintext, self.db)
