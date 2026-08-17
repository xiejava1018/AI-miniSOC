# 后台任务可观测性 Runbook

> 适用版本：v0.4.2+
> 关联设计：`docs/design/2026-08-16-后台任务执行可观测性梳理与方案-v0.4.md`
> 关联代码：`src/backend/app/services/task_observability/`
> 关联看板：`configs/grafana/dashboards/ai-minisoc-task-observability.json`
> 关联告警：`configs/prometheus/ai-minisoc-tasks-alerts.yml`

---

## 0. 30 秒速查

| 现象 | 立即操作 |
|---|---|
| `/health` 返回 `down` | 看日志最后 200 行；DB 连接挂了通常是元凶 |
| `/health` 返回 `degraded` + `zombies` 非空 | 按下方 §2 SOP 处理僵尸 |
| 收到 `TaskWatchdogDown` 告警 | 立即登录服务器看 `journalctl -u ai-minisoc -n 500`；watchdog 挂了 = 整个观测系统瞎了 |
| 收到 `TaskConsecutiveFailures` 告警 | §3 SOP；先看 soc_task_registry.last_error |
| 任务一直 skip 没 run | §2：99% 是前一个同步线程卡死，锁没释放 |
| 前端"任务中心"看不到任务 | §5：检查 registry 表 + 菜单 seed + admin role 授权 |

---

## 1. 健康检查

### 1.1 端点

```bash
curl -s http://localhost:8000/health | jq
```

返回 4 种状态：

| status | HTTP code | 含义 |
|---|---|---|
| `healthy` | 200 | 看门狗活着，无僵尸，无停滞，无 disabled 关键任务 |
| `degraded` | 200 | 有停滞任务、有僵尸、或有关键任务 disabled |
| `down` | 503 | DB 不可达或看门狗进程级死亡 |

字段说明：

```jsonc
{
  "status": "degraded",
  "watchdog": {
    "alive": true,
    "last_tick_seconds_ago": 12,
    "clock_skew_seconds": 0
  },
  "stale_tasks": [
    {"task_key": "browsing_detector", "last_run_at": "...", "expected_interval_s": 300}
  ],
  "zombies": [...],
  "disabled_tasks": ["..."]
}
```

### 1.2 Prometheus 指标

| 指标 | 类型 | 用途 |
|---|---|---|
| `task_watchdog_alive` | Gauge | 1=活着，0=挂了 |
| `task_watchdog_last_tick` | Gauge | 最后一次 tick 的 Unix 时间戳 |
| `task_zombie_total` | Gauge | 当前僵尸 run 数 |
| `task_consecutive_failures{task_key}` | Gauge | 连续失败次数 |
| `task_staleness_seconds{task_key}` | Gauge | 距今多久没成功 run |
| `task_last_duration_seconds{task_key}` | Gauge | 最近一次 run 耗时 |
| `task_runs_total{task_key,status,trigger}` | Counter | run 次数 |
| `task_notification_queue_size` | Gauge | 通知队列积压 |
| `notification_dropped_total` | Counter | 通知丢弃总数 |

---

## 2. SOP：僵尸任务（Zombie）

### 2.1 判定标准

`soc_task_runs.status = 'running'` 且 `started_at < now() - 5 min`。

watchdog 每 60s 扫一次，会把这些 run 标记为 `zombie` 并发站内信。

### 2.2 根因

99% 是 `@track_task` 装饰器包装的**同步 body 在 `asyncio.to_thread` 里卡死**（DB 慢查询、HTTP 无 timeout、文件锁等）。装饰器的 `asyncio.timeout()` 触发后会等同步线程真正结束（POC-2 验证过的设计），所以：

- timeout 已触发但 sync 线程还在跑 → run 暂时保持 `running`，后续 tick 被 skip
- 5 分钟后 watchdog 标记 zombie（但线程其实还在跑，锁还持有）
- 同步线程最终结束后，run 被 finish_run 写成 `timeout`（覆盖 zombie）

### 2.3 处理步骤

```bash
# 1. 找到僵尸 run
psql -c "SELECT id, task_key, started_at, host, trigger
         FROM soc_task_runs
         WHERE status='running'
           AND started_at < now() - interval '5 minutes';"

# 2. 看进程在干啥（macOS/Linux 通用）
py-spy dump --pid <pid>

# 3a. 如果是死锁/不可恢复 → 重启进程
systemctl restart ai-minisoc
# 启动时 reconcile_on_startup() 会把所有 running run 标成 unknown

# 3b. 如果只是慢查询，等它自然结束（锁会释放，run 最终写 timeout）
# 观察：
watch -n 30 "psql -c \"SELECT task_key, status, duration_ms FROM soc_task_runs
                         WHERE id='<run_id>';\""
```

### 2.4 预防

- 所有 HTTP 调用必须设 timeout（`httpx.Timeout(10)`、`requests.get(timeout=...)`）
- 所有 DB 查询必须走索引
- `timeout_s` 设置 ≥ 95 分位耗时 × 2

---

## 3. SOP：任务连续失败

### 3.1 判定

`task_consecutive_failures{task_key="..."} >= 3` 触发告警。

