# 2026-10-07 本体 SBOM 物化 + CI/CD 调查

## 主题
OH-1.4 资产组件（SBOM）物化 + 多项 UI/后端修复 + CI/CD runner Failed 排查

## 关键改动（commit d02242c）

### 本体（OH-1.4）方案3
- 新增 `AssetComponent` ORM 模型 → `soc_asset_components`（asset_id FK / name / version / component_type / size / path / agent_id / first_seen / last_seen）
- alembic 迁移 `c3d4e5f6a7b8` 挂 `u7v8w9x0y1z2` 下游（生产已跑通）
- `asset_component_sync`：OpenSearch syscollector packages → `soc_asset_components` 全量刷新（6h 间隔）；per-asset 独立事务；`asyncio.to_thread` 卸载 IO（§4.5 教训）
- `main.py` lifespan 注册 scheduler（`ASSET_COMPONENT_SYNC_ENABLED=false` 可关）
- 映射层 `ontology_mapping.py`：支持 `table:` / `opensearch:` 形态；识别 `status: planned`；注册 `AssetComponent`
- `configs/asset_ontology_v1.yaml`：
  - `control` 映射 Wazuh agent（EDR 口径），`count = 22`
  - `process` 映射 `soc_graph_nodes` + filter `node_type = 'process'`
  - `asset-component` 物化 live + OpenSearch 来源声明
- ontology-view 前端：planned / opensearch_sources 渲染
- 菜单 100 icon 修：`ri:share-circle-2-line` → `ri:node-tree`（iconify 静默坑，iconify API 验证 not_found）

### 时间线（OH-P0.T4）
- `adapters.summary`：dict → str 截断（pydantic 422 → 500 修复）
- `asset_timeline.types`：兼容 `?types=a,b,c` 与 `?types=a&types=b` 两种传参

### UI
- 资产详情：risk-card 补 margin-bottom 与 info/summary 一致（漏掉导致无间距）
- 通知通道：删除站内信占位卡（始终可用，无需配置）；修 `isDirty=computed(()=>false)` 永远禁用按钮 bug（启用/保存/测试全灰）
- 用户管理：新增邮箱字段（表单/列表/校验/列配置）—— 后端本已支持
- 邮件 SMTP：certifi CA 显式 TLS context，修 Mac Python 框架版 `CERTIFICATE_VERIFY_FAILED`；`ssl_verify=false` 逃生口

## CI/CD runner Failed 排查

**症状**：10-07 09:13、09:14、12:14 三次 runner Job Failed，102 上代码 HEAD 仍停在 7ed6cd6；deploy.log 没有失败堆栈（最后一条是 10-03 06:57:57 成功）。

**手动跑 deploy.sh**：**部署成功**（d02242c 已生效，alembic 同步到 c3d4e5f6a7b8，`soc_asset_components` 已建）。

**疑似根因**：
1. 网络/runner 超时（§4.14 教训方向）—— git pull 或 npm ci 阶段失败，runner 不重试
2. `alembic check` autogenerate 失败（已存在大量 drift：注释、索引、check constraint 差异），虽然 `|| log "WARN"` 应能吞错，但 pipeline 中 `tee` 退出码在某些边界条件可能让 ERR trap 提前触发
3. 采集器段 `deploy_collectors.sh` 失败（也写同一份 LOG_FILE，但 runner 日志被截断）

**待办**（不阻塞当前）：
- 给 deploy.sh 加 `set +e` 或显式吞 `alembic check` 的失败
- runner workflow 加 `continue-on-error` + retry
- 排查 102→GitHub 慢网（§4.14）

## 验证
- 本地：手动 `run_component_sync_once()` → 21 台资产 / 15131 组件入库（1 台失败：syscollector 毒记录 agent）
- 本体对齐：`asset-component → orm, soc_asset_components, count=15131`，validate valid
- 通知中心：`POST /notification-channels/2/test?actual=true` → `email sent to admin@example.com: sent OK`，619ms
- 时间线：`GET /api/v1/assets/{id}/timeline?limit=10&types=log,alert` → 200，10 条
