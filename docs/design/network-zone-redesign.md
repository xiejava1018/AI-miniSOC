# network_zone 8 值改造设计方案

> **状态**: 已实施（2026-XX-XX）
> **作者**: Claude Code 协作
> **关联**: alembic 迁移 `c1d2e3f4g5h6_network_zone_eight_values.py`、脚本 `scripts/backfill_network_zone.py`、字典 seed `scripts/init_system_data.py:88-99`

---

## 1. 背景

原 `network_zone` 字段定义为 5 个枚举值：

| 旧值 | 中文 | 含义 |
|---|---|---|
| `intranet` | 内网 | 生产/业务核心 |
| `dmz` | DMZ | 对外服务前置 |
| `office` | 办公网 | 员工办公终端 |
| `management` | 管理网 | 带外/堡垒机 |
| `other` | 其他 | 任意兜底 |

随着 SOC 资产纳管范围扩大（云、蜜罐、DevOps），暴露以下问题：

1. **`intranet` 太粗**：把生产核心和"所有非办公内网"压在一起，丢失业务/开发/测试的区分
2. **`other` 是任意填的兜底**：新形态资产（云、蜜罐）落到这里 = 分类失效，运维/审计/告警无法识别
3. **缺公网维度**：云服务器（ECS/CVM）该填什么没答案，cloud 资产被迫挤 `intranet`
4. **缺开发/测试维度**：DevOps 资产混在生产会污染告警分级与风险评分
5. **缺隔离区维度**：蜜罐/应急隔离区属于 SOC 自有资产，应独立告警处理
6. **缺业务承载维度**：旧分法只看"网络位置"，不看"业务性质"

## 2. 业界参考

| 框架 | 关键参考点 |
|---|---|
| NIST SP 800-53 / 800-82 | 物理区（corporate/operational/control/safety）+ 逻辑区（public/DMZ/internal/restricted/isolated/air-gapped） |
| Cisco 经典 5 区模型 | Internet / DMZ / Internal / Production / Management |
| AWS/阿里云 VPC 安全域 | Public zone / DMZ zone / App zone / Data zone / Mgmt zone / Isolated |

## 3. 新分法（8 值）

按 **3 个正交维度** 归类：安全暴露、业务承载、管理性质。

| dict_code | 中文 label | color | sort | 含义 | 典型资产 |
|---|---|---|---|---|---|
| `public` | 公网区 | danger | 1 | 直接面向互联网的入口 | 云 SLB / CDN / 对外 API Gateway / 公开网站 |
| `dmz` | DMZ | warning | 2 | 对外服务前置 | Web 前置 / 反向代理前置 / VPN 接入 |
| `production` | 生产内网 | primary | 3 | 业务核心（带等保） | 生产 DB / 应用服务器 / 微服务 |
| `office` | 办公网 | info | 4 | 员工办公终端 | PC / 笔记本 / 打印机 |
| `dev` | 开发测试网 | info | 5 | 开发/测试/Staging | dev/staging/test VM、CI runner |
| `management` | 管理网/带外 | info | 6 | 堡垒机 / 带外 | iLO / iDRAC / IPMI / OOB / 堡垒机 / jumpbox |
| `isolated` | 隔离区 | danger | 7 | 蜜罐/应急隔离/取证 | 蜜罐 ECS、应急隔离区、取证镜像 |
| `unknown` | 未分类 | info | 8 | 真兜底（≠`other`） | 触发人工复核 |

### 3.1 决策树（运维/纳管流程的判定路径）

按以下顺序判断，命中即落：

```
┌─ 1. 蜜罐/取证？ ──── yes ──→ isolated
│
├─ 2. 直接面向互联网入口（无前置）？ ── yes ──→ public
│
├─ 3. 员工办公终端？ ── yes ──→ office
│
├─ 4. iLO / iDRAC / 堡垒机 / 带外？ ── yes ──→ management
│
├─ 5. 开发/测试/Staging？ ── yes ──→ dev
│
├─ 6. 对外服务前置（Web 前置 / API Gateway / VPN）？ ── yes ──→ dmz
│
├─ 7. 生产业务核心？ ── yes ──→ production
│
└─ 8. 都不到？ ──→ unknown（人工复核）
```

### 3.2 与 `exposure_level` 的关系

`network_zone` 与 `exposure_level` 是 **正交** 字段，**不**互相替代：

| 字段 | 关注点 | 取值 |
|---|---|---|
| `network_zone` | 资产**位于哪个内部网络分区** | 8 值 |
| `exposure_level` | 资产**对外暴露程度** | `public` / `internal` / `isolated` |
| `public_ip` | 资产**公网入口 IP**（暴露面扫描目标） | 文本，可空 |

**联动建议**（未来实现，非本期）：
- `network_zone='public'` → 建议 `exposure_level='public'`
- `network_zone='isolated'` → 建议 `exposure_level='isolated'`
- `network_zone in ('dmz','production','dev','management')` → 建议 `exposure_level='internal'`

### 3.3 云服务器选什么

按 **角色** 选，不再按"是不是云"选：

| 云服务器角色 | network_zone | 备注 |
|---|---|---|
| 阿里云 ECS 部署对外 Web API，有公网 SLB | `public`（SLB）/ `dmz`（ECS） | 看架构层级 |
| 阿里云 ECS 内网 API，只供内网调用 | `production` | 业务核心，不对外 |
| 阿里云 RDS 内网访问 | `production` | 同上 |
| 阿里云堡垒机 | `management` | 带外 |
| 阿里云蜜罐 ECS | `isolated` | SOC 资产 |