### 3.2 排查

```bash
# 看最近 5 次错误
psql -c "SELECT started_at, status, LEFT(error_text, 500)
         FROM soc_task_runs
         WHERE task_key='<TASK_KEY>'
           AND status IN ('failed','timeout')
         ORDER BY started_at DESC
         LIMIT 5;"

# 看 registry 汇总
psql -c "SELECT task_key, consecutive_failures, last_status,
                LEFT(last_error, 300) AS err, last_run_at
         FROM soc_task_registry
         WHERE task_key='<TASK_KEY>';"
```

### 3.3 常见根因

| 错误关键字 | 根因 | 处理 |
|---|---|---|
| `OperationalError.*connection` | DB 连接池耗尽 | 看 §4 |
| `ReadTimeout` / `ConnectTimeout` | 上游依赖（Loki/Wazuh/CISA）不可达 | 等上游恢复 |
| `401 Unauthorized` | 凭证失效 | 重新配置（如 MCP：`set_mcp_credentials`） |
| `Deadlock found` | 并发写入冲突 | 检查是否同一时刻有多个 trigger |
| `disk full` / `No space left` | 磁盘满 | `df -h` |
| `asyncio.Lock deadlock` | 同任务在上一轮卡住 | 按 §2 处理僵尸 |

### 3.4 复位

当根因修复后，需要把 `consecutive_failures` 清零让告警恢复：

```bash
psql -c "UPDATE soc_task_registry
         SET consecutive_failures=0
         WHERE task_key='<TASK_KEY>';"
```

下一次成功 run 也会自动清零。

---

## 4. SOP：DB 连接池耗尽

### 4.1 症状

- 大量任务同时 hang 在"running"
- 日志报 `QueuePool limit of size X overflow Y reached`
- `/health` 可能也变 down（自己查 DB 也失败）

### 4.2 根因

最常见：
1. 装饰器 timeout 后同步线程仍在跑，持有 DB 连接
2. 多个任务同时触发（scheduler tick + 手动 trigger 叠加）
3. 长事务未提交

### 4.3 紧急处理

```bash
# 看当前连接数
psql -c "SELECT count(*), state FROM pg_stat_activity
         WHERE datname='ai-minisoc'
         GROUP BY state;"

# 紧急重启
systemctl restart ai-minisoc
```

### 4.4 长期

- 调大 `DB_POOL_SIZE`（默认 10）
- 检查所有 `SessionLocal()` 是否在 `finally: db.close()`
- 长任务用独立 session（不要在 to_thread 外持有）

---

## 5. SOP：前端"任务中心"看不到任务

### 5.1 检查后端

```bash
# 后端是否有数据
psql -c "SELECT count(*) FROM soc_task_registry;"
# 应该 ≥ 5（4 业务 + 1 watchdog；MCP configure 后 +1）
```

### 5.2 检查菜单

```bash
psql -c "SELECT id, title, path, component
         FROM soc_menus
         WHERE path='task-center';"
# 应该返回 1 条，id 通常是 34
```

如果为空，补 seed：

```bash
cd src/backend && ../../venv/bin/alembic upgrade head
# 或重跑 a0b1c2d3e4f5 迁移
```

### 5.3 检查角色授权

```bash
psql -c "SELECT role_id, menu_id FROM soc_role_menus WHERE menu_id=34;"
# 应该看到 role_id=1 (admin)
```

### 5.4 重新登录

菜单缓存在 Pinia + localStorage，需要登出再登录才能拉到新菜单。

---

## 6. SOP：看门狗挂了（TaskWatchdogDown）

### 6.1 含义

`task_watchdog_alive == 0` 或最后一次 tick > 180s 前。

**影响**：
- 不会再标记 zombie
- 不会再检测停滞任务
- 不会再做时钟偏移检测
- 业务任务可能还在跑，但你"看不见"

### 6.2 处理

```bash
# 1. 立即看日志
journalctl -u ai-minisoc -n 1000 | grep -E 'watchdog|ERROR' | tail -50

# 2. 重启（watchdog 会在 lifespan 启动时自动重跑 reconcile + initial tick）
systemctl restart ai-minisoc

# 3. 验证
sleep 5
curl -s http://localhost:8000/health | jq '.watchdog'
# 应该看到 alive=true, last_tick_seconds_ago 是个位数
```

### 6.3 长期

- 检查服务器内存（OOM killer 可能杀了 watchdog task，但进程还活着）
- `dmesg | tail -50`
- 看是否有 `watchdog tick failed` 异常堆栈，按堆栈修 bug

---

## 7. SOP：通知没收到

### 7.1 检查通知队列

```bash
curl -s http://localhost:8000/metrics | grep task_notification_queue_size
```

- 持续增长 → drain task 挂了，重启进程
- 一直是 0 但应该有通知 → 看 §7.2

### 7.2 检查 dedup

5 分钟滑动窗口内相同 `(alert_type, task_key)` 只通知一次。看：

```bash
# 日志里搜 dedup
journalctl -u ai-minisoc | grep -i 'dedup\|skip.*notification' | tail -20
```

### 7.3 检查接收人

