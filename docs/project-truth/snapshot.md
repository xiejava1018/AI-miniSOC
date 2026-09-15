# 项目硬事实快照

> **自动生成于 2026-09-15 02:58 UTC** by `scripts/sync_claude_md_truth.py`
> 不要手改——下次跑脚本会被覆盖。发现过期请修脚本或修源数据。

## 数据库

- **业务表总数**: `66`（全部 `soc_` 前缀）
- **非 soc_ 前缀的表**: 无
- **alembic 迁移文件数**: `63`

## Alembic heads

- 单 head: `628109e83308`（线性 OK）

## 顶级菜单（按 sort_order）

| sort | path | component | title | 可见 |
|---:|---|---|---|:-:|
| 1 | `/dashboard` | `/dashboard/console` | 概览仪表板 | ✅ |
| 2 | `/assets` | `/index/index` | 资产管理 | ✅ |
| 3 | `/vulnerabilities` | `(容器)` | 脆弱性管理 | ✅ |
| 4 | `/incidents` | `/index/index` | 事件管理 | ✅ |
| 5 | `/alerts` | `/index/index` | 告警管理 | ✅ |
| 6 | `/browsing` | `/index/index` | 行为分析 | ✅ |
| 7 | `/reports` | `(容器)` | 安全报告 | ✅ |
| 8 | `/scan` | `/index/index` | 资产扫描 | ✅ |
| 9 | `/config` | `/index/index` | 配置中心 | ✅ |
| 10 | `/ops` | `/index/index` | 运维管理 | ✅ |
| 11 | `/system` | `/index/index` | 系统管理 | ✅ |

## 角色（X1 权限矩阵）

| id | code | name | 启用 |
|---:|---|---|:-:|
| 1 | `admin` | 管理员 | ✅ |
| 2 | `user` | 普通用户 | ✅ |
| 3 | `readonly` | 只读用户 | ❌ |
| 4 | `test_role` | 测试角色 | ❌ |
| 25 | `operator` | 运维 | ✅ |
| 26 | `viewer` | 观察者 | ✅ |
| 27 | `auditor` | 审计人员 | ✅ |

## 部署拓扑（本地 .env 视角）

- **LOKI_API_URL**: `http://192.168.0.30:3100`
- **WAZUH_API_URL**: `https://192.168.0.40:55000`
- **OPENSEARCH_URL**: `https://192.168.0.40:9200`
- **GLM_MODEL**: `glm-4-flash`
- **DB_HOST**: `111.228.57.2`
- **DB_PORT**: `25432`
- **DB_NAME**: `AI-miniSOC-testdb`
- **DB_USER**: `aisoc`
- **BACKEND_PORT**: `8000`
- **BACKEND_CORS_ORIGINS**: `http://localhost:5173,http://192.168.0.42:5173`

## 生成命令

```bash
venv/bin/python scripts/sync_claude_md_truth.py
```
