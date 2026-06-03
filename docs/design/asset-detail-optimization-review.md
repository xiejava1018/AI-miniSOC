# 资产详情页 SOC 视角体检报告

**文档版本**: v1.0
**创建日期**: 2026-06-02
**最后更新**: 2026-06-03
**作者**: Claude（基于 `/Users/xiejava/AIproject/AI-miniSOC/src/frontend/src/views/asset/detail/index.vue` 全文审阅）

---

## 📋 文档说明

本文档从 SOC（安全运营中心）日常使用场景出发，对资产详情页进行一次体检，识别当前实现的盲点与可优化点，并给出落地优先级建议，供产品决策参考。

**当前文件**: `src/frontend/src/views/asset/detail/index.vue`（约 543 行）

**v1.1 更新重点**: 新增"主机应用清单 + 漏洞"核心缺口（基于 Wazuh agent syscollector + vulnerability-detector 的集成方案）

---

## 🎯 体检范围

- 顶部基本信息卡片（13 个字段）
- 4 个 Tab：端口管理、标签管理、关联事件（注：原代码实际为 3 个 Tab，端口/标签/事件）
- 2 个弹窗：端口弹窗、标签弹窗
- 数据接口：后端已有 `/api/v1/alerts?ip=xxx` 告警接口，前端未消费

---

## 🔴 核心缺口（不进 SOC 关键场景）

### 1. 缺"告警"Tab — 致命

**现状**：
- 详情页只有"关联事件"Tab，显示的是已经工单化的 `soc_incidents` 数据
- 后端 `/api/v1/alerts`（基于 Wazuh OpenSearch 实时查询）支持 `?ip=xxx` 按 IP 过滤告警
- 前端 `src/frontend/src/api/` 下**完全没有 alert.ts 封装**

**为什么致命**：
- SOC 运维的第一反应是看**原始告警**（可能是攻击信号但还没人工处理）
- 工单化的事件是滞后指标，攻击可能正在进行但未触发开单流程
- 现在的"关联事件"对 SOC 来说信息延迟太大

**修复**：
- 前端新增 `src/frontend/src/api/alert.ts` 封装 `getAlertsByIp(ip, hours, level)`
- 详情页加"告警"Tab 在最前
- 表格列：时间 / 等级（高危红） / 规则描述 / 状态

---

### 2. 缺"安全摘要" — 致命

**现状**：
- 进入资产详情第一眼看到的是 IP/名称/MAC/网络段等**身份元数据**
- 这些信息 SOC 早已在告警里看过，进详情是想看"现在安不安全"

**为什么致命**：
- SOC 进详情页的 90% 场景是"这个 IP 出事了，过来看看怎么回事"
- 现在的体验是"看半天才能找到告警数"——违背 SEC（Security Event Control）黄金 10 秒原则

**修复**（在基本信息卡片上方插入安全摘要区）：

```vue
<ElCard class="security-summary">
  <div class="metric-row">
    <MetricCard label="24h 告警" :value="alertCount24h" type="danger" />
    <MetricCard label="高危告警" :value="criticalAlertCount" type="warning" />
    <MetricCard label="未关闭事件" :value="openIncidentCount" type="info" />
    <MetricCard label="数据新鲜度" :value="scanFreshness" type="success" />
    <MetricCard label="在线状态" :value="onlineStatus" :type="onlineType" />
  </div>
</ElCard>
```

**指标来源**：
- 告警数：调 `/api/v1/alerts/statistics?hours=24`
- 事件数：`soc_asset_incidents` JOIN `soc_incidents` WHERE status != 'closed'
- 扫描新鲜度：端口表最大 `scan_time` → "X 天前"或"已过期"
- 在线状态：`asset_status` 字段

---

### 3. 端口风险盲

**现状**：
- 端口表只显示端口号/协议/状态/服务/版本
- 22/3389/445/3306/1433 这种高危端口和 8080 一样显示，无差别

