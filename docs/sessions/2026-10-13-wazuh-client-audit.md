# 2026-10-13：WazuhClient() 调用点全量审计与异常分级

> 事件链：用户要求审计"其他 WazuhClient() 调用点"是否有同样问题 → 全后端 grep 出 3 处 + 11+ 共用全局单例 → 修 2 处真正会爆的 + 加异常分级 + 加 lazy 工厂

## 审计范围

`grep -rn 'WazuhClient(' src/backend/ --include='*.py'`

### WazuhClient 类实例化点（3 处）

| 位置 | 状态 | 修复 |
|---|---|---|
| `src/backend/app/services/asset_reconciliation.py:237` | ✅ commit 590daf1（上一轮） | `WazuhClient(db=self.db)` |
| `src/backend/app/services/graph/builders.py:1199` | ✅ commit 8eda281（本次） | `WazuhClient(db=self.db)` |
| `src/backend/app/services/wazuh_client.py:276` | ⚠️ 架构债 | 全局单例 `wazuh_client = WazuhClient()`，**保留**（向后兼容 11+ 调用点） |

### wazuh_client 全局单例使用点（11+ 处）

```
src/backend/app/api/data_sync.py:132           wazuh_client.get_agents()
src/backend/app/api/sca.py:71                  wazuh_client.get_agents()
src/backend/app/api/vulnerabilities.py:1073    wazuh_client.get_agent_info()
src/backend/app/services/wazuh_sca_sync_v2.py  (3 处)
src/backend/app/services/asset_sync.py         (3 处)
src/backend/app/services/wazuh_sca_sync.py     (3 处)
src/backend/app/services/wazuh_agent_sync.py   (2 处)
src/backend/app/services/wazuh_scap_sync.py    (2 处)
src/backend/app/services/asset_enrichment.py   wazuh_client.get_agent_sysinfo
src/backend/app/services/alert_query.py        wazuh_client.get_agents()
```

**全部走 .env 兜底，不走配置中心 v1**。当前 .env 已配 WAZUH_API_USERNAME/PASSWORD（commit 78db936 之前的兜底），稳定运行。

## 修复内容（commit 8eda281）

### 1. 异常分级（wazuh_client.py）

新增三个异常类区分故障类型：

```python
class WazuhClientError(RuntimeError): ...
class WazuhConfigError(WazuhClientError): ...    # 凭据读取失败
class WazuhAuthError(WazuhClientError): ...      # Wazuh 401 拒绝
class WazuhNetworkError(WazuhClientError): ...   # 网络问题
```

`_get_token()` 内部精确抛错：

```python
if not self.username or not self.password:
    raise WazuhConfigError("Wazuh 凭据未配置 ...")

try:
    response = self._client.post(url, auth=..., headers=...)
except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
    raise WazuhNetworkError(...) from e
except httpx.HTTPError as e:
    raise WazuhNetworkError(...) from e

if response.status_code == 401:
    raise WazuhAuthError("Wazuh API 401 拒绝认证: ...")
```

### 2. 资产稽核异常分类提示（asset_reconciliation.py）

`ReconciliationError` message 按异常类型区分：

| 异常类型 | 错误信息 |
|---|---|
| `WazuhConfigError` | "Wazuh 配置读取失败（不是数据源不可达），本次对账终止。请检查 soc_data_sources 表 type=wazuh 记录 / .env WAZUH_API_USERNAME/PASSWORD" |
| `WazuhAuthError` | "Wazuh API 拒绝认证（不是数据源不可达），本次对账终止。wazuh 用户密码可能已变更" |
| `WazuhNetworkError` | "Wazuh API 不可达（网络问题），本次对账终止。请检查 192.168.0.40:55000 可达性 + wazuh-collector 容器状态" |
| 其他 | 原有"Wazuh API 不可达"信息 |

### 3. graph builders 透传 db（graph/builders.py）

`EndpointProcessBuilder.rebuild_all()` 内部：

