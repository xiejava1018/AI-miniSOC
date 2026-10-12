# PR1 实施契约（三 agent 并行的对接界面）

> 本文件是 PR1 并行实施的唯一接口契约，实现必须严格符合签名，内部实现自由。
> 设计文档：`docs/design/2026-10-12-用户中心重构与MCP-Key管理设计.md`（v1.2，必读）

## 环境

- Python: `../../venv/bin/python`（src/backend 下）；SQLAlchemy 2.0.54 / mcp 1.19.0
- dev DB: 远端 `AI-miniSOC-testdb`（.env 已配）；pytest 库: `AI-miniSOC-db_test`（同主机）
- alembic 单 head: `c3d4e5f6a7b8`（新迁移 down_revision 挂它）
- 响应 envelope: `{code,msg,data}` HTTP 恒 200（code 401/403/404/409/422 业务码）
- 审计: `@log_audit` 装饰器（参考 `app/api/users.py` 现有用法）

## Agent A 产出（数据层）——B 和 C 依赖此界面

### 1. `app/models/mcp_key.py`

```python
class SOCMCPKey(Base):
    __tablename__ = "soc_mcp_keys"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("soc_users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(50), nullable=False)          # 应用层唯一(active 内,同 user)
    key_prefix = Column(String(16), nullable=False)     # "sk-mcp-"+4位
    key_hash = Column(String(255), nullable=False, unique=True)  # sha256 hex
    status = Column(String(20), nullable=False, default="active")  # active/revoked
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    revoke_reason = Column(String(100))  # user_revoked/admin_revoked/admin_proxy
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```
（soc_users.id 是 Integer——保持一致；`app/models/__init__.py` 要注册 import）

### 2. `app/services/mcp_key_service.py`

```python
class MCPKeyService:
    def __init__(self, db: Session): ...
    def list_keys(self, user_id: int) -> list[SOCMCPKey]           # 不含明文
    def create_key(self, user_id: int, name: str, validity_days: int) -> tuple[SOCMCPKey, str]
        # 校验: name 1-50 且 active 内同名 409; 数量上限 409; validity 范围 422
        # 生成 sk-mcp-{secrets.token_urlsafe(32)[:40]} → 64位hex hash; 返回 (记录, 明文一次性)
    def extend_key(self, user_id: int, key_id: int, new_validity_days: int) -> SOCMCPKey
        # 仅 active 可延期,否则 409; 新 expires_at=now+days; 校验上限; 清缓存
    def revoke_key(self, user_id: int, key_id: int, reason="user_revoked") -> SOCMCPKey
        # 幂等:已 revoked 直接返回; 设 status/revoked_at/reason; 清缓存
    def admin_revoke_key(self, key_id: int) -> SOCMCPKey            # reason=admin_revoked; 清缓存
    # ↓ C(MCP中间件)用:
    def validate_key(self, plaintext: str) -> dict
        # {"ok":bool,"error":"key_invalid|key_revoked|key_expired|user_disabled","user_id":int,"username":str,"role_code":str,"key_id":int}
        # 未认证通过时 user_id 等为 None

# 模块级(进程内共享,C 的中间件与 B 的 API 同进程):
def get_config(key: str, default)          # 读 soc_system_configs(带60s内存缓存): mcp.key.* 5项+mcp.auth.required
def invalidate_key_cache(key_hash: str=None, user_id: int=None)
def validate_key_cached(plaintext: str) -> dict   # validate_key + key_hash级TTL缓存(60s,配置mcp.key.cache_ttl_seconds)
def touch_last_used(key_id: int)                  # 异步写回,失败静默
```

配置中心默认项（迁移种子 INSERT，**bind.execute 带参数，JOIN 结构不硬编码 id**）：
`mcp.auth.required=false` · `mcp.key.max_per_user=5` · `mcp.key.max_validity_days=365` · `mcp.key.min_validity_days=1` · `mcp.key.cache_ttl_seconds=60` · `mcp.key.failure_lock_threshold=10` · `mcp.key.failure_lock_minutes=15`
（先查 `soc_system_configs` 现有行的结构照抄列名/类型，幂等：已存在则跳过）

### 3. `app/schemas/mcp_key.py`

```python
MCPKeyCreate(BaseModel): name: str(1-50); validity_days: int(gt=0)
MCPKeyExtend(BaseModel): new_validity_days: int(gt=0)
MCPKeyResponse: id,name,key_prefix,status,days_remaining,expires_at,last_used_at,created_at
MCPKeyCreatedResponse(MCPKeyResponse): key: str   # 明文仅此一次
```
（另含 ProfileUpdate/ChangePassword schema 供 B 用：B 也可自建在 `app/schemas/user_profile.py`，二选一，勿重复）

### 4. alembic 迁移 `xxxx_create_soc_mcp_keys.py`：down_revision = "c3d4e5f6a7b8"

### 5. 单元测试 `tests/unit/test_mcp_key_service.py`（A 负责跑绿）

## Agent B 产出（API 层）——依赖 A 的 import 界面

`app/api/users.py` 追加（**路由注册顺序：/me/* 必须在 /{user_id} 之前**，否则被吞）：

```
GET    /users/me                    # 完整字段: id,username,nick_name,email,phone,avatar,gender,role(code+name),department_name,last_login,created_at
PUT    /users/me                    # 白名单: nick_name,phone,email,avatar,gender;传越权字段→422+detail列名
POST   /users/me/change-password    # 旧密码错→401(计失败,连续5次锁15分钟);新密码<6位→422;成功→200+审计 password.change.success/fail
GET    /users/me/mcp-keys           # 本人列表
POST   /users/me/mcp-keys           # viewer/auditor→403;成功→MCPKeyCreatedResponse
POST   /users/me/mcp-keys/{id}/extend
DELETE /users/me/mcp-keys/{id}
# admin:
GET    /users/{user_id}/mcp-keys    # require_role("admin")
POST   /users/{user_id}/mcp-keys    # admin 代发
DELETE /users/{user_id}/mcp-keys/{id}
```
全部 `@log_audit`。测试 `tests/integration/test_users_me_api.py`（B 负责跑绿）。

## Agent C 产出（MCP 中间件）——依赖 A 的 validate 界面

`app/mcp/server.py`（保留现有双 transport 结构）+ `app/mcp/token_manager.py`：

1. Starlette 纯 ASGI/`BaseHTTPMiddleware` 中间件包住组合 app：
   - 无 Authorization 头：`mcp.auth.required`(A 的 get_config)=false→放行(现状); true→401
   - 有 Bearer sk-mcp-：`validate_key_cached`（DB 调用放 `anyio.to_thread.run_sync`，别堵 MCP 的事件循环）
   - ok→签 JWT（复用 `app/core/security.py` 的 create_access_token，附 jti）→ `token_manager.inject_identity(user_id, username, token)`（注入的凭证**优先级高于** set_mcp_credentials 会话凭证）；`touch_last_used` 后台化
   - 失败→401 JSON `{"error":"key_invalid|key_revoked|key_expired|user_disabled"}`；按 IP 失败计数（模块级 dict，超 `failure_lock_threshold` 锁 `failure_lock_minutes`）→ 429
2. `token_manager.py` 增加 `inject_identity()` / `clear_identity()`：与现有会话凭证共存，注入优先；`get_token()` 优先返回注入凭证
3. 单元测试 `tests/unit/test_mcp_key_middleware.py`（monkeypatch validate，不发真网络）

## 集成验证（父 agent 做）

pytest 全绿 → 重启后端 → curl：申请→带Key调 /mcp initialize→注销→下一请求401。