## 4. 落地路径

### 4.1 alembic 迁移（必须先执行）

文件: `alembic/versions/c1d2e3f4g5h6_network_zone_eight_values.py`

执行顺序（**先数据后约束**，避免 CHECK 拒绝中间值）：

1. `UPDATE soc_assets SET network_zone = CASE ...`：5 旧值粗粒度映射到新 8 值
2. `DROP CONSTRAINT soc_assets_network_zone_check`
3. `ADD CONSTRAINT ... CHECK (network_zone IN ('public','dmz','production','office','dev','management','isolated','unknown'))`
4. `COMMENT ON COLUMN`：更新列注释指向本文档

**回滚代价**：`downgrade()` 把所有 `production` 退回 `intranet`，所有 `public`/`dev`/`isolated`/`unknown` 退回 `other`。**生产环境禁止 downgrade**。

### 4.2 字典 seed 更新（alembic 迁移后执行）

文件: `scripts/init_system_data.py:88-99` + 新增 `_migrate_network_zone_dict()`

逻辑：

1. for 循环按 8 值插入 `sys_dict`（如果 dict_code 不存在）
2. 调 `_migrate_network_zone_dict(db)`：
   - 把旧 `intranet` 行就地改为 `production`
   - 把旧 `other` 行就地改为 `unknown`
   - 保留 id / created_at / updated_at / is_active

**幂等**：重复执行不重复更新（基于 dict_code 冲突检测）。

### 4.3 数据迁移脚本（可选，alembic 后跑）

文件: `scripts/backfill_network_zone.py`

5 条二次回填规则（高置信度，无歧义才动）：

| 规则 | from | to | 条件 | 默认 |
|---|---|---|---|---|
| 1 | production | dev | asset_type='server' AND name/desc/os 含 dev/staging/测试 等 | ON |
| 2 | unknown | public | public_ip IS NOT NULL AND 非空 | ON |
| 3 | unknown | isolated | asset_type='security_device' OR name/desc 含 蜜罐/honeypot/取证 等 | ON |
| 4 | unknown | management | name/desc/os 含 iLO/iDRAC/堡垒/带外 等 | ON |
| 5 | office | production | asset_type='server' AND os_name 是服务器 OS | OFF（保守） |

用法：
```bash
# 预估影响范围（不执行）
../../venv/bin/python scripts/backfill_network_zone.py --dry-run

# 实际执行（默认规则 1-4，规则 5 关闭）
../../venv/bin/python scripts/backfill_network_zone.py

# 包含规则 5
../../venv/bin/python scripts/backfill_network_zone.py --include-office-server-rule

# 跳过规则 1
../../venv/bin/python scripts/backfill_network_zone.py --skip-dev-rule
```

回滚 SQL 见文件末尾 `ROLLBACK_SQL`。

### 4.4 前端

字典表由前端 `dictStore.getOptions('network_zone')` 自动拉取，**模板无需改**。已修改：

- `views/asset/list/index.vue:899/1067/1091`：formData 默认值 `'other'` → `'unknown'`
- 模型层默认值同步：`app/models/asset.py:34`、`app/schemas/asset.py:23`

## 5. 影响范围 / 验收清单

- [x] alembic 迁移：通过 `alembic upgrade head` 无错误
- [x] 字典 seed：`init_system_data.py` 跑后 `SELECT * FROM sys_dict WHERE dict_type='network_zone'` 返回 8 行
- [x] 字典迁移：`network_zone/intranet`、`network_zone/other` 两行被合并，无重复
- [x] 二次回填：`scripts/backfill_network_zone.py --dry-run` 打印合理预估
- [x] 同步路径：`asset_sync_handler.py` 白名单与新 8 值一致；非法值收敛为 `unknown`
- [x] scanner 纳管：`scan_tasks.py` 默认 `network_zone='unknown'`
- [x] 前端下拉：资产管理-添加资产表单的"网络区域"下拉出现 8 个选项
- [x] 列表展示：`unknown` 资产仍可见，标签为"未分类"

## 6. 未来扩展（不在本期）

1. **`network_zone` ↔ `exposure_level` 联动建议**：
   - 网络区域=public → 自动建议 exposure=public
   - 网络区域=isolated → 自动建议 exposure=isolated
2. **字典可视化管理**：把 8 值加到"系统管理-字典管理"页面支持 CRUD（当前依赖 seed）
3. **纳管表单决策树可视化**：添加资产时按决策树顺序给"为什么是这个值"的提示
4. **`network_zone` 维度用于告警分级**：`isolated` 的告警默认不计入生产 SLA；`dev` 的告警不计入 production KPI

## 7. 参考文档

- 业界：NIST SP 800-53、Cisco 5 区模型、AWS Well-Architected Framework（安全支柱）
- 项目内：
  - `docs/design/2026-06-03-asset-detail-v2-design.md`（资产字段定义）
  - `src/backend/app/models/asset.py`（Asset 模型）
  - `src/backend/app/core/criticality.py`（三维度重要性）
  - `src/backend/alembic/versions/807124bfc2bc_add_asset_network_zone.py`（原 5 值迁移）