**为什么致命**：
- 端口管理是**暴露面**的核心数据
- SOC 看端口表最关心"哪些是高危的、能不能关"
- 现在的体验是 SOC 得自己记哪些端口高危

**修复**：
- 在端口表加"风险等级"列
- 预设高危端口库（前端常量即可，无需后端）：
  - 远程访问：22(SSH), 3389(RDP), 23(Telnet)
  - 数据库：3306(MySQL), 1433(SQL Server), 5432(PostgreSQL), 27017(MongoDB), 6379(Redis)
  - 文件共享：445(SMB), 139(NetBIOS), 21(FTP)
  - 控制/管理：2375(Docker), 9200(ES), 5601(Kibana)
- 命中高危的端口整行 ElTag danger 色 + "高危"标签
- 表格头部加"仅看高危"过滤器

---

### 4. 缺"主机应用清单" + "主机漏洞"视图 — 致命

**现状**：
- 详情页只有"端口管理"Tab，显示端口/协议/服务/版本
- `soc_asset_ports` 表虽然有 `service` / `version` 字段，但**没有聚合视图**——一台机器跑了 nginx 监听 80/443 两条记录，看不出是同一个应用
- `soc_asset_ports.vulnerability` 字段在 schema 里**已建**（`Column(Text)`，注释是"已知CVE漏洞信息（逗号分隔）"），但前端**完全没有展示**
- **Wazuh agent 本身具备完整的主机应用采集 + 漏洞检测能力，但本项目后端 Wazuh 客户端没接：**

```python
# app/services/wazuh_client.py 当前实现
def get_agents(self)               # ✅ 有
def get_alerts(...)                # ✅ 有
def get_syscheck(...)              # ✅ 有 (FIM)
def get_agent_sysinfo(self, ...)   # ✅ 有 (hardware)
# ❌ 没有: get_agent_packages()
# ❌ 没有: get_agent_processes()
# ❌ 没有: get_agent_vulnerabilities()
# ❌ 没有: get_agent_vuln_last_scan()
```

**为什么致命**：
- SOC 看资产的第一诉求是"这台机器跑了什么应用、有什么已知漏洞"——这是**暴露面管理（ASM）和漏洞管理的核心数据**
- 现在 SOC 要进 Wazuh Dashboard 单独查，体验割裂
- `soc_asset_ports.vulnerability` 字段已经在 schema 躺着，是**沉没成本**——必须接 Wazuh 把它填上

**Wazuh 提供的现成能力**（v4.x API）：

| 能力 | Wazuh API 端点 | 数据样例 |
|---|---|---|
| 已安装软件包 | `GET /syscollector/{agent_id}/packages?limit=500&offset=0` | `{"vendor":"Canonical","name":"openssl","version":"1.1.1f-1ubuntu2","architecture":"amd64"}` |
| 运行进程 | `GET /syscollector/{agent_id}/processes?limit=500` | `{"pid":1234,"name":"nginx","cmd":"nginx: worker"}` |
| 监听端口 | `GET /syscollector/{agent_id}/ports?limit=500` | `{"protocol":"tcp","local_port":80,"state":"listening"}` |
| 已发现漏洞 | `GET /vulnerability/{agent_id}?limit=500` | `{"cve":"CVE-2021-23017","severity":"High","cvss3_score":7.7,"package":{"name":"openssl","version":"1.1.1f"}}` |
| 漏洞扫描时间 | `GET /vulnerability/{agent_id}/last_scan` | `{"last_full_scan":"2026-06-01T10:30:00Z","last_partial_scan":"..."}` |

**修复方案（按 Wazuh 集成深度分 3 档）**：

#### 档位 A：前端纯展示层（半天，0 后端）
- 前端在"端口管理"Tab 紧邻位置加"应用清单"Tab
- 列：应用名 | 版本 | 厂商 | 架构 | 来自端口 | 操作
- 把当前端口表 `vulnerability` 字段读出来，逗号拆成 ElTag 列表
- 优点：零后端，立即可见
- 缺点：还是端口视角，没"应用"概念

