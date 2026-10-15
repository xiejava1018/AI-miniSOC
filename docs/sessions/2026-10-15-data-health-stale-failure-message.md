# 2026-10-15 数据健康"最近失败 2026-10-12 23:06" 长期占位

**状态**: ✅ A1 已落地（DB 标 superseded）；A2 代码已改（data_health.py 7 天→24h），**待部署**
**关联**: CLAUDE.md §1.1 envelope / §0 硬事实 / §4 教训

---

## 0. 触发

操作员在 `http://192.168.0.102:3006/#/ops/data-health` 看到：

```
数据源健康
  wazuh:agents
    最近失败 2026-10-12 23:06: sequence item 0: expected a bytes-like object, NoneType found
    成功 10206 / 失败 5425
```

但 3 天来没有新的真失败，且最近 wazuh 资产同步成功（最近成功 2026-10-15 21:22）。
**告警是历史任务，不是当前故障**。

---

## 1. 根因（三层叠加）

### 1.1 panel 显示源是 `soc_sync_tasks` 表，不是 `soc_source_health`

```python
# src/backend/app/api/data_health.py:333-336
"last_failure_at": _iso(last_failed_task.created_at) if last_failed_task else None,
"last_failure_message": (last_failed_task.error_message or None) if last_failed_task else None,
```

`sync_freshness` 这个字段（前端 `data-health/index.vue:111` 读的是它）从 `soc_sync_tasks` 表取 `last_failed_task`——**跟 `soc_source_health.last_failure_at` 是两个完全独立的字段**。

### 1.2 那 6 条 `failed` task 是 10-12 23:06 你手动点"立即同步"触发的，不是采集器

`sync_type=manual` 的 6 条 task 全部 `failed` 时间为 `2026-10-12 23:06:56 ~ 23:06:59`（**3 秒内集中失败 6 次**——典型的"点了 6 下按钮"）。

`sync_type=collector`（wazuh-collector 5 分钟自动循环）**最近 1 天 575 条全 completed**——采集器链路完全正常。

### 1.3 当时失败的根因是 Wazuh 凭据 None（CLAUDE.md §4 已记）

```
2026-10-12 23:06:57,028 [ERROR] app.services.asset_sync: 资产同步失败: 
  sequence item 0: expected a bytes-like object, NoneType found
2026-10-12 23:06:57,030 [WARNING] app.services.source_health: source_health failure: wazuh:agents 
  err=TypeError: sequence item 0: expected a bytes-like object, NoneType found
```

根因（CLAUDE.md §4 已记）：`wazuh_client` 模块级单例 import 时建，`_resolve_config(db=None) → None → 走 settings 兜底`。`.env` 缺 `WAZUH_API_USERNAME/PASSWORD` → httpx `auth=(None, None)` → TypeError。

**修复**：2026-10-13 已补 .env 兜底（commit `590daf1`）。`wazuh_client.py:80-90` 也加了拦截：
```python
# 不要让 httpx 内部拼 auth=(None, None) 才报 TypeError。
if not self.username or not self.password:
    raise WazuhConfigError(...)
```

### 1.4 data_health.py 当时已经有 7 天窗口（前人设计），但不够窄

```python
# 7 天前的注释：
# "陈年失败（历史 bug 已修、任务表仅存档）不应永远占据'最近失败'位"
failure_display_window = timedelta(days=7)
```

7 天窗口对"3 天前"的任务**仍然显示**——前人设计错了（操作员日常不会回看 3 天前的失败）。

---

## 2. 修复

### 2.1 A1: 6 条 manual failed task 标 superseded（保留审计）

```sql
-- 备份（防误操作可回滚）
CREATE TABLE _backup_sync_tasks_superseded_20261015 AS
  SELECT * FROM soc_sync_tasks
  WHERE status='failed' AND sync_type='manual'
    AND created_at > now() - interval '10 days'
    AND error_message LIKE '%bytes-like object%NoneType found%';

-- UPDATE 标 superseded（不删，error_message 末尾追加标记）
UPDATE soc_sync_tasks
SET status = 'superseded',
    error_message = error_message || E'\n[2026-10-15] 标记为 superseded：...'
WHERE ...（同上 6 条）
```

- 备份表：`_backup_sync_tasks_superseded_20261015`（6 行）
- 主表：6 行 `status: failed → superseded`
- panel 查询 `WHERE status='failed' AND created_at > now() - interval '7 days'` → **0 行**
- **panel 立即不显示"23:06 sequence NoneType"**（不需要等 A2 部署）

### 2.2 A2: data_health.py 7 天 → 24h 窗口（防未来占位）

```python
# src/backend/app/api/data_health.py:172
- failure_display_window = timedelta(days=7)
+ failure_display_window = timedelta(hours=24)
```

**A2 必须在 102 重启后端才生效**（待操作员 push master 触发 CD，或手动 scp + restart）。

---

## 3. 验收

```
$ ssh 102 "psql -c \"SELECT id, status, error_message FROM soc_sync_tasks WHERE id='03d61568-...';\""
  status = superseded
  error_message = "sequence item 0: ...\n[2026-10-15] 标记为 superseded: ..."
```

panel "数据源健康"卡片刷新后（**A1 立即生效**）：

- "最近失败 2026-10-12 23:06: sequence item 0..." **消失**
- 改为显示 "无最近失败"（或 24h 内确实没有就 null）

---

## 4. 未做（按计划，不阻塞）

| 项 | 原因 |
|---|---|
| `soc_source_health` 表 `wazuh:agents` `failure_count=5425` 不归零 | 历史累计值；归零有审计风险（CLAUDE.md §6 写"审计所有写操作走 @log_audit"）。failure_count 反映历史真实，不算 UI bug |
| alembic 迁移 | A1 是运维状态变更（status: failed → superseded），不是 schema 变更。按项目"schema 变跟代码走，状态变可以走 SQL + 备份表"惯例处理 |

---

## 5. 教训

- **`sync_freshness` 和 `source_health.sources[*]` 是两套字段**，前端在同一个"数据源健康"卡片里把它们并排显示，操作员误以为是同一个指标的"告警"——**这是 UX 设计 bug，不是数据 bug**。建议下版面板把"同步任务最近失败"和"数据源健康"做成两张独立卡片。
- **"`failure_count` / `last_failure_at` 不重置"是 source_health 表的语义设计**：保留历史累计。但 `record_success` 只清 `last_failure_message`、不推 `last_failure_at`——**新失败要发生在旧失败之前才能"覆盖"**。这种设计对操作员直觉是反的，3 天前失败一直占位就是后果。建议加一个"连续 N 次成功则清 last_failure_at"的可选规则。
- **A1 治标 + A2 治本** 模式：标记具体历史 task 是治标，缩窗口是治本。两者都做才能既立刻解决问题、又能防未来重犯。
