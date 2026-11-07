# 2026-11-07：影子资产渲染空白修复 + CI/CD runner 自更新卡死

## 一、影子资产"有数量无内容"

### 现象

`http://192.168.0.102:3006/#/assets/reconciliation`（资产稽核）统计卡片显示"影子 2"，
但表格里看不到是哪两条资产，也没有纳管入口。

### 排查路径（先证伪"后端没数据"）

生产库直查（**注意：本地 Mac `.env` 连的是远端 testdb，≠ 生产库**）：

```bash
ssh xiejava@192.168.0.102 \
  "PGPASSWORD='***' psql -h 127.0.0.1 -p 5432 -U aisoc -d 'AI-miniSOC-db' \
   -c \"SELECT reconciliation_type,status,count(*) FROM soc_asset_reconciliations GROUP BY 1,2;\""
# offline | ignored | 1
# offline | resolved | 7
# shadow  | pending  | 2     ← 就是这 2 条
```

两条 shadow 的 `details`：

```json
{
  "source": "scanner",
  "asset_ip": "192.168.0.2",
  "mac_address": "64:6E:97:B1:40:F2",
  "os_guess": null,
  "exposure": "internal",
  "finding_id": 138,
  "scanner_id": "7abb52cb-...",
  "scan_task_uuid": "4909459f-..."
}
```

`192.168.0.3` 同结构（`finding_id=139`，MAC `64:6E:97:B1:3A:EF`）。
两者都不在 `soc_assets` 里 —— 是真的影子资产。

### 根因：shadow 有两条来源路径，`details` 结构完全不同

| 来源 | `details` 形状 | 产出位置 |
|---|---|---|
| Wazuh 主路 | `agent.{id,name,ip,status,os_name}` + `ledger.*` | `AssetReconciliationService.run()` 遍历 agents |
| **scanner 路径** | `asset_ip,mac_address,os_guess,exposure,finding_id` | `reconcile_scanner_findings()` |

前端只认第一条。`src/frontend/src/views/asset/reconciliation/index.vue` 里：

```js
// 改前
const objName = (row) => row.details?.ledger?.name || row.details?.agent?.name || '（未命名）'
const objIp   = (row) => row.details?.ledger?.asset_ip || row.details?.agent?.ip || ''
```

scanner 来源 → `details.agent` / `details.ledger` 都是 `undefined` → 落到兜底：
- 对象列：`（未命名）` + 空 IP
- 差异详情列（`v-else` 兜底分支）：`Agent undefined · 系统未知 · 状态 undefined`

统计卡片按**行数**计数，所以"影子 2"是对的，但表格内容全空。
**这正是 CLAUDE.md §4.1「假绿」的形态：数字对，内容缺。**

### 顺带发现 3 个问题

1. **`objName`/`objIp` 不分来源** → 修：按 `details.source === 'scanner'` 分支
2. **差异详情列只有 3 个分支**（mismatch/offline/兜底） → 修：加 scanner 分支
3. **scanner shadow 只写 `created_at`**，没写 `first_seen_at`/`last_seen_at`/`last_seen_run_id`/`occurrence_count`
   → 前端「老化」列显示 `—`；且 `_upsert_diff` 的 dedup 口径（`last_seen_run_id`）拿不到
   → 修：与 Wazuh 主路保持一致，3 个时间戳都写
4. **没有纳管入口**：shadow 行只有「已处理/确认/忽略」，想纳管得自己去 `/scan/findings`
   页面翻 finding，路径断在这里 → 修：补「纳管」按钮 + 弹窗，复用已有的
   `POST /scan/findings/{id}/adopt`（后端已写审计日志 `action="asset_adopt"`），
   成功后把该条差异置 `resolved`，队列自动收敛

### 生产库回填

存量 2 行 `first_seen_at`/`last_seen_at` 为 NULL，用底层 `soc_scan_findings.created_at` 回填
（**取 finding 的时间而非对账行的 created_at** —— 后者是 11-07，前者才是真实首次发现时间 11-04）：

```sql
WITH f AS (
  SELECT r.id AS recon_id, MIN(f2.created_at) AS first_seen, MAX(f2.created_at) AS last_seen
  FROM soc_asset_reconciliations r
  JOIN soc_scan_findings f2
    ON f2.asset_ip = r.details->>'asset_ip'
   AND f2.id = (r.details->>'finding_id')::int
  WHERE r.reconciliation_type='shadow' AND r.details->>'source'='scanner'
    AND r.first_seen_at IS NULL
  GROUP BY r.id
)
UPDATE soc_asset_reconciliations r
SET first_seen_at=f.first_seen, last_seen_at=f.last_seen, last_seen_run_id=r.run_id
FROM f WHERE r.id=f.recon_id;
```

### 教训

- **同一业务概念有多条来源路径时，`details` 的 schema 必须显式分型**，
  前端不能靠"取不到就兜底"糊弄 —— 兜底会静默产生空白内容。
- **统计卡片按行数计数 ≠ 内容可见**。计数正确而渲染空白时，
  要怀疑的是"同名词在不同来源下结构不同"，而不是"数据没进来"。
