# 上网行为异常检测模块详细设计

> 版本: v1.0
> 日期: 2026-08-03
> 状态: 设计完成，待开发
> 关联文档: [采集器集成架构设计](2026-06-07-collector-integration-architecture.md)、[TP-Link 路由器集成](2026-06-07-tplink-router-integration.md)
> 数据源: Loki (http://192.168.0.30:3100) — TP-Link TL-R479GP-AC 路由器上网行为日志

---

## 1. 背景与目标

### 1.1 背景

AI-miniSOC 当前通过 Loki 采集 TP-Link TL-R479GP-AC 路由器的上网行为日志（OTLP 推送），
日志记录了内网每台设备的**访问网址**和**使用的应用类型**。该数据是网络行为审计和安全检测的
高价值数据源，但目前**只采集不分析**，异常行为（恶意域名访问、数据外泄、C2 通信等）无法被发现。

### 1.2 目标

1. **自动化检测**：定时从 Loki 拉取上网行为日志，通过规则引擎识别 6 类异常行为
2. **事件化落地**：检测结果生成安全事件（`soc_incidents`），进入 AI-miniSOC 事件管理闭环
3. **实时通知**：高风险异常通过站内通知 + WebSocket 实时推送给运维人员
4. **可运营**：规则、阈值、黑名单均可在系统配置中调整，无需改代码
5. **可演进**：预留 AI 研判（Phase 2）和威胁情报（Phase 3）接入点

### 1.3 非目标

- 不将原始上网行为日志写入 OpenSearch（数据流原则：原始日志留 Loki，仅告警/事件进 OpenSearch）
- 不做实时流处理（当前量级 ~20万条/天，轮询足够；未来量级增长再评估 Loki ruler / 流式消费）
- 不做 HTTPS 解密 / 全量流量镜像（路由器日志本身不含这些能力）

---

## 2. 数据源分析（实测）

### 2.1 日志格式

日志由 TP-Link TL-R479GP-AC 路由器产生，经 OTLP exporter 推送到 Loki，格式为 syslog：

```
# 访问网址类
<13>Aug 03 22:28:08 TL-R479GP-AC behavior_ctl: 2026-08-03 22:28:08 <5> :
  上网行为:a:IPGROUP_ANY a:192.168.0.8 网站分组:所有网站 网址:main.vscode-cdn.net 。

# 使用应用类
<13>Aug 03 22:28:23 TL-R479GP-AC behavior_ctl: 2026-08-03 22:28:23 <5> :
  上网行为:a:IPGROUP_ANY a:192.168.0.9 apptype:网络基础协议 使用HTTP 。
```

### 2.2 字段提取

| 字段 | 提取方式 | 说明 |
|------|---------|------|
| `timestamp` | Loki 时间戳（纳秒） | 日志产生时间 |
| `ip` | Loki 标签 `ip` | 内网设备 IP（也可能是公网 IP，见 2.4） |
| `domain` | 正则 `网址[:：]\s*([^\s。]+)` | 访问的目标域名/URL |
| `apptype` | 正则 `apptype[:：]?\s*([^ ]+)` | 应用类型（网络基础协议/视频直播/云服务…） |
| `category` | 正则 `网站分组[:：]\s*([^ ]+)` | 网站分组（所有网站…）—— 可选 |
| `action` | 关键字 | `网址` 或 `apptype` 两种行为 |

### 2.3 标签与量级（2026-08-03 实测）

- 标签：`exporter=OTLP`、`service_name=LAG/unknown_service`、`host=192.168.0.30`、`ip=<54个>`
- 量级：24h 约 **20 万+ 条**，其中约 78% 为访问网址、22% 为使用应用
- 各 IP 域名访问量差异大（6h 去重域名：192.168.0.6→816、192.168.0.8→89），适合建立差异化基线
- 已观察到隧道/穿透类域名（`stun-heyuan-v6.easytier.cn`、`stun.225284.xyz`）

### 2.4 注意事项

- **IP 标签包含公网 IP**：路由器把部分公网 IP 也写入 `ip` 标签（如 `8.160.215.x`），
  解析后需区分内网/公网，公网 IP 行为不参与内网基线检测
- **同一日志重复推送**：Loki 中同一事件存在重复条目（实测同一时间戳多条相同内容），
  检测需按 `(ip, domain, 秒级时间戳)` 去重后再统计

---

## 3. 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI-miniSOC Backend                        │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  BrowsingDetectorScheduler（后台定时任务，lifespan 启动）    │  │
│  │                                                           │  │
│  │   ┌──────────┐   ┌──────────┐   ┌──────────────────┐      │  │
│  │   │ LokiClient│→  │ LogParser│→  │ RuleEngine(6类)  │      │  │
│  │   │ (query_range) │ (字段提取)  │  │ 打分+去重+聚合    │      │  │
│  │   └──────────┘   └──────────┘   └──────────────────┘      │  │
│  │                                  │  分值 ≥ 阈值            │  │
│  │                                  ▼                        │  │
│  │                       ┌────────────────────┐              │  │
│  │                       │ EventService       │              │  │
│  │                       │ ①写 soc_browsing_events            │  │
│  │                       │ ②写 soc_incidents（复用现有API逻辑） │  │
│  │                       │ ③NotificationService.create()     │  │
│  │                       └────────────────────┘              │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │ WS 推送                              │
│  ┌────────────────────┐  │   ┌────────────────────────────┐    │
│  │ soc_system_config  │◄─┼─►│ 前端「行为检测」页面             │    │
│  │ （规则/阈值/开关）    │  │   │ 事件列表/详情/处置/规则配置    │    │
│  └────────────────────┘  │   └────────────────────────────┘    │
│                          │                                     │
│  ┌────────────────────┐  │   ┌────────────────────────────┐    │
│  │ soc_browsing_events│  │   │ soc_incidents（事件管理复用） │    │
│  │ soc_browsing_baseline │  │   + soc_notifications          │    │
│  └────────────────────┘  │   └────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
         ▲                                      │
         │ Loki API（每 N 分钟轮询）               │
┌────────┴───────────┐                 ┌─────────▼──────────┐
│  Loki (192.168.0.30:3100)            │  AI 研判(可选,Phase2)│
│  路由器上网行为日志                     │  AIAnalysisService  │
└────────────────────┘                 └────────────────────┘
```

**设计决策**：采用**后端轮询**而非 Loki Ruler / 实时流，理由：

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| 后端定时轮询 | 可结合 PG 基线/威胁情报/AI；事件直接入库；无新增组件 | 有 1 个周期延迟 | ✅ 首选 |
| Loki Ruler | 零代码、LogQL 简单规则 | 告警落地要接 alertmanager；无法做基线偏离/AI | 二期可选补充 |
| 实时流消费 | 延迟最低 | 复杂度高，当前量级不需要 | 量级增长后评估 |

---

## 4. 检测规则引擎设计

### 4.1 规则总览

6 类规则，每条规则输出一个分值，总分 ≥ 阈值触发告警。规则可在 `soc_system_config` 中启用/停用、调参。

| # | 规则 | 权重分 | 判定逻辑 | 检测风险 |
|---|------|--------|---------|---------|
| R1 | 恶意域名命中 | 100 | 域名命中黑名单（本地维护 + 可选威胁情报） | 木马/钓鱼/挖矿 C2 |
| R2 | 突发高频访问 | 40 | 窗口内 同IP访问同域名次数 ≥ 阈值 | 数据外泄、C2 心跳 |
| R3 | 基线偏离 | 20 | 访问该IP历史(7天)未见过的域名 | 新型 C2、异常行为 |
| R4 | 隧道/穿透工具 | 35 | 域名匹配隧道关键词正则 | 内网穿透、数据回传 |
| R5 | 凌晨活跃 | 15 | 02:00-05:00 时段访问量突增 | 自动化攻击、僵尸主机 |
| R6 | 可疑域名特征 | 15 | 域名高熵/随机子域/超长/IP直连 | DGA 恶意软件 |

### 4.2 打分与触发

```
score = Σ(命中规则权重)
触发阈值（默认）: score ≥ 50 → 生成事件；score ≥ 100 → 严重告警直发通知
severity 映射:
  score ≥ 100 → critical
  score ≥  80 → high
  score ≥  50 → medium
  其余（R3 低频命中）→ low
```

- **R1 命中直接告警**（100 分直接达 critical）
- **聚合**：同一窗口内同 `(ip, domain)` 命中多条规则时只生成一条事件，`score` 取最高单次分值，`rule_hits` 字段记录命中的规则列表
- **抑制**：同一 `(ip, domain)` 生成事件后进入 30 分钟抑制期（防刷屏），抑制期结束且仍命中才再次生成

### 4.3 规则详细定义

**R1 恶意域名命中**
- 黑名单来源（三级，优先级从高到低）：
  1. 系统配置 `browsing_detection.blacklist_domains`（手动维护，逗号分隔）
  2. 数据库表 `soc_browsing_blacklist`（可经 API 维护，支持通配 `*.xxx.com`）
  3. 威胁情报 API（二期接入，见 §9）
- 匹配：域名精确匹配或通配符后缀匹配

**R2 突发高频访问**
- 窗口：`window_minutes`（默认 5 分钟）
- 条件：同 IP 访问同一域名次数 > `burst_threshold`（默认 30 次/窗口）
- 需先按 `(ip, domain, 秒级时间戳)` 去重（数据存在重复推送）

**R3 基线偏离**
- 基线来源：`soc_browsing_baseline`（§5.3）
- 条件：`domain NOT IN (该IP近7天访问域名集合)`
- 误报控制：仅当该 IP 当窗口域名访问数 ≥ 3 时评估（过滤一次性噪声）；新增域名仅记分不直接告警

**R4 隧道/穿透工具**
- 关键词正则（可配置）：
  ```
  easytier|stun|frp|fatedier|zerotier|tailscale|n2n|wireguard|tinc|nebula|innernet
  ```
- 条件：domain 命中正则

**R5 凌晨活跃**
- 时段：`night_start_hour`(默认2) ~ `night_end_hour`(默认5)
- 条件：该 IP 在窗口内凌晨日志数 ≥ `night_count_threshold`（默认 5）
- 实测凌晨基线≈0，出现即异常

**R6 可疑域名特征**
- 条件（任一命中）：
  - 域名整体 Shannon 熵 ≥ 4.0（不含 TLD）
  - 子域为纯随机字符（≥ 12 位且非词典词）
  - 域名长度 ≥ 63（DNS 上限）
  - 无域名（直接 IP 形式访问，如 `http://203.119.206.x`）
- 注意：CDN 动态子域（`sg.tgalileo.com` 等）可能误报，命中后仅计分，须配合 R2/R3 综合判断

### 4.4 白名单机制

- 系统配置 `browsing_detection.whitelist_domains`：全局白名单域名，不参与任何检测
- 系统配置 `browsing_detection.whitelist_ips`：免检 IP（如监控探针、打印服务器）
- 误报事件可在前端一键加入白名单（写入配置或 `soc_browsing_blacklist` 反向表）

---

## 5. 数据模型设计

### 5.1 新表：`soc_browsing_events`（异常检测事件）

检测引擎输出，供前端列表/详情/处置使用。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK, default gen_random_uuid() | 主键 |
| ip | String(45) | NOT NULL, index | 异常源 IP（内网设备） |
| domain | String(255) | NOT NULL, index | 异常域名 |
| apptype | String(50) | NULL | 相关应用类型（如有） |
| score | Integer | NOT NULL | 触发分值 |
| severity | String(20) | NOT NULL | critical/high/medium/low |
| rule_hits | JSONB | NOT NULL | 命中的规则列表 `[{"rule":"R2","weight":40},...]` |
| source_count | Integer | NOT NULL | 窗口内原始日志条数 |
| window_start | DateTime(tz) | NOT NULL | 检测窗口开始 |
| window_end | DateTime(tz) | NOT NULL | 检测窗口结束 |
| status | String(20) | NOT NULL, default 'new' | new/confirmed/false_positive/resolved/ignored |
| incident_id | UUID | FK soc_incidents.id, NULL | 关联事件（如有生成） |
| ai_analysis_id | UUID | FK soc_ai_analyses.id, NULL | AI 研判结果（二期） |
| created_at | DateTime(tz) | default now() | 创建时间 |
| resolved_at | DateTime(tz) | NULL | 处置时间 |
| resolution_note | Text | NULL | 处置备注 |

索引：`ix_browsing_events_ip_domain (ip, domain)`、`ix_browsing_events_created (created_at)`

### 5.2 新表：`soc_browsing_blacklist`（恶意域名黑名单）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BigInteger | PK, autoincrement |
| domain | String(255) | NOT NULL, unique | 域名，支持通配 |
| source | String(50) | 来源（manual / threat_intel） |
| reason | String(255) | 备注 |
| created_by | BigInteger | FK soc_users.id |
| created_at | DateTime(tz) | |

### 5.3 新表：`soc_browsing_baseline`（IP×域名基线）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BigInteger | PK, autoincrement |
| ip | String(45) | NOT NULL, index |
| domain | String(255) | NOT NULL |
| first_seen | DateTime(tz) | 首次出现 |
| last_seen | DateTime(tz) | 最近出现 |
| total_count | BigInteger | 累计访问次数 |
| unique_key | String | `ip:domain` 唯一键 |

唯一约束：`(ip, domain)`。基线滚动维护：仅保留近 7 天有访问的记录（每日清理 `last_seen < now()-7d`）。

### 5.4 复用现有表

- `soc_incidents`：异常事件升级为安全事件（status=open、severity 映射、created_by='browsing-detector'、wazuh_alert_id 留空，新增 `source` 概念见 §6.3）
- `soc_notifications`：站内通知，`type='alert'`，`link` 指向事件详情页
- `soc_system_config`：规则配置，`category='browsing_detection'`

---

## 6. 后端服务与 API 设计

### 6.1 新增服务（`app/services/browsing_detection/`）

```
browsing_detection/
├── __init__.py
├── loki_client.py      # Loki API 客户端（query_range / 解析）
├── log_parser.py       # 日志解析（提取 ip/domain/apptype/去重）
├── rule_engine.py      # 6 类规则 + 打分 + 抑制
├── baseline_service.py # 基线读写/清理
├── event_service.py    # 事件入库 + 升级 soc_incidents + 通知
└── scheduler.py        # 后台调度（lifespan 启动）
```

**LokiClient**（参考 `alert_query.py` 的 httpx 模式）：
```python
class LokiClient:
    def __init__(self, base_url: str = settings.LOKI_API_URL):
        self._client = httpx.Client(base_url=base_url.rstrip("/"))

    def query_range(
        self,
        query: str,
        start_ns: int,
        end_ns: int,
        limit: int = 10000,
    ) -> list[dict]:
        """GET /loki/api/v1/query_range，返回 result 流列表"""
```

**Scheduler**（lifespan 后台任务）：
```python
async def run_browsing_detector() -> None:
    """每 interval_seconds 执行一轮检测"""
    while True:
        try:
            await run_detection_once()   # 拉取→解析→规则→落库→通知
        except Exception:
            logger.exception("browsing detection failed")
        await asyncio.sleep(interval_seconds)
```

启动挂载（`main.py`）：
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(run_browsing_detector())  # 受 BROWSING_DETECT_ENABLED 开关控制
    yield
    task.cancel()
```

### 6.2 新增 API（`app/api/browsing.py`，前缀 `/api/v1/browsing`）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/events` | 异常事件分页列表（ip/severity/status/时间范围筛选） | 需登录 |
| GET | `/events/{id}` | 事件详情（含 rule_hits） | 需登录 |
| PUT | `/events/{id}` | 更新处置状态（confirmed/false_positive/resolved/ignored） | 需登录 |
| POST | `/events/{id}/whitelist` | 一键加入白名单 | 需登录 |
| GET | `/baseline` | 基线查看（ip → 域名列表，可搜索） | 需登录 |
| GET | `/blacklist` | 黑名单列表 | 需登录 |
| POST | `/blacklist` | 添加黑名单域名 | 管理员 |
| DELETE | `/blacklist/{id}` | 删除黑名单域名 | 管理员 |
| GET | `/stats` | 统计（今日异常数/等级分布/命中规则分布） | 需登录 |
| POST | `/rules/test` | 规则试运行（指定时间窗口回放，不入库） | 管理员 |
| GET | `/rules/config` | 读取规则配置（来自 soc_system_config） | 需登录 |

### 6.3 事件升级到 `soc_incidents`

当事件 `severity >= high` 时，自动创建 `soc_incidents` 记录：

| soc_incidents 字段 | 值 |
|--------------------|-----|
| title | `[上网行为] {ip} 异常访问 {domain}` |
| description | 规则命中明细 + 窗口统计 + 关联日志样例 |
| status | `open` |
| severity | 按分值映射（§4.2） |
| created_by | `browsing-detector`（系统） |
| resolved_at | NULL |

> 现有 `soc_incidents` 无 source 字段，一期复用 `created_by='browsing-detector'` 区分来源；
> 二期若需与 Wazuh 事件混合筛选，可加 `source` 字段（`wazuh` / `browsing` / `manual`）。

### 6.4 通知

```python
# event_service.py 内部
await NotificationService(db).create(
    user_id=notify_user_id,          # 配置 browsing_detection.notify_user_ids
    type="alert",
    title=f"[上网行为异常] {ip} 访问 {domain}",
    content=f"分值 {score}，命中规则 {rule_names}，详情见事件中心",
    link=f"/#/browsing/event/{event_id}",  # 前端路由
    push_ws=True,                    # 复用 ws_manager 实时推送
)
```

- 仅 `severity >= high` 触发通知（防骚扰）
- `notify_user_ids` 默认取管理员用户列表

---

## 7. 配置设计（`soc_system_config`，category=`browsing_detection`）

| key | value_type | 默认值 | 说明 |
|-----|-----------|--------|------|
| enabled | bool | true | 检测总开关 |
| interval_seconds | int | 300 | 轮询间隔（秒） |
| window_minutes | int | 5 | 检测窗口（分钟） |
| score_threshold | int | 50 | 触发阈值 |
| severity_high | int | 80 | high 分界 |
| severity_critical | int | 100 | critical 分界 |
| burst_threshold | int | 30 | R2 高频阈值（次/窗口） |
| night_start_hour | int | 2 | R5 凌晨起始 |
| night_end_hour | int | 5 | R5 凌晨结束 |
| night_count_threshold | int | 5 | R5 凌晨条数阈值 |
| tunnel_keywords | string | easytier\|stun\|frp\|zerotier\|tailscale\|n2n\|wireguard | R4 正则 |
| blacklist_domains | text | 空 | R1 手动黑名单（逗号分隔） |
| whitelist_domains | text | 空 | 全局白名单域名 |
| whitelist_ips | text | 空 | 免检 IP |
| suppress_minutes | int | 30 | 事件抑制期（分钟） |
| notify_user_ids | string | 空(默认管理员) | 通知目标用户 ID |
| baseline_days | int | 7 | 基线保留天数 |
| rules_enabled | string | R1,R2,R3,R4,R5,R6 | 启用的规则集合 |

规则配置在启动时和每轮检测前从 DB 读取（带缓存，配置变更 60 秒内生效）。

---

## 8. 前端设计（概要）

新增页面「行为检测」：`src/frontend/src/views/browsing/`，菜单挂在「安全检测」分组下。

| 页面 | 路由 | 核心功能 |
|------|------|---------|
| 事件列表 | `/browsing/event/index` | 分页表格（时间/IP/域名/severity/规则/状态），筛选，状态操作 |
| 事件详情 | `/browsing/event/detail` | 规则命中明细、原始日志样例、关联事件、处置 |
| 黑名单管理 | `/browsing/blacklist` | 黑名单 CRUD（管理员） |
| 规则配置 | `/browsing/config` | 读取/保存 `soc_system_config` 规则项 |

复用现有组件：`useTable`、`ArtButtonTable`、`v-auth` 权限指令、`ElTag` severity 配色。
API 封装：`src/frontend/src/api/browsing.ts`（与后端 §6.2 一一对应）。

---

## 9. 威胁情报集成（二期）

| 阶段 | 来源 | 方式 | 更新频率 |
|------|------|------|---------|
| 一期 | 手动维护 + 本地黑名单表 | API 维护 | 手动 |
| 二期 | abuse.ch URLhaus | 定时拉取恶意 URL/域名列表入库 `soc_browsing_blacklist` | 每小时 |
| 二期 | PhishTank | 同上 | 每 4 小时 |
| 三期 | 商用情报（微步/奇安信等） | API 批量查询域名信誉 | 实时/每日 |

R1 规则保持同一接口，黑名单数据源解耦，可随时切换。

---

## 10. 开发任务拆解（里程碑）

### M1：检测管道骨架（2~3 天）
- [ ] `loki_client.py` + `log_parser.py`（含去重）
- [ ] 数据模型：`soc_browsing_events`、`soc_browsing_blacklist`、`soc_browsing_baseline`（alembic 迁移或 create_all）
- [ ] `scheduler.py` + `main.py` lifespan 接入（enabled 开关）
- [ ] 系统配置项初始化脚本（`browsing_detection` category）

### M2：核心规则 R1 + R2 + R4（2~3 天）
- [ ] `rule_engine.py`：黑名单/高频突发/隧道工具
- [ ] `event_service.py`：事件入库 + 升级 soc_incidents + 通知
- [ ] 单测：构造样例日志验证检测与打分

### M3：基线规则 R3 + R5 + R6（2~3 天）
- [ ] `baseline_service.py`：基线写入/查询/清理
- [ ] R3 基线偏离、R5 凌晨活跃、R6 域名特征
- [ ] 白名单机制

### M4：API + 前端（3~4 天）
- [ ] 后端 `/api/v1/browsing/*` 全部端点
- [ ] 前端 4 个页面 + API 封装 + 菜单/权限
- [ ] 联调、页面验收

### M5：AI 研判与加固（2~3 天，Phase 2 联动）
- [ ] 高风险事件自动触发 `AIAnalysisService` 生成研判结论
- [ ] `ai_analysis_id` 关联、事件详情展示 AI 结论
- [ ] 规则误报统计、配置热生效优化

### M6：威胁情报（二期）
- [ ] URLhaus / PhishTank 定时同步入库
- [ ] 黑名单命中溯源展示

---

## 11. 运维与监控

- **任务健康**：scheduler 每轮记录执行日志（耗时、拉取条数、命中数、错误数）
- **可观测**：在 `/metrics` 暴露 `browsing_detection_runs_total`、`browsing_detection_errors_total`、`browsing_detection_last_run_seconds`
- **开关**：`browsing_detection.enabled=false` 立即停用；改配置无需重启
- **DB 容量**：`soc_browsing_events` 预计 < 100 条/天（抑制后），基线表按 7 天滚动清理，均无容量压力

## 12. 风险与注意事项

| 风险 | 影响 | 缓解 |
|------|------|------|
| 公网 IP 混入 ip 标签 | 误报 | 解析时区分内网/公网，公网只记录不检测 |
| 日志重复推送 | 计数虚高触发 R2 误报 | 秒级去重后再统计 |
| CDN 动态子域触发 R6 | 误报 | R6 仅计分；白名单；与 R2/R3 综合 |
| 路由器日志中断（已知问题） | 检测空转 | scheduler 记录错误并告警（复用通知系统） |
| 夜间测试环境误报 | 噪音 | 白名单 + suppress 抑制期 |
| 单进程定时任务（多 worker 部署） | 重复执行 | 一期文档声明仅单 worker；二期加 PG 锁/Redis 锁 |

## 13. 附录：Loki 查询示例（LogQL）

```bash
# 取窗口日志（解析在代码内完成）
curl -G http://192.168.0.30:3100/loki/api/v1/query_range \
  --data-urlencode 'query={exporter="OTLP"}' \
  --data-urlencode 'start=<start_ns>' \
  --data-urlencode 'end=<end_ns>' \
  --data-urlencode 'limit=10000'

# 隧道工具实时筛查（R4 快速验证用）
{exporter="OTLP"} |~ "easytier|stun|frp|zerotier"

# 高频突发（R2，Loki 侧预筛可选）
sum by (ip) (count_over_time({exporter="OTLP"} |= "网址"[5m])) > 30
```

---

**文档结束。** 后续开发按 §10 里程碑推进，每个里程碑实现后补充实现文档与测试报告。
