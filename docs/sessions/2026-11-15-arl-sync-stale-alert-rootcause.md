# arl:sync 数据链路异常告警 — 根因排查

> 排查时间：2026-11-15 上午
> 告警原文：`数据源中断 / arl:sync 已中断 9.2 小时 (阈值 3.0 小时) / 影响：对账与报告的数据可能不完整（告警趋势可能用零值填充）/ 查看详情`
> 结论：**不是数据链路故障，是「采集器从未部署为常驻服务」**。告警本身是正确的（源健康断流可见性按设计工作），但被断的对象是一个只跑过一次性验证的链路。

---

## 1. 告警从哪来

推送场景 1「数据链路异常」：`src/backend/app/services/push_notification_service.py`

- `_find_source_anomalies()` 遍历 `soc_source_health` 全表
- 阈值：`threshold = max(down_hours * 3600, expected_interval_seconds * 2)`
- `arl:sync` 的 `expected_interval_seconds = 1800`（30min），`down_hours` 默认 3
  → `max(3h, 1h) = 3h` → **阈值 3.0h，与告警文案完全一致**
- 断流时长 = `now - last_success_at` → **9.2h**

邮件模板：`src/backend/app/services/email_template_registry.py:114`
`"[数据源中断] {source_code} 已中断 {down_hours} 小时"`

`impact` 文案「对账与报告的数据可能不完整（告警趋势可能用零值填充）」是 `push_notification_service.py` 硬编码常量。

## 2. 关键发现：告警来自**本地 Mac dev 后端**，不是生产

| 环境 | DB | `soc_source_health` 里有 `arl:sync`？ | 有该告警通知？ |
|---|---|---|---|
| 生产 192.168.0.102 | 本机 PG `AI-miniSOC-db` | **无**（只有 6 行：loki:browsing_detection / scanner:discovery / scanner:ports / tplink:collector / tplink:nat / wazuh:agents） | **无** |
| 本地 Mac dev | 远端 `111.228.57.2:25432` `AI-miniSOC-testdb` | **有** | **有**（`2026-11-15 10:06:02`） |

即：本地 `uvicorn`（PID 85967，Nov 14 16:31 启动）对 testdb 跑 `push_scheduler`，
读到自己 testdb 里的 `arl:sync` 断流，发了站内信 + 邮件。

**生产侧完全没有这条告警** —— 因为生产库压根没有 `arl:sync` 行（ARL 采集器没在生产跑过）。

> 注意：这条告警只有 6 个接收人副本（同一 push 事件 fan-out 到 6 个用户），dedup 键是 `link`，
> 而场景 1 传 `link_path=None` → `link` 为空 → 6 条通知 content 完全一样。

## 3. 真正的问题：`arl-collector` 从未作为常驻服务部署

代码是齐的（commit `a37a137` 2026-11-15 00:51「部署链路补齐」）：

- `src/collectors/arl/` — collector + Dockerfile + pyproject + config.example.yaml ✅
- `src/collectors/docker-compose.yaml` — `arl-collector` service 已定义 ✅
  （`restart: unless-stopped` / `init: true` / healthcheck 只打 SOC `/api/v1/health`，不刷 ARL）
- `deploy/deploy_collectors.sh` — §8 ARL 数据新鲜度门禁已写 ✅
  （曾有数据但 stale → FAIL / 从无数据 → WARN / DB 查询失败 → WARN）

但**服务从未真正跑起来**：

### 3.1 生产 102 上根本没部署

```
$ ssh 102 'docker ps'
minisoc-wazuh-collector     Up 14 hours (healthy)
minisoc-scanner-collector   Up 15 seconds (healthy)
minisoc-tplink-collector    Up 14 hours (healthy)
# 无 minisoc-arl-collector

$ ssh 102 'cd src/collectors && docker compose images'
minisoc-scanner-collector / minisoc-tplink-collector / minisoc-wazuh-collector
# 无 arl-collector 镜像
```

原因链：

1. 102 的 `src/collectors/docker-compose.yaml` mtime = **Oct 12 14:47** → 还是 ARL 集成之前的版本
   （ARL compose 块在 `a37a137` 才加，Nov 15）
2. 102 的 `src/collectors/.env` 只有 9 个键（`MINISOC_URL` / `MINISOC_API_KEY` / `ROUTER_*` /
   `TPLINK_INTERVAL` / `WAZUH_*`），**`ARL_*` 一个都没有** → 即使 compose 里有块，
   `arl_collector/__main__.py:35-40` 拿不到 `ARL_BASE_URL` 会直接 `raise ValueError("缺少 ARL_BASE_URL")`，
   且 `client.py:70-72` 在 `api_key` 和 `username+password` 都缺时抛
   「ARL 凭据缺失：需要 api_key 或 username+password（其一）」→ **容器起不来**
