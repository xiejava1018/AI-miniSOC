# 2026-10-13：WazuhClient 调用点全量迁移 + 配置中心 v1 验收（技术债清偿）

> 前置：2026-10-13 上午修复资产稽核 TypeError（commit 590daf1）时识别出 11+ 调用点共用"绕过配置中心"的全局单例。用户拍板"连测试一起全做，技术债不欠"。

## 验收结果（决定性证据）

**删除 102 `.env` 的 `WAZUH_API_USERNAME/PASSWORD` 兜底后**（凭据唯一来源 = soc_data_sources 表）：

```
POST /api/v1/assets/reconcile → 200
  agent_count: 17, asset_count: 76, linked_count: 17, diff_total: 4
  wazuh_reachable: True, wazuh_error: None

后端日志:
  POST https://192.168.0.40:55000/security/user/authenticate 200 OK
  对账完成 run_id=d63ad758 agents=17 assets=76 diffs=4
```

**这才是"迁移成功"的证明**——不删兜底，迁移成功与否根本看不出来（兜底也能跑）。

## 改动（commit f167c4a）

### 工厂语义 v2（修"首次固化"雷）

```python
# get_wazuh_client(db=None) 的 4 条语义：
1. 单例不存在 → 创建
2. "无 db"单例 + 传 db 调用 → 关旧建新（升级到配置中心路径）
3. 带 db 单例存活 >60s → 重建（soc_data_sources 变更 <=60s 生效，
   与 DataSourceResolver._CACHE_TTL 对齐）
4. 无 db 调用永远复用 → 不降级
```

### 10 文件 25 处调用点迁移

| 文件 | 处数 | db 来源 |
|---|---|---|
| services/asset_sync.py | 3 | self.db |
| services/wazuh_agent_sync.py | 2 | self.db |
| services/wazuh_sca_sync.py | 3 | classmethod db 形参 |
| services/wazuh_sca_sync_v2.py | 3 | classmethod db 形参 |
| services/wazuh_scap_sync.py | 2 | classmethod db 形参 |
| services/asset_enrichment.py | 1 | self.db（**to_thread 线程边界**） |
| services/alert_query.py | 1 | self.db |
| api/data_sync.py | 1 | Depends(get_db) |
| api/sca.py | 1 | Depends(get_db) |
| api/vulnerabilities.py | 1 | Depends(get_db) |

### 测试：42 个全绿

- 5 个测试文件 mock 目标改为 patch **使用方模块**的 `get_wazuh_client`
- test_endpoint_process_builder fake 加 `__init__(*args, **kwargs)`
- test_asset_sync 3 处过期断言修正（"在线"→"online"，与 status_map 对齐，预存失败顺手修）
- 新增 test_wazuh_client_factory.py 9 用例（配置中心路径 / 工厂 4 语义 / 精确异常）

## 踩坑（本轮新增教训）

### 1. from-import 本地绑定 vs patch 源模块属性

```python
# 服务模块: from app.services.wazuh_client import get_wazuh_client
# 测试:     patch("app.services.wazuh_client.get_wazuh_client")  # ✗ 无效!
```

`from X import Y` 在导入方模块建了**本地绑定**。patch X.Y 改的是源模块属性，**不影响已导入的名字**。首轮 wo2 测试 2 个失败（DID NOT RAISE）+ 1 个"成功"用例实际在打真实 Wazuh API（100s vs 修复后 7s）就是这个坑。

**正确写法**：patch **使用方模块**的绑定：
```python
patch("app.services.wazuh_agent_sync.get_wazuh_client")  # ✓
```

### 2. SQLAlchemy session 线程边界（to_thread）

`asset_enrichment.py` 在 `asyncio.to_thread` 里调 Wazuh。`get_wazuh_client(db=self.db)` 内部 resolver 会用 db 查 soc_data_sources——**session 非线程安全**。正确做法：

```python
# 事件循环线程先拿 client（db 查询在这里发生）
client = get_wazuh_client(db=self.db)
# 只把同步的 client 方法丢进线程
sysinfo = await asyncio.to_thread(client.get_agent_sysinfo, asset.wazuh_agent_id)
```

### 3. 验收标准：删兜底才算数

迁移"成功"的唯一可信验收 = **删除 fallback 后功能仍然通**。保留兜底跑通的迁移无法自证。102 端 `.env.bak-20261013-pre-fallback-removal` 保留作回滚素材。

## 回滚路径

```bash
# 102:
cp src/backend/.env.bak-20261013-pre-fallback-removal src/backend/.env
sudo systemctl restart aisoc-backend
# git: revert f167c4a
```