```python
# 旧：
client = WazuhClient()
# 新：
client = WazuhClient(db=self.db)  # 走配置中心 v1
```

`EndpointProcessBuilder.__init__(db: Session, ...)` 已有 db 参数，`self.db` 可用。

### 4. lazy 工厂（wazuh_client.py）

新增 `get_wazuh_client(db=None, use_mock_data=False)` 工厂：

```python
_wazuh_client_singleton: Optional[WazuhClient] = None
_wazuh_client_lock = threading.Lock()

def get_wazuh_client(db=None, use_mock_data=False) -> WazuhClient:
    global _wazuh_client_singleton
    with _wazuh_client_lock:
        if _wazuh_client_singleton is None:
            _wazuh_client_singleton = WazuhClient(db=db, use_mock_data=use_mock_data)
        return _wazuh_client_singleton
```

未来调用点迁移路径：
```python
# 旧：
from app.services.wazuh_client import wazuh_client
wazuh_client.get_agents()
# 新：
from app.services.wazuh_client import get_wazuh_client
get_wazuh_client(db=db).get_agents()
```

旧 `wazuh_client` 全局单例保留（向后兼容 11+ 调用点不动）。

## 验证

| 步骤 | 结果 |
|---|---|
| git pull + systemctl restart | uvicorn etime=00:10（新进程） |
| POST /api/v1/assets/reconcile | HTTP 200, agent_count=17, diff_total=4, wazuh_reachable=True |
| Wazuh*Error 异常路径 | 未触发（凭据正常 + 网络通），但类型已就位下次生效 |

## 架构债（未完成）

11+ 处 `wazuh_client.get_xxx()` 调用点仍走 .env 兜底。后续 PR 一次到位迁移到 `get_wazuh_client(db=...)`：

- `src/backend/app/services/asset_sync.py:28` 等 3 处
- `src/backend/app/services/wazuh_sca_sync.py:63` 等 3 处
- `src/backend/app/services/wazuh_sca_sync_v2.py:52` 等 3 处
- `src/backend/app/services/wazuh_agent_sync.py:36,170` 等 2 处
- `src/backend/app/services/wazuh_scap_sync.py:74,149` 等 2 处
- `src/backend/app/services/asset_enrichment.py:31`
- `src/backend/app/services/alert_query.py:441`
- `src/backend/app/api/data_sync.py:132`
- `src/backend/app/api/sca.py:71`
- `src/backend/app/api/vulnerabilities.py:1073`

每个都需要：
1. 看所在函数是否接 db 参数（service 方法一般有 `self.db`，API 端点一般 `Depends(get_db)`）
2. 改为 `get_wazuh_client(db=db_or_self_db).get_xxx()`
3. 加单元测试验证配置中心路径生效

**本次不做的原因**：
- 11+ 文件改动 + 集成测试 + 单测 mock，工作量 1+ 人天
- 当前 .env 兜底有效，业务稳定
- 异常分级已就位，下次有人忘了传 db 也能拿到精确错误信息
- 集中迁移应该单独一个 PR 走完（"配置中心 v1 调用点迁移" 主题）

## 教训

1. **全局单例在 import 时创建 = db 永远传不进去**：
   - 任何需要 db session 才能正确初始化的客户端不能做模块级单例
   - 必须 lazy 初始化（首次调用时建）或 factory
2. **异常分类是错误处理的第一性原理**：
   - 把所有异常包成"X 不可达"是错误信息的反模式
   - 应当：网络/凭据/配置/认证 4 类区分，让用户能定位问题
3. **审计同类问题不要只修一处**：
   - 找到一个 WazuhClient() 不传 db 就要 grep 全部调用点
   - 但**全量修改的 ROI 要算**——架构债写进笔记留给后续 PR 比一次性大爆炸更稳
4. **配置中心 v1 上线时检查所有调用方**：
   - CLAUDE.md §1.7 路径（soc_data_sources 表）需要每个调用方都显式传 db
   - 仅靠"我加了一条记录"不够，要看谁在用这个类
