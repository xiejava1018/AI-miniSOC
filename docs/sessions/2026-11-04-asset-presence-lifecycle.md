# 2026-11-04 资产存在性治理 P1/P2/P3 + 扫描排障

## 起因
- 用户发现 192.168.0.37 资产停在 10-25 的 online，删除资产报 500，内网定时扫描 18 天全失败没人知道。

## 修复与功能（commits 8928294 / 4f95559 / 2b2bdf9 / 13fdbc1 / 3818ace）

### 1. 资产删除 500
- 根因：`soc_alert_groups` / `soc_alert_group_analyses` 的 `linked_asset_id` FK 是 NO ACTION
- 修复：迁移 `e3f4a5b6c7d8` 改 ON DELETE SET NULL；`DELETE /assets/{id}` 加 IntegrityError 兜底返 400

### 2. 内网定时扫描 18 天全失败
- 根因：`soc_scan_targets` 里有 `172.18.0.0/16`（65536 地址），容器 `NMAP_TIMEOUT=300`/`MAX_RATE=100` 必超时
- 修复：目标 2/3 置 `enabled=false`，只扫 `192.168.0.0/24`（6s 完成）
- 教训：**scheduled 任务连续失败无任何告警** → 本次会议 P1 补了 data-health scan_coverage 节 + 站内通知

### 3. P1/P2/P3 存在性治理（commit 4f95559）
三公理：断言/观测分离；缺席需覆盖证明；状态有时效可复活。

- **Schema**（迁移 `f4a5b6c7d8e9`）：`soc_assets` + `last_seen_at/miss_streak/last_scan_missed_at/lifecycle_state`；新表 `soc_asset_observations`（asset×source 心跳合并）+ `soc_scan_coverage`（覆盖凭证含失败）
- **服务** `app/services/asset_presence.py`：`record_observation`（复活）/`record_task_coverage`/`settle_coverage`（缺席结算状态机：active→unverified(连续miss≥2)→presumed_offline(30天无观测)；retired 人工终态）
- **结算不在 report 时做**：采集器先 PATCH report 后才 POST /sync 数据（实测差 40s），report 时结算会把全网标失联 → `presence_scheduler` 每 15min 延迟 ≥10min 结算，凭证 `settled` 标记幂等
- **接入点**：scan report（覆盖凭证）、discovery/port sync（scanner 观测）、AssetSyncHandler 新建/更新（wazuh/tplink）、asset_sync webhook 路径、手工 POST /assets（manual）
- **阈值**走配置中心 `asset_lifecycle`（miss_streak_threshold=2 / offline_days=30 / fail_alert_threshold=3）
- **前端**：资产列表加"存在性"列+筛选（与 asset_status 正交）；概览加"失联资产"KPI
- **测试** `tests/services/test_asset_presence.py` 5 用例全绿

## 踩坑（新）
1. **alembic 迁移 SQLAlchemy 2.x**：`bind.execute("裸字符串")` 报 ObjectNotExecutableError → 必须 `sa.text()`；且 bind 参数 cast 必须 `CAST(:x AS regclass)` 不能 `:x::regclass`（§4.3 红线 4 的变体，连踩两次，各回滚部署一次）
2. **discovery 观测钩子**最初只放在 finding 更新分支，新 finding（新 task_uuid 每次都是新建路径）不记观测 → 移到 matched_asset 判空后统一记
3. **docker logs 只看到 public 扫描**：collector 有 daemon（拉 internal 任务）+ `--once` cron（public）两条路径，日志混在同一容器
4. **结算 cutoff 边界**：`scanned_at` 是 DB 时钟，比较用 `<= cutoff` 防微秒竞争

## 验证结果（生产）
- alembic 到 f4a5b6c7d8e9，65 资产回填 active
- 观测：scanner 24 / wazuh 19 / tplink-router 12
- 192.168.0.37：miss_streak=1（active），第二次覆盖（次日 11:00 定时扫描）后自动变 unverified
- 明天 11:00 起 scheduled internal 每天扫 /24（6s），覆盖凭证/结算全自动

## 待办（不阻塞）
- 定时时间 `EXEC_HOURS` 写死，未进配置中心；`soc_scan_targets` 无 UI/API 管理入口
- F1.3 对账 type=offline 自动联动（presumed_offline → 生成对账差异）未做，目前只有状态+KPI+通知
- 前端 data-health 页未展示 scan_coverage 节（API 已有）
- `retired` 状态的人工确认入口（API/前端按钮）未做