3. `deploy_collectors.sh` 从没在 102 上跑过（compose images 里三个镜像都是 14h 前 = 上次
   deploy.sh 触发的旧路径；ARL 门禁 §8 是 `a37a137` 新加的，还没到过 102 的仓库）

### 3.2 ARL-Next 本身是通的（排除网络/上游故障）

```
从 102:  curl -sk https://192.168.0.42:5173/api/ → 404, 0.027s
从 Mac:  curl -sk https://192.168.0.42:5173/api/ → 404, 0.067s
```

404 是正常的（该路径无路由），说明 TLS 握手 + TCP 全通。**上游 ARL-Next（PVE 虚机 192.168.0.42）
健康，是我们的采集器没跑。**

## 4. `arl:sync` 最后一次成功 = 2026-11-15 00:51（一次性验证跑）

`testdb` 的 `soc_sync_tasks` 尾部（ARL 专属、只有 collector 类型）：

```
00:51:02  tot=2    c=0 u=2   f=0   ← arl_vuln
00:50:34  tot=197  c=0 u=197 f=0   ← arl_site
00:50:19  tot=2    c=0 u=2   f=0
00:49:43  tot=197  c=0 u=197 f=0
00:49:09  tot=197  c=0 u=197 f=0
00:48:37  tot=197  c=0 u=197 f=0
00:39:37  tot=2    c=2 u=0   f=0
00:37:01  tot=0    c=0 u=0   f=0
```

**14 分钟内连推 6 轮** —— 这是人工「端到端验证」的一次性跑批（`a37a137` commit message 里明确写了
「采集：arl_site 197 条 + arl_vuln 2 条」「幂等验证：同天批次重推 created=0」），
**不是 30min 节奏的常驻 daemon**。跑完就退出了 → 之后 9.2h 无成功 → 告警。

commit `a37a137` 的时间戳 `2026-11-15 00:51:46` 与最后一次 push `00:51:02` 严丝合缝 —— 跑完就提交。

## 5. 伴生告警 `probe:arl_site`

同一批推送里还有一条 `【数据链路异常】probe:arl_site`（已 9.5h 无成功，阈值 3.0h）。

`probe:arl_site` 在 `soc_source_health` 里，`last_success_at = 2026-11-15 00:37:01`，
对应上表 00:37:01 那条 `tot=0` 的 sync_task。

来源不在 `src/backend/app/services/sync_handlers/` 里（grep 无命中），且 `expected_interval_seconds = None`
→ 它是被某个**临时探针脚本**写的（验证脚本一次性打的探针），同样跑完即退。

> 遗留问题：`probe:arl_site` 这个 source_key **没有对应的生产代码写入方**，属于验证脚本遗留的脏行。
> 它会永久占用「数据链路异常」告警位（因为 `expected_interval=None` → threshold 退化为 3h 兜底）。
> 应清理或补上正式写入方。

## 6. 结论与处置

### 告警本身没有 bug

`arl:sync` 断流被如实检出并推送 —— 这正是 §八-B「源健康的运营化消费」设计要的效果。
**假阴性（断流无人知晓）比误报更危险**（CLAUDE.md §4.2 精神）。

真正的问题是**被监测对象的部署缺口**。

### 处置清单

| # | 事项 | 优先级 | 说明 |
|---|---|---|---|
| 1 | 在 102 上部署 `arl-collector` 容器 | **高** | 补 `src/collectors/.env` 的 `ARL_BASE_URL` / `ARL_USERNAME` / `ARL_PASSWORD`（或 `ARL_API_KEY`）/ `ARL_SCOPE_IDS`；再跑 `deploy/deploy_collectors.sh` |
| 2 | 102 的 `src/collectors/docker-compose.yaml` 需更新到含 `arl-collector` 的版本 | 高 | 现在还是 Oct 12 旧版；`deploy_collectors.sh` 依赖 git checkout 拉新版本，需确认拉的是 ARL 块 |
| 3 | 清理 `probe:arl_site` 脏行 | 中 | 无写入方的临时探针行，会永久占告警位 |
| 4 | 评估 `arl-collector` 的 API Key 制度 | 中 | config 注释说「长期 API Key（推荐，按制度轮换）」，当前 ARL_USERNAME/PASSWORD 走 login 换 token（会话 24h） |
| 5 | 决定 ARL 同步在**生产**是否启用 | 中 | 若一期只在 dev 验证，则 dev 的 testdb 告警应静音（如 dev 环境关 `source_health` 场景 1），避免噪声淹没真告警 |
| 6 | `deploy_collectors.sh` §8 ARL 门禁首次上 102 时会判 `WARN`（从未有数据） | 低 | 语义正确（不拦部署），但要预期到 |

### 部署命令参考（102）