#### 档位 B：Wazuh API 全量接入（推荐，1-2 天）
- 后端 `wazuh_client.py` 加 4 个方法：
  - `get_agent_packages(agent_id, limit, offset)` → 调 `/syscollector/{agent_id}/packages`
  - `get_agent_processes(agent_id)` → 调 `/syscollector/{agent_id}/processes`
  - `get_agent_vulnerabilities(agent_id, severity, limit, offset)` → 调 `/vulnerability/{agent_id}`
  - `get_agent_vuln_last_scan(agent_id)` → 调 `/vulnerability/{agent_id}/last_scan`
- 新建 `src/backend/app/api/wazuh_assets.py` 暴露 4 个端点：
  - `GET /api/v1/wazuh/agents/{agent_id}/packages`
  - `GET /api/v1/wazuh/agents/{agent_id}/vulnerabilities?severity=Critical,High`
  - `GET /api/v1/wazuh/agents/{agent_id}/vuln-last-scan`
  - `GET /api/v1/wazuh/agents/{agent_id}/processes`（可选）
- 详情页新增 2 个 Tab：
  - **应用清单**（读 packages）：表格列 `应用名 | 版本 | 厂商 | 架构 | 操作`
  - **漏洞列表**（读 vulnerabilities）：表格列 `CVE | 严重性 | CVSS3 | 影响包 | 修复版本 | 操作`；头部加 `Critical: 0 | High: 0 | Medium: 0` 计数
- 关联：在端口表里识别 `service` 来自哪个 package，加"应用"列
- 优点：SOC 一站式看到"应用 + 漏洞 + 暴露面"全貌
- 缺点：每次进详情页要调 Wazuh API，需考虑**缓存**（建议 1 小时 Redis 或 DB 缓存表）

#### 档位 C：本地快照 + 周期同步（重量，3-5 天）
- 在 B 的基础上，把 packages / vulnerabilities 同步到本地 `soc_asset_packages` / `soc_asset_cves` 表
- 定时任务（每 1-6 小时）从 Wazuh 拉增量
- 优点：详情页秒开、可以做"全公司高危漏洞 TOP10"
- 缺点：要建 2 张新表 + 同步任务 + 增量逻辑
- **适合**：未来做漏洞管理模块时一起做

**建议落地：先 A 占位 + 同步实现 B，C 待 B 跑稳后再评估**

---

## 🟡 重要增强

### 4. 标签管理 hardcode — 应该字典驱动

**现状**：
```typescript
// detail/index.vue:369-384
const commonTagKeys = [
  { label: '环境 (environment)', value: 'environment' },
  { label: '业务系统 (business_system)', value: 'business_system' },
  // ...
  { label: '数据分类 (data_classification)', value: 'data_classification' }
]

const tagKeyOptionsMap: Record<string, string[]> = {
  environment: ['production', 'staging', 'development', 'testing'],
  // ...
}
```

**问题**：
- 5 个常用标签键 + 可选值**硬编码在 Vue 文件**
- 团队要加新标签键必须改前端代码 + 发版
- 多人协作完全靠开发者自觉

**修复**：
- 在 `soc_dicts` 里建一个 `dict_type='asset_tag_key'` 字典
- 标签键的 value 选项也用 `soc_dicts`（每条 dict 的子项管理 value）
- 或更轻量：单独建一个 `soc_tag_presets` 配置表
- 取舍：考虑到现有 `soc_dicts` 已经是键值对，优先复用，把每个 tag key 作为一个 dict_type，每个可选 value 作为一个 dict item

---

### 5. 缺"数据分类"独立字段

**现状**：
- 现在只能通过 `soc_asset_tags` 手动加 `data_classification` 标签
- 标签可以多选，不能强约束"必须有一个"

**为什么重要**：
- 数据分类（公开/内部/机密/秘密）是**合规基础字段**
- 等保 2.0、ISO27001、GDPR 都要求资产有数据敏感度分级
- SOC 做数据泄露事件时，第一时间要知道这个资产存的是什么级别的数据