```bash
psql -c "SELECT key, value FROM soc_system_config WHERE key='oncall_user_ids';"
# 应该是 JSON 数组，如 [1, 2]
# 没配置时默认发给 admin 角色所有用户
```

### 7.4 检查 WebSocket

- 前端是否已建立 WS（浏览器 DevTools → Network → WS）
- 后端日志是否有 `websocket connected`
- 多 pod 部署需要 Redis pub/sub（Phase 2，当前未实现）

---

## 8. SOP：手动触发 vs 取消

### 8.1 手动触发

**前端**：任务中心 → 点"立即执行" → 填原因（≥3 字，写入审计日志）。

**API**：

```bash
curl -X POST http://localhost:8000/api/v1/tasks/<task_key>/trigger \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "上线后验证"}'
# 返回 202 + run_id（fire-and-forget，不等待执行结果）
```

### 8.2 取消

当前 Phase 1 **不支持真取消**（Python 线程无法安全 kill）。`cancel` API 只标记 run 状态为 `cancelled`，但同步线程仍会跑完。

```bash
curl -X POST http://localhost:8000/api/v1/tasks/<task_key>/cancel/<run_id> \
  -H "Authorization: Bearer $TOKEN"
```

如果任务真的卡死，用 §2 重启进程。

---

## 9. 部署清单

### 9.1 后端

1. 跑迁移：`cd src/backend && ../../venv/bin/alembic upgrade head`
   - 应用 3 个迁移：`e8f9a0b1c2d3`（建表）、`f9a0b1c2d3e4`（去循环 FK）、`a0b1c2d3e4f5`（菜单 seed）
2. 重启后端：`systemctl restart ai-minisoc`
3. 验证：`curl http://localhost:8000/health` 返回 healthy
4. 验证：`curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/tasks/summary` 返回 ≥5 个任务

### 9.2 Prometheus

1. 把 `configs/prometheus/ai-minisoc-tasks-alerts.yml` 复制到 Prometheus 规则目录
2. `promtool check rules ai-minisoc-tasks-alerts.yml`
3. `curl -X POST http://prometheus:9090/-/reload`
4. Prometheus UI → Alerts 确认 7 条规则绿色

### 9.3 Grafana

1. 把 `configs/grafana/dashboards/ai-minisoc-task-observability.json` 复制到 provisioning 目录
2. 配置两个数据源变量：`DS_PROMETHEUS`、`DS_POSTGRES`
3. 打开 Dashboard UID `ai-minisoc-tasks`
4. 确认 14 个 panel 有数据

### 9.4 前端

1. `npm run build`
2. 部署静态资源
3. 重新登录（拉新菜单）
4. 侧栏"系统管理"下应出现"任务中心"

---

## 10. 关键数据库查询速查

```sql
-- 1. 看所有任务状态
SELECT task_key, task_type, enabled, last_status, consecutive_failures,
       total_runs, last_run_at, last_duration_ms
FROM soc_task_registry ORDER BY task_key;

-- 2. 看某任务最近 20 次 run
SELECT started_at, status, trigger, duration_ms, LEFT(error_text, 200) err
FROM soc_task_runs
WHERE task_key='<TASK>'
ORDER BY started_at DESC LIMIT 20;

-- 3. 找正在跑的 run
SELECT id, task_key, started_at, host, trigger
FROM soc_task_runs WHERE status='running';

-- 4. 24h 成功率
SELECT task_key,
       count(*) FILTER (WHERE status='success')*1.0 / count(*) AS success_rate,
       count(*) AS total
FROM soc_task_runs
WHERE started_at > now() - interval '24 hours'
GROUP BY task_key ORDER BY success_rate ASC;

-- 5. 最近失败
SELECT task_key, started_at, LEFT(error_text, 300) err
FROM soc_task_runs
WHERE status IN ('failed','timeout','zombie')
  AND started_at > now() - interval '24 hours'
ORDER BY started_at DESC LIMIT 50;
```

---

## 11. 升级与回滚

### 11.1 升级到 v0.4.2

```bash
cd /opt/ai-minisoc
git pull
cd src/backend
../../venv/bin/alembic upgrade head
sudo systemctl restart ai-minisoc
```

### 11.2 回滚

```bash
git checkout <previous-version>
cd src/backend
../../venv/bin/alembic downgrade -1  # 会删除菜单 seed；表保留
sudo systemctl restart ai-minisoc
```

⚠️ 表不会自动 drop（`e8f9a0b1c2d3` 不能简单 downgrade，因为有外键）。需要手动：

```sql
DROP TABLE soc_task_runs CASCADE;
DROP TABLE soc_task_registry CASCADE;
DELETE FROM soc_role_menus WHERE menu_id IN (SELECT id FROM soc_menus WHERE path='task-center');
DELETE FROM soc_menus WHERE path='task-center';
DELETE FROM alembic_version WHERE version_num IN ('e8f9a0b1c2d3','f9a0b1c2d3e4','a0b1c2d3e4f5');
```

---

**文档版本**：Runbook v1.0
**最后更新**：2026-08-17
**维护者**：AI-miniSOC Team