> **前置**：102 已有 `MINISOC_URL` + `MINISOC_API_KEY`（另外 3 个采集器在用，同一个 key 走
> `POST /api/v1/data/sync` 的 `require_api_key` 认证）→ **推数据侧的凭证不缺**。
> 缺的只有 `ARL_*` 4 个键。

```bash
ssh xiejava@192.168.0.102
cd /home/xiejava/AIproject/AI-miniSOC
# 1) 确认 compose 有 arl-collector 块（现在还是 Oct 12 旧版，必须先更新代码）
git pull                                   # 或 git checkout 到含 a37a137 的 commit
grep -n 'arl-collector' src/collectors/docker-compose.yaml
# 2) 补 src/collectors/.env 的 ARL_* 键（凭据不在仓库，需从 ARL-Next 运维侧取）
#    ARL_BASE_URL=https://192.168.0.42:5173
#    ARL_API_KEY=<长期 Key>            # 或 ARL_USERNAME + ARL_PASSWORD
#    ARL_SCOPE_IDS=<授权 scope_id 逗号分隔>
# 3) 部署（compose config --services 会自动覆盖到 arl-collector）
bash deploy/deploy_collectors.sh
# 4) 验证（30min 内应看到 arl:sync 恢复）
cd src/backend && PYTHONPATH=. ./venv/bin/python -c "
from app.core.database import SessionLocal
from app.models.source_health import SourceHealth
db=SessionLocal()
s=db.query(SourceHealth).filter(SourceHealth.source_key=='arl:sync').one_or_none()
print(s.source_key, s.last_success_at, s.last_failure_message)"
```

**凭据现状**：E2E 验证时 ARL 凭据是**命令行内联传入**的（`~/.zsh_history` 无记录，
`src/collectors/.env` 与 `src/collectors/arl/config.yaml` 在 Mac 上都不存在，仓库里只有
`config.example.yaml` + compose 的 env 注入位）→ **凭据已随会话丢失，部署前需重新获取**。

**可选**：走 `--test` 双连通自检（ARL + SOC）先验证凭据再上常驻
（`python -m arl_collector --test`，见 `client.py:66 test_connection`）。

## 7. 沉淀教训

1. **「部署链路补齐」≠「已部署」**。commit message 写「部署链路补齐」指的是 compose 块 + Dockerfile +
   门禁脚本都写好了，**不等于容器在跑**。验收要看 `docker ps` 有没有那个容器 + `arl:sync`
   的 `last_success_at` 有没有持续推进。**两者都不是「代码写完」能证明的。**

2. **一次性验证跑 ≠ 常驻服务**。E2E 验证会推 6 轮数据（14 分钟内），这会在 `soc_source_health`
   留下「看起来很健康」的成功记录，但服务早已退出。**间隔分布才是判据**：14 分钟 6 轮
   ≠ 30min 1 轮。看 `soc_sync_tasks` 的时间分布能立刻分辨。

3. **告警要连同「哪个环境」一起看**。同一条 `arl:sync` 告警在生产库不存在、在 testdb 存在 →
   第一反应应该是「告警来自哪个 DB」，而不是「哪个服务挂了」。
   `soc_source_health` 行数在两个库完全不同（6 vs 11）就是最早的信号。

4. **门禁脚本也要跟着上生产**。`deploy_collectors.sh` §8 的 ARL 门禁写于 Nov 15，
   但 102 上从未跑过这个脚本 → 门禁本身没被验证过。新写门禁的第一次执行要盯输出，
   别默认它工作。

5. **临时探针要清理**。`probe:arl_site` 这类「验证脚本留下的 source_health 行」没有写入方，
   但会被常驻的告警扫描器当成永久故障源。验证脚本用完应删行，或用带明确前缀且能被识别
   为临时的 key。

---

## 附：相关文件

| 文件 | 作用 |
|---|---|
| `src/backend/app/services/push_notification_service.py` | 场景 1 数据链路异常（阈值计算 + 推送内容） |
| `src/backend/app/services/email_template_registry.py:114` | `[数据源中断] {source_code} 已中断 {down_hours} 小时` 模板 |
| `src/backend/app/services/source_health.py` | `SourceHealthRecorder.record_success/failure`（唯一写入方） |
| `src/backend/app/services/sync_handlers/arl_site_sync_handler.py` | `arl:sync` key + `expected_interval_seconds=1800` |
| `src/backend/app/services/sync_handlers/arl_vuln_sync_handler.py` | 同上（共享 key `arl:sync`） |
| `src/collectors/arl/` | ARL-Next 采集器（Dockerfile + config） |
| `src/collectors/docker-compose.yaml` | `arl-collector` service 定义 |
| `deploy/deploy_collectors.sh` §8 | ARL 数据新鲜度门禁 |
| `docs/design/2026-11-14-ARL-Next集成设计方案.md` | OH-ARL.1~5 总体设计 |