**修复**：
- `soc_assets` 加 `data_classification VARCHAR(20) CHECK IN ('public','internal','confidential','secret')` 字段
- 配套 `soc_dicts` 加 `dict_type='data_classification'`
- 表单 / 详情 / 列表 都加这一列
- 顶部安全摘要可用此字段高亮（机密/秘密资产红框警示）

---

### 6. 缺"基线合规"信息

**现状**：
- 完全没有任何"是否符合安全基线"的信息
- SOC 无法判断"这个资产是不是已经偏离基线"

**修复方向**（P2，先占位）：
- 在基本信息卡片加"安全基线"描述项
- 字段可以是 `baseline_compliance VARCHAR(20)`，值 'compliant' / 'deviation' / 'unknown'
- 短期 V1：默认填 'unknown'，等基线扫描模块上线后再接
- 长期：关联漏洞扫描结果自动判定

---

### 7. 缺"联系方式"

**现状**：
- `owner VARCHAR(255)` 只能填名字或邮箱字符串
- 实际工单化时需要电话、备用联系人

**修复**（P2，可选）：
- 加 `owner_contact VARCHAR(50)` （电话）
- 加 `backup_owner VARCHAR(255)` （备用负责人）
- 表单里用 input tag 提示格式

---

### 8. 扫描数据新鲜度可视化

**现状**：
- 端口表有"扫描时间"但只用 `toLocaleString('zh-CN')` 显示
- 看不出"这是 3 天前的数据还是 3 个月前的"

**修复**：
- 加 `formatRelativeTime()` 工具函数：
  - < 1h："刚刚"
  - < 24h："X 小时前"
  - < 7d："X 天前"
  - >= 7d："X 周前"（黄）
  - >= 30d："过期"（红）
- 端口表用相对时间，鼠标 hover 显示绝对时间
- 顶部"安全摘要"展示"最后扫描：3 天前"

---

## 🟢 锦上添花

### 9. Tab 加未读数 / 计数

**现状**：
- Tab 标题只有"端口管理""标签管理""关联事件"

**修复**：
```vue
<ElTabPane :label="`告警 (${alertCount})`" name="alerts" />
<ElTabPane :label="`事件 (${openIncidentCount}/${totalIncidentCount})`" name="incidents" />
```
- "告警 (5)" → "事件 (3/12)" 立刻知道有 3 件未处理 / 共 12 件

---

### 10. 状态色强化

**现状**：
- `asset_status` 的字典 color 在前端配置，Tag 显示相应颜色
- 但"离线"和"已删除"如果配的是 'info'，视觉警示不够

**修复**：
- 校验字典 seed：
  - `active` → success
  - `inactive` → warning
  - `retired` → danger
- 在线状态在顶部安全摘要里用大色块显示

---

### 11. 描述项支持 Markdown（可选）

**现状**：
- `asset_description` 是纯文本
- 实际运维场景：负责人会想写"该资产 23 点自动重启，注意..."

**修复**：
- 用 `md-editor-v3` 或简单 `marked` 渲染
- 表单改 `<MdEditor />` 组件
- 详情页渲染 Markdown

---

## 📊 落地优先级建议

