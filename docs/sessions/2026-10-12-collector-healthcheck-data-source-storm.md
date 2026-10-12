# 2026-10-12：tplink 401 风暴 + 容器 healthcheck 刷数据源（同源问题 4 天后修复）

> 事件链：用户报 102 频繁打 192.168.0.1 → 以为是 5 分钟一次 → 实测 1 分钟一次 → 抓 healthcheck + 容器日志对齐 → 发现 wazuh 同样刷数据源(静默)

## 现象

```
# 用户贴的告警
1  2026-10-12 22:28:20  通知  tploginadmin(102) 尝试错误密码登录
2  2026-10-12 22:27:57  通知  tploginadmin(102) 尝试错误密码登录
3  2026-10-12 22:27:19  通知  tploginadmin(102) 尝试错误密码登录
4  2026-10-12 22:26:19  通知  tploginadmin(102) 尝试错误密码登录
# 看起来 ~1 分钟一次
# 但 config.yaml 写 interval=300(5 分钟)
# 哪个对?
```

## 调查路径

1. **看 `config.yaml`**：确认 interval=300
2. **看 102 容器日志**：
   ```
   2026-10-12 13:22:54 [INFO] 开始采集...
   2026-10-12 13:22:54 [INFO] POST http://192.168.0.1/ 401
   2026-10-12 13:27:54 [INFO] 开始采集...   ← 业务循环 5 分钟 ✓
   2026-10-12 13:27:54 [INFO] POST http://192.168.0.1/ 401
   ...
   2026-10-12 14:29:20 [HEALTHCHECK] POST http://192.168.0.1/ 401
   2026-10-12 14:30:21 [HEALTHCHECK] POST http://192.168.0.1/ 401   ← 1 分钟 1 次
   2026-10-12 14:31:22 [HEALTHCHECK] POST http://192.168.0.1/ 401
   ```
3. **看 `tplink-collector` 的 healthcheck 配置**：
   - `docker-compose.yaml` 没有 `healthcheck:` 段
   - `tplink/Dockerfile` 里有: `HEALTHCHECK --interval=60s ... CMD python -m tplink_collector --test || exit 1`
   - **HEALTHCHECK 走 `--test` 模式 → 调 `test_connection()` → 登录路由器**
4. **顺带验证 wazuh 容器**：
   - `wazuh/Dockerfile` 无 HEALTHCHECK
   - 但 compose 里有 `healthcheck:` 段,30 秒一次,内容是 `await c.test_connection()` → 登录 Wazuh API
   - 同样刷数据源,只是 Wazuh 无防爆破节流,**静默 4 天没人发现**
5. **wazuh-collector 实测 10 分钟打 Wazuh API 3 次**(30 秒一次),和我之前误以为"wazuh 不刷"完全相反

## 根因(双层)

### 直接:业务密码失配

102 容器内 `ROUTER_PASSWORD=mnbvvbnm123qaz`,但路由器 Web 管理密码已被改过。配置失配 4 天,期间 tplink 资产数据 0 入库。

### 架构:healthcheck 复用业务 test_connection

```python
# 错误模式(同病两处)
# tplink/Dockerfile
HEALTHCHECK --interval=60s ... CMD python -m tplink_collector --test
# docker-compose.yaml (wazuh)
healthcheck:
  test: |
    python -c "...await c.test_connection()..."
  interval: 30s
```

`test_connection()` 是给"业务连通性自检"用的,本来只在 `--test` 启动时跑一次。**复用它做容器健康检查**导致:
- **无防爆破数据源**(Wazuh):静默刷,无人察觉
- **有防爆破数据源**(TP-Link 5 分钟封禁):持续 401 触发"错误密码登录"告警,**刷出 4 天误报**

## 修复(commit 401797b + ce5e5ee)

### 1. `tplink/Dockerfile` 删 HEALTHCHECK 指令

镜像层不再隐式刷数据源。健康度交给 compose 段控制。

### 2. `docker-compose.yaml` 两段 healthcheck 统一改成"只测 miniSOC"

```yaml
healthcheck:
  test: ["CMD-SHELL", "python -c \"import os, urllib.request, urllib.error, sys
try:
    r = urllib.request.urlopen(os.environ['MINISOC_URL'].rstrip('/') + '/api/v1/health', timeout=5)
    sys.exit(0 if r.status == 200 else 1)
except (urllib.error.URLError, OSError):
    sys.exit(1)\""]
  interval: 60s
  timeout: 10s
  retries: 3
  start_period: 30s
```

设计原则:
- **只测到 miniSOC 的网络** → 不刷数据源
- **try/except URLError** → 失败时静默 exit 1,不在 healthcheck Output 留 traceback
- **间隔从 30s 统一到 60s**(原本 tplink 60s / wazuh 30s 不一致)

### 3. `CLAUDE.md §4.13` 加配套教训

详见 §4.13 第三条 bullet。

## 验证(102 实测)

```bash
# 部署前
docker inspect minisoc-tplink-collector   # Status=unhealthy, FailingStreak=4349
docker inspect minisoc-wazuh-collector   # Status=healthy, FailingStreak=0
                                          # (静默,不是没问题)

# docker compose build tplink-collector   # Dockerfile 改了
# docker compose up -d tplink-collector wazuh-collector
# sleep 60

# 部署后
docker inspect minisoc-tplink-collector   # Status=healthy, FailingStreak=0
docker inspect minisoc-wazuh-collector   # Status=healthy, FailingStreak=0
```

应用日志 3 分钟窗口:
- tplink 容器:打 192.168.0.1 **1 次**(业务 5 分钟一次正常节奏)✓
- tplink 容器:healthcheck 不进应用 stdout(只走 Docker daemon)✓
- wazuh 容器:打 192.168.0.40 **2 次** + 192.168.0.102 **1 次**(业务一次完整 cycle:认证/拉 agents/同步)✓
- **没有任何 healthcheck 干扰**

## 待办(不阻塞)

- ~~**业务密码**:`.env` 里的 `ROUTER_PASSWORD=mnbvvbnm123qaz` 失配~~ ✅ **2026-10-12 修复**:用户确认路由器新凭据 `xiejava / xiejava@Happy99`,改 102 `.env` + `docker compose up -d tplink-collector` 重启。`登录成功,stok: d61c6453...`,采集 11 条资产 `updated=11, skipped=0`,NAT 0 条(路由器无虚拟服务器规则)。DB 验证 `soc_assets WHERE data_source='tplink-router'` 76 条,`updated_at` 集中在 `2026-10-12T22:54:05`。
- **wazuh 凭据**:虽密码对,但 30 秒一次刷 Wazuh API 是"礼貌"问题(API 限流场景可能踩到),本次已一并降级
- **CLAUDE.md §4.13** 已加"静默刷数据源"教训,后续新增 collector 必须:
  - Dockerfile 不写 HEALTHCHECK 指令
  - compose healthcheck 段只测 miniSOC 端点
  - 数据源连通性由业务采集循环 + 告警覆盖

## 经验总结

1. **健康检查 = 进程活着 + 网络到后端通**,不应该去测业务数据源
2. **数据源连通性** 是业务关注点,必须由业务循环 + 告警覆盖,不能甩给 Docker daemon
3. **静默 ≠ 没问题** — wazuh 静默 30 秒刷 Wazuh API 4 天没人发现,因为 Wazuh 没内置防爆破
4. **`FailingStreak=0` 不代表架构正确** — 它只代表"探针逻辑全通过",不代表"探针逻辑本身合理"