- **类型定义要跟得上**：这次顺带发现 `ReconciliationItem` TS 类型缺
  `first_seen_at`/`last_seen_at`（前端已在用但类型里没有，`vue-tsc` 报 TS2339），
  一并补上，也顺手修掉 2 个既有类型报错。

## 二、CI/CD：self-hosted runner 自更新卡死，部署静默跳过

### 现象

push 后 CI 全绿，但 CD run 永远 `pending`，`jobs=0`，部署没发生。

```
42370983607 | CD | 5c038169 | pending/null    | jobs=0
42370972468 | CD | 5c038169 | completed/cancelled | jobs=0
42335442360 | CD | 4b2f5531 | completed/cancelled | jobs=0
42043257227 | CD | e9556fa4 | queued/null      | jobs=1   ← 卡了 2 天
41844801062 | CD | 78edd4e8 | completed/success | jobs=1   ← 11-04 还正常
```

**`jobs=0` 的 run 永远不会被 runner 领走**（GitHub 压根没创建 job），
`jobs=1` 但 `runner_name` 为空、`status=queued` 才是"排队等 runner"。

### 根因

runner 版本落后且自更新失败：

```
[2026-11-06 14:30:24Z ERR SelfUpdater] Runner package
  '.../actions-runner-linux-x64-2.338.2.tar.gz' failed after 3 download attempts
  (HttpClient.Timeout of 100 seconds elapsing)
[2026-11-07 08:54:22Z INFO Terminal] WRITE LINE: Current runner version: '2.336.0'
[2026-11-07 08:54:22Z INFO Terminal] WRITE LINE: Listening for Jobs
```

即 **§4.14 的慢网问题**（102→GitHub 极慢）打死了 runner 自更新。
`runner1.tar.gz` 后来在 14:30 下载成功了（27MB），但 runner 已经进入
「重启 → 重新监听 → 再次收到更新指令 → 再超时」的循环，**Worker 从 11-04 之后再没起来过**。

### 处置

1. **重启 runner**：`sudo -n systemctl restart` 不通（sudoers 只放行了 `aisoc-backend`），
   但 runner 进程跑在 `xiejava` 用户下 → 直接 `kill <Runner.Listener PID>`，
   `RunnerService.js` 会自动拉起新的 Listener（`Runner_20261107-121819-utc.log`）。
   重启后能正常 "Listening for Jobs"，但 `jobs=0` 的 run 依旧领不走（GitHub 没建 job）。
2. **手动部署**（CLAUDE.md §2.3 文档路径）：server 直接 `git fetch --depth=20 origin master`
   → 拿到 `5c038169`（这次 fetch 成功了）→ `bash deploy/deploy.sh <sha> "说明"` → 部署成功。

```bash
ssh xiejava@192.168.0.102 \
  'cd /home/xiejava/AIproject/AI-miniSOC && \
   nohup bash deploy/deploy.sh 5c038169... "手动部署" > /tmp/deploy-manual.log 2>&1 &'
# [2026-11-07 12:20:28] ====== 部署成功: 5c038169... ======
```

### 待修（未做）

- runner 版本锁在 2.336.0，每次 GitHub 推新版就复现一次。
  **要么** 定期手动升级 runner，**要么** 在 runner 上关掉自更新
  （`.runner` 旁加 `--disableupdate`），把升级变成显式的人工动作。
- `sudoers` 没放行 runner 的 systemctl，需要运维时得走 `kill` 这条野路子，
  建议补一条 `NOPASSWD: /usr/bin/systemctl restart actions.runner.*`。
- CD 触发条件 `workflow_run` + `concurrency` 组合下会出现"一个 cancelled + 一个 pending(无 job)"，
  **pending 无 job 不会被 runner 领走也不会自动失败** → 部署静默跳过，无人知晓。
  建议给 CD 加个超时告警（pending 超过 N 分钟就告警）。

### 教训

- **CI 全绿 ≠ 已部署**。必须另行验证 server 上的 `git rev-parse HEAD` 与部署日志。
- `jobs=0` 和 `status=queued` 是两种不同的"没跑起来"，排查时要分开看。
- 慢网环境下，**依赖自动下载新版本的基础设施组件（runner）会静默腐烂**，
  且症状出现在下游（部署不发生）而不是自身。

## 变更清单

| 文件 | 变更 |
|---|---|
| `src/backend/app/services/asset_reconciliation.py` | scanner shadow 补写 3 个老化字段 |
| `src/frontend/src/api/asset.ts` | `ReconciliationItem.details` 补 scanner 字段 + 老化字段 |
| `src/frontend/src/views/asset/reconciliation/index.vue` | 分来源渲染 + scanner 详情列 + 「纳管」按钮/弹窗 |

commit `5c038169`，手动部署至 192.168.0.102。

## 验证

- `npx vite build` ✅
- `pytest tests/test_reconcile_scanner.py tests/test_recon_upsert_dedup.py` → **23 passed**
- `vue-tsc` 本文件 9 个报错均为改动前既有（stash 对比确认），改动顺带修掉 2 个
- 生产库 2 行回填后：`ip=192.168.0.2/192.168.0.3`，`first_seen_at=2026-11-04 19:51`
- 部署后 `dist/assets/index-C61qhGux.js` 含「扫描发现（未纳管）」+「一键纳管为资产」