| 优先级 | 工作 | 价值 | 工作量 | 依赖 |
|---|---|---|---|---|
| **P0** | 加告警 Tab（后端已有 + 前端封装 + 表格） | SOC 核心场景 | 中（1-2h） | 无 |
| **P0** | 顶部加"安全摘要"卡片 | 进页第一眼 | 中（2h） | 告警 Tab |
| **P0** | 应用清单 Tab（档位 A 端口表聚合 + 读 `vulnerability` 字段） | 暴露面 + 漏洞视图基础 | 小（0.5h） | 无 |
| **P0** | Wazuh 客户端加 packages / vulnerabilities 方法（档位 B 后端） | 接 Wazuh 主数据源 | 中（1-2h） | 无 |
| **P0** | 漏洞列表 Tab（档位 B 前端，调用 Wazuh vulnerabilities） | 漏洞视图 | 中（1-2h） | Wazuh 方法 |
| **P1** | 端口表加"风险等级"列 + 高危标红 | 暴露面研判 | 小（0.5h） | 无 |
| **P1** | 标签键改字典驱动 | 多人协作基础 | 中（1-2h） | 需 `soc_dicts` 配合 |
| **P1** | Tab 标题加未读数 | 信息密度 | 小（0.5h） | P0 |
| **P1** | Wazuh API 响应加缓存（1h Redis 缓存 packages/vulns） | 详情页响应 | 中（1-2h） | P0 漏洞 Tab |
| **P2** | 加"数据分类"字段（schema + 迁移 + 表单 + 列表） | 资产分级 | 中（2h） | DB 迁移 |
| **P2** | 相对时间显示 | 体感 | 小（0.5h） | 无 |
| **P2** | 状态色强化 | 视觉警示 | 极小（0.2h） | 改字典 seed |
| **P2** | 应用/CVE 本地快照表（档位 C） | 全局漏洞视图 | 大（3-5d） | P0 跑稳后 |
| **P3** | 缺"基线合规"信息 | 合规基础 | 大（先占位） | 等基线扫描模块 |
| **P3** | 缺"联系方式"独立字段 | 应急联系 | 小（0.5h） | DB 迁移 |
| **P3** | 描述项 Markdown | 内容表达 | 中（1h） | 引入组件 |

---

## 🚀 建议落地顺序

**第一批（P0，约 1.5 个工作日）**：
1. 加告警 Tab（前端 alert.ts + Tab 表格）
2. 加安全摘要卡片
3. Wazuh 客户端扩展：加 `get_agent_packages` / `get_agent_vulnerabilities` / `get_agent_vuln_last_scan` 3 个方法
4. 应用清单 Tab（调用 Wazuh packages API，缓存 1h）
5. 漏洞列表 Tab（调用 Wazuh vulnerabilities API，缓存 1h）
6. 端口表加 `vulnerability` 字段展示（逗号拆 CVE 列表）
7. 端口风险标红
8. 标签字典化
9. Tab 未读数

**第二批（P2，约 0.5 个工作日）**：
- 数据分类字段（带迁移）
- 相对时间
- 状态色调整
- Wazuh API 响应加 Redis 缓存（如果第一批已经做了内存缓存可延后）

**第三批（P3，待 P0/P1/P2 完成后再评估）**：
- 应用/CVE 本地快照表（档位 C）
- 基线合规占位
- 联系方式字段
- 描述 Markdown

---

## ❓ 待确认事项

1. **告警 Tab 性能**：高流量资产 24h 内可能有上千条告警，是否需要分页/虚拟滚动？
2. **安全摘要刷新频率**：详情页默认进入刷新一次，停留多久后自动刷新？
3. **数据分类是否要强制必填**：合规角度建议必填，但可能阻挡老资产录入
4. **标签字典化用哪种方案**：
   - A. 复用 `soc_dicts`，每个 tag key 一个 dict_type（轻量）
   - B. 单独建 `soc_tag_presets` 配置表（更灵活，支持更多属性）
5. **Wazuh 漏洞数据缓存策略**：
   - 内存缓存（1h TTL，进程重启失效）—— 简单
   - DB 缓存表（`soc_wazuh_vuln_cache`，定时刷新）—— 持久化
   - 直接调 Wazuh API（最实时，但慢）—— 取决于 Wazuh 性能
6. **漏洞 Tab 是否要展示补丁状态**（Wazuh 也提供 patched vs unpatched 区分）？
7. **应用清单展示哪些字段**：vendor / architecture / install_path / package_type 都展示还是精简到 name + version？

---

## 📝 版本历史

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-06-02 | 初始版本，基于 2026-06-02 资产详情页代码审阅 | Claude |
| v1.1 | 2026-06-03 | 补充第 4 节"主机应用清单 + 漏洞"（P0），Wazuh agent syscollector + vulnerability-detector 集成方案（3 档位 A/B/C） | Claude |
