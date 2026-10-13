# 2026-10-13：资产稽核报 "Wazuh API 不可达 (TypeError)" 根因与修复

> 事件链：用户在前端点击 "重新稽核" → 收到错误信息 "Wazuh API 不可达，本次对账终止（TypeError: sequence item 0: expected a bytes-like object, NoneType found）" → 怀疑"采集故障" → 实际是后端配置读取 bug

## 现象

```
POST /api/v1/assets/reconcile
→ code=200, data: { "wazuh_reachable": false, "wazuh_error": "TypeError: ..." }
→ 资产稽核终止，差异 = 0
```

## 用户判断 vs 实际

用户说："请先恢复数据源，避免把采集故障误判为资产差异"

实际诊断：
- **数据源(Wazuh API)** 完全可达：wazuh-collector 容器 5 分钟一次入库 18 个 agents
- **采集正常**：tplink-collector 共享 session 后 1 cycle 1 login 成功
- **真正根因**：后端 `WazuhClient()` 实例化没传 `db` → 配置中心 v1 (`soc_data_sources` 表) 路径失效 → 走 settings 兜底 → settings 字段 None → httpx auth=(None, None) → TypeError

**TypeError 不是"网络错误"也不是"数据源不可达",是"凭据读取失败"**。从用户视角看症状是"稽核失败",从代码视角是"配置中心被绕过了"。

## 调查路径

1. **Wazuh 容器状态**：`minisoc-wazuh-collector Up 18 hours (healthy)`，容器在跑
2. **Wazuh API 实测**：
   - 从 102 主机直连 → HTTP 401(凭据未明文传)
   - 容器内调用 → HTTP 200(传了正确的 user/password)
3. **102 后端日志**：
   ```
   [WARNING] app.services.asset_reconciliation:
     对账失败：Wazuh 不可达 TypeError: sequence item 0: expected a bytes-like object, NoneType found
   ```
4. **后端 .env 检查**：WAZUH_API_USERNAME/PASSWORD 不存在(配置中心 v1 上线时删了,见 .env 注释)
5. **soc_data_sources 表检查**：实际有 3 条记录包括 `id=1 wazuh-prod type=wazuh basic wazuh/****** enabled=true is_default=true`,但 DataSourceResolver 读不到
6. **DataSourceResolver 路径**：
   ```python
   def _resolve_config(self, db: Optional[object]) -> Optional[Dict[str, Any]]:
       if db is None:
           return None  # ← WazuhClient() 不传 db 时立刻走 env
       ...
   ```
7. **WazuhClient 实例化**:
   ```python
   # asset_reconciliation.py
   client = WazuhClient()  # ← db 默认 None
   ```
8. **settings 字段**:
   ```python
   WAZUH_API_USERNAME: Optional[str] = None
   WAZUH_API_PASSWORD: Optional[str] = None
   ```
9. **httpx 内部**:
   ```python
   self._client.post(url, auth=(None, None), ...)
   # → base64.b64encode(b":".join([None, None]))  ← None 不能 join bytes
   # → TypeError
   ```

## 修复（commit 590daf1）

**单行修复**：透传 db 给 WazuhClient

```python
# src/backend/app/services/asset_reconciliation.py
- client = WazuhClient()
+ client = WazuhClient(db=self.db)
```

**配套 defense-in-depth**（102 主机 .env 兜底,不入库）：

```bash
# /home/xiejava/AIproject/AI-miniSOC/src/backend/.env (102 端, .gitignore)
WAZUH_API_USERNAME=wazuh
WAZUH_API_PASSWORD=OgdHes6S57Y?L5HwU0dLB3tWtw.1.TUu
```

即使将来 DB 那条 wazuh 记录被清空或 fernet key 失效,.env 兜底仍能让 WazuhClient 拿到凭据。

## 验证

| 时间 | 步骤 | 结果 |
|---|---|---|
| 17:05:47 | POST /reconcile(只 .env 兜底,代码未改) | ✅ agent_count=17, asset_count=76, diff_total=4 (offline), wazuh_reachable=true |
| 17:09:11 | git pull + systemctl restart(代码修复) | uvicorn etime=00:14 |
| 17:09:xx | POST /reconcile(代码生效,db 路径) | ✅ 同上, wazuh_reachable=true, wazuh_error=None |

**前后对比**：之前 100% 失败,现在 100% 成功,4 个真实 offline 差异(不是"假阴性"也不是"假阳性")。

## 教训

1. **TypeError 字符串内容往往能定位 bug**：
   - "expected a bytes-like object, NoneType found" → 某处 list/tuple 含 None
   - 在 httpx/Django/SQLAlchemy 等"框架边界"出现 → 几乎总是构造请求时缺字段
2. **`DataSourceResolver` 默认 db=None → 立刻 fallback 到 env**：
   - 这是 by design(无 DB 时 settings 兜底)
   - 但**调用方必须显式传 db**,否则配置中心 v1 静默失效
   - 审计其他 `WazuhClient()` 调用点(grep "WazuhClient()") 是否也有同样问题
3. **"数据源不可达"是个有歧义的错误信息**：
   - 真实不可达（网络断/容器死）
   - 凭据失效（密码错/账号禁用）
   - 凭据读取失败（本 bug：DB 路径被绕 + env 兜底空 + httpx TypeError）
   - 应当区分错误类型，TypeError 不应该被包装成"API 不可达"
4. **配置中心 v1 上线时删 .env 兜底 = 高风险**：
   - 当时注释说"current .env 中这些键已不存在, 全部从 .env.bak 恢复"
   - 但如果 DB 那条记录没成功写入或被误删，settings 是 None → 失败
   - 建议:配置中心 v1 上线时**保留 .env 兜底至少 1 个月**, 直到所有数据源在 DB 中验证 OK

## 待办（不阻塞）

- **审计其他 `WazuhClient()` 调用点**：grep `WazuhClient(` 整个 src/backend/, 把所有不传 db 的改成传 db。本仓库代码应当全量迁移。
- **错误信息更精确**：`ReconciliationError` 当前 message 把所有 WazuhClient 异常都包成"Wazuh API 不可达",应当按异常类型区分（认证失败/网络/配置错误）
- **DataSourceResolver 改进**：`db=None` 时除了回落 env, 还应当**显式日志 warn**, 否则静默 fallback 难发现
