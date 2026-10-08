# 2026-10-08 Wazuh Collector 假绿活体案例修复

**状态**: ✅ 已修复并部署 102
**关联**: CLAUDE.md §4.13（已知未修的"假绿" → 本次实锤并根治）

---

## 0. 触发

另一个 agent 在排查 102 wazuh-collector 日志时发现：

```
同步成功: source=wazuh, type=baseline ...
同步成功: {'code': 400, 'msg': '不支持的数据类型: baseline，当前支持: asset, port, discovery, nat_mapping', 'data': None}
```

每 5 分钟推一次、每次都被后端 400 拒收、但采集器**照例打"同步成功"**——CLAUDE.md §4.13 记录的"假绿"在 102 实锤。

## 1. 假绿活体诊断

### 1.1 修复前基线（102 soc_source_health 表）

```
       source_key        | source_type | success_count | failure_count |          err
-------------------------+-------------+---------------+---------------+----------------------------------------------
 wazuh:baseline          | wazuh       |             0 |          2117 | unsupported data_type: baseline
 wazuh:vulnerability     | wazuh       |             0 |          2117 | unsupported data_type: vulnerability
 wazuh:agents            | wazuh       |          8192 |          5359 | PendingRollbackError (代码 OH-6.1b 之后部分缓解)
```

**OH-6.1b 补丁**（在 `app/api/data_sync.py:38-58`）**已经记了 failure**——`soc_source_health` 表里 `wazuh:baseline` / `wazuh:vulnerability` 的 failure 2117 是 OH-6.1b 之后才有的。

**所以严格说**：今天"假绿"已经**部分缓解**（面板**不会全绿**了，但**没人在看**）；但**业务数据缺失 6 周是真的**。

### 1.2 根因（三层叠加）

1. **链路设计错位**：SCA/baseline 应该走 `Vulnerability(type=sca)` OpenSearch 链路（T5 已定），但 `wazuh-collector` 还在按老配置推 `data_type=baseline` → `/data/sync`
2. **配置未迁移**：T5（2026-08-15）把 vulnerability 从 Wazuh API 迁到 OpenSearch 之后，**采集器侧配置没通知到**——`wazuh-collector` 还在 `config.yaml` 配 `[asset, vulnerability, baseline]`
3. **sync_client 容错太宽**：102 容器里跑的是旧版 `sync_client.py`，`else: result = body` 兜底——HTTP 200 + code!=200 也 return body，**采集器看不到失败**。本仓库 main 上的新版虽然严判 envelope，但 102 容器**没刷新**（pip install -e 装的是 base 旧版）

## 2. 修复

### 2.1 代码改动

| 文件 | 改动 |
|---|---|
| `src/collectors/wazuh/config.yaml` | `types:` 移除 `vulnerability` / `baseline`，只留 `asset`；顺便修 `minisoc.url` 从 192.168.0.128（死值）→ 192.168.0.102（实际生效值） |
| `src/collectors/wazuh/src/wazuh_collector/collector.py:167` | 默认 `collect_types` 同样收敛为 `["asset"]`（防止有人手改 yaml 删字段） |
| `src/collectors/base/collector_framework/sync_client.py:67-78` | 严判 envelope 形态：非 dict / 无 `code` / `data` 非 dict / `code!=200` **全部走重试到 raise**——杜绝老逻辑 `else: return body` 假绿 |

### 2.2 部署

- 102 走 `deploy/deploy_collectors.sh` 标准流程（慢网下 git pull 失败，scp 三个文件 fallback）
- 三个采集器（wazuh / tplink / scanner）全部重建，**全部 healthy**
- wazuh-collector 镜像从 2026-08-26（6 周）刷新到 2026-10-08

### 2.3 修复后稳态（5 分钟观察窗）

```
       source_key        | failure_count | last_failure_at
-------------------------+---------------+--------------------
 wazuh:baseline          |          2119 | 2026-10-08 20:20:30  ← 停在这一刻（容器重建时残留）
 wazuh:vulnerability     |          2119 | 2026-10-08 20:20:29  ← 停在这一刻
 wazuh:agents            |          5370 | 2026-10-08 20:31:11  ← 持续 +2/轮（真实 bug 见 §3）
```

`wazuh:baseline` / `wazuh:vulnerability` 的 `last_failure_at` 在 5 分钟稳态窗口**完全没动**——采集器**真的不再推这两种 data_type**。假绿**根治**。

## 3. 顺手暴露的 bug：wazuh:agents UniqueViolation（不在本次 scope）

修复后日志里 `wazuh:agents` **真正失败**了（之前假绿时是 PendingRollbackError + 部分成功算假成功）：

```
(psycopg2.errors.UniqueViolation) duplicate key value violates unique constraint "uq_soc_assets_agent_id"
DETAIL:  Key (wazuh_agent_id)=(010) already exists.

[SQL: UPDATE soc_assets SET ... wazuh_agent_id='010' WHERE soc_assets.id = '70ce2f10-...'::UUID]
```

**根因**：`AssetSyncHandler.handle()` 在批量 upsert 时，**同一批内**两个不同 asset 行试图把 `wazuh_agent_id` 设成同一个值（'010'）→ 第二个 UPDATE 触发 `uq_soc_assets_agent_id` 唯一约束违反 → 整个 SQLAlchemy session 进入 `PendingRollbackError` → **整批**回滚 → 全 500。

**为什么之前没暴露**：sync_client 把 code=400/500 都"成功"地打日志，**handler 内部错误是 500**但**没记**——直到今天 sync_client 修复了才看见。

**严重度**：wazuh:agents 已有 6 周持续 1/3 失败（success 8192 / failure 5359 = 39% 失败率），**资产同步真数据是 60% 完整**。

**建议下一步**：单开一个 session 修 `AssetSyncHandler.handle()` 的批量 upsert——是按 (wazuh_agent_id) 分组后单条 upsert，还是改成先 SELECT 再分批 UPDATE。**不在本次 scope**。

## 4. 教训补强

- **CLAUDE.md §4.13**（"sync_client 假绿"）应该改写为"已修复"——本次 commit 治住了根因
- **新教训**："链路迁移（T5）没通知到采集器"——**任何架构迁移都要同时改三处**：①代码 ②配置 ③所有依赖该配置的下游（采集器/容器/CI）
- **新教训**："pip install -e 的镜像缓存"——`base/collector_framework/` 改了代码，但**采集器镜像的 site-packages 不会自动刷新**，必须 `docker compose build` 重建。102 上 wazuh-collector 镜像就是 6 周前 build 的，里面装的是当时 base 的版本
