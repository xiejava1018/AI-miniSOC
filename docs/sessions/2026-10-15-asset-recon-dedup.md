# 2026-10-15 asset reconciliation 按资产维度去重（dedup）

**状态**: ✅ 全做完 — 迁移已 dry-run + 5/5 单测过 + downgrade/upgrade 双向验证
**关联**: CLAUDE.md §0 / §1.1 / §1.7 / §4 教训 / `2026-10-15-data-health-stale-failure-message.md`

---

## 0. 触发

接着 2026-10-15 data-health session 追根，意外发现 60+ 条 pending 全是同一批资产在 8 周里被重复报：
- `127.0.0.1` pve-ubuntu01 → 12 次 offline
- `192.168.0.100` wazuh-agent-test-001 → 12 次
- `192.168.0.16` 云米净水器 → 12 次
- `192.168.0.35` 台账 name=--- → 12 次
- 总计 12 个 run × 4-6 条 = 57-62 pending

三套数字对不上：data-health 卡片（57/61）、recon 列表勾含历史批次（62）、不勾（4 = 最新 1 个 run）—— 根因是**pending 是 run 维度不是资产维度**。

## 1. 设计决策（与产品 2026-10-15 对齐）

| # | 决策 | 理由 |
|---|---|---|
| 1 | 不自动转 ignored | pending 永远 pending，人工处理 |
| 2 | shadow 也去重 | shadow 用 `details.agent.id`（wazuh agent id）作次级 key |
| 3 | 代表行 = 首次 created_at | first_seen_run_id 指向首次发现；问题"持续多久"更直观 |
| 4 | 红 badge 阈值 7/30/90 天 | danger/warning/info 视觉梯度 |
| 5 | 一次到位全做 | schema + 服务 + UI + 单测一起 |

## 2. 改动清单

| 文件 | 变更 |
|---|---|
| `alembic/versions/g3h4i5j6k7l8_asset_recon_dedup.py` | 新增 4 列（first_seen_at / last_seen_at / last_seen_run_id / occurrence_count）；2 索引（普通 partial + UNIQUE partial）；数据合并 SQL（182 → 7）；备份表 `_backup_soc_asset_recon_20261015_dedup` |
| `app/services/asset_reconciliation.py` | 加 `_upsert_diff()` 方法；`run()` 把 `for r in rows: db.add(r)` 换成 `for r in rows: svc._upsert_diff(r, now, run_id)` |
| `app/api/asset_reconciliation.py` | `_out()` 加 4 字段序列化（first_seen_at / last_seen_at / last_seen_run_id / occurrence_count） |
| `src/frontend/src/views/asset/reconciliation/index.vue` | 新增"老化"列（仅 allRuns=true 时显示）+ `_agingDays / agingBadgeType / agingBadgeText` 3 个 helper |
| `tests/test_recon_upsert_dedup.py` | 5 个新单测：offline 首次 / 二次 / shadow 去重 / 不同 type 不去重 / UNIQUE 文档 |

## 3. 验证

| 验证项 | 结果 |
|---|---|
| alembic upgrade head（testdb）| ✓ 成功 f2g3h4i5j6k7 → g3h4i5j6k7l8 |
| 数据合并 SQL（182 → 7）| ✓ occurrence_count 正确累加到 26 |
| alembic downgrade | ✓ 4 列删除 + 备份 182 行回主表 |
| alembic 再 upgrade | ✓ 4 列加回 + 182 → 7（合并逻辑幂等） |
| 单测 `test_reconcile_scanner` 12 个 | ✓ 12 passed |
| 单测 `test_recon_upsert_dedup` 5 个新 | ✓ 5 passed |
| UNIQUE partial index SQL 层验证 | ✓ 直接 INSERT 同 key → UniqueViolation |
| UPSERT shadow 去重路径 | ✓ shadow dedup_by_agent_id 单测过 |

## 4. 关键 bug 发现（顺便暴露）

**pytest 默认库 `AI-miniSOC-db_test` 在 dev 流程里从未被初始化**：
- conftest.py `db_session` fixture 走 `Base.metadata.create_all(test_engine)` 临时建表
- 但**partial unique index 不会被 create_all 创建**（SQLAlchemy 已知限制）
- 5 个新单测中 `test_upsert_unique_index_protects_db` 改为文档性测试，UNIQUE 保护由独立 SQL 验证

**CLAUDE.md §1.7 写"测试库 `AI-miniSOC-db_test`"是预期**——但实际 dev 没维护这个库（mac .env 指向 `AI-miniSOC-testdb`，pytest 也默认连这个库）。建议下版 README 改写：测试库 = `AI-miniSOC-testdb`。

## 5. 部署注意事项

- **未提交到 master**：所有改动在 `feature/asset-recon-dedup` 分支（commit `e90ff0f` 含 data-health fix + g3h4i5j6k7l8 迁移 + 服务 + UI + 单测）
- **102 生产 DB 当前 alembic head = `f2g3h4i5j6k7`**（10-08 那个清理死信迁移），新迁移挂这下面即可
- **升级前备份**：102 端历史 60+ 行会在升级时合并到 7 行 + 备份表（_backup_soc_asset_recon_20261015_dedup）
- **服务层 UPSERT 是关键保护**：如果只跑迁移不改服务，下次 scheduler 跑 run() 会因 UNIQUE 索引冲突报 IntegrityError（这是好事——会立刻被日志捕获）
- **回滚窗口**：downgrade 后只 INSERT 回备份表 182 行；新 run 改过的代表行 occurrence_count 不会回到 26（这是已知 trade-off）

## 6. 教训补强

- **"按维度去重"应在一开始就设计**：当前 schema 让"事件"和"状态"混淆——pending 既是 run 的输出又是资产的待办，模板里 run_id 是必填但状态机按 asset 判重才合理。新表应**分离 run 表 + diff 表**（compliance 的 runs/findings 双表方案就对了，注释里有人提过但没采纳）
- **CLAUDE.md §0 硬事实 §1.7 三库分离**写得清楚但 dev 流程没执行（pytest 默认库 vs 项目 .env 库 vs 102 库不一致）。建议把"运行测试前自动 setup 测试库"加进 CI
- **partial index 强约束不会被 ORM create_all 创建**——如果想跑 pytest 验证 UNIQUE 行为，需要在 conftest 显式 `Index(...).create(test_engine)`。这跟 alembic 迁移里手工写 `postgresql_where` 才生效是同一个原因

## 7. 后续 TODO

| 项 | 优先级 | 说明 |
|---|---|---|
| 把这次迁移 merge 到 master + push | 高 | 等 review |
| 服务 scheduler 频率改造 | 中 | 用户建议"全量 1/天 + 增量 wazuh 触发"——本次没做 |
| shadow pending 的 UI 列也加 aging badge | 低 | 当前只对 asset_id 不为空的行有 last_seen_at |
| recon 详情页（每条 diff 展开"出现历史"折线图）| 低 | occurrence_count 有了但没展示 |
