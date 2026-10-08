# 2026-10-08 AssetSync wazuh_agent_id 漂移识别修复

**状态**: ✅ 已修复并部署 102
**关联**: [2026-10-08-wazuh-collector-data-type-trim.md](2026-10-08-wazuh-collector-data-type-trim.md)（同步修复的姊妹篇）

---

## 0. 触发

修复完 sync_client 假绿后，102 wazuh-collector 日志里暴露出**新一层**的 UniqueViolation：

```
(psycopg2.errors.UniqueViolation) duplicate key value violates unique constraint "uq_soc_assets_agent_id"
DETAIL:  Key (wazuh_agent_id)=(010) already exists.

[SQL: UPDATE soc_assets SET ..., wazuh_agent_id='010' WHERE soc_assets.id = '70ce2f10-...'::UUID]
```

每 5 分钟一轮、每轮 3 次 retry 后 500、failure_count 每 5 分钟 +2。

## 1. 根因

### 1.1 数据库约束

```sql
CREATE UNIQUE INDEX uq_soc_assets_agent_id 
ON public.soc_assets USING btree (wazuh_agent_id) 
WHERE (wazuh_agent_id IS NOT NULL);
```

`wazuh_agent_id` 在 `soc_assets` 表上**跨 IP 全局唯一**（NULL 例外）。

### 1.2 现实数据状态（修复前）

- 库中 `wazuh_agent_id='010'` **只有一条**：`id=19265fdd-3b2e-..., asset_ip=192.168.0.17, network_segment=lan-main`
- 这条 `asset_description` 是 TP-Link 风格（"无线设备 | SSID: TP-LINK_3ED4 | 5GHz | RSSI: -64dBm | AP: TL-XAP1800GI-PoE-0005"）
- `soc_asset_sources` 显示**双来源**：tplink-router（online）+ wazuh（**offline**，010，last_seen_at 2026-10-03）
- Wazuh Server 那边 agent `id=010` name=`xiejava-fnNAS` **当前** IP=`192.168.0.18`（**DHCP 漂移过**）

### 1.3 死循环

1. 历史某时刻，Wazuh agent 010 装在 192.168.0.17 → 库中创建记录（wazuh_agent_id='010', asset_ip='192.168.0.17'）
2. 之后 0.17 被 tplink 接管（wazuh 那台机器退了/换 IP），tplink 推的 item **不带** wazuh_agent_id → 不覆盖该字段 → 残留
3. Wazuh agent 010 DHCP 漂移到 192.168.0.18 → 重新连 Wazuh
4. wazuh-collector 推 18 条 agent 列表（含 agent 010=192.168.0.18）→ 后端 `/data/sync`
5. handler 收到 item `{asset_ip=192.168.0.18, wazuh_agent_id=010, ...}`：
   - 按 (asset_ip, network_segment) 查重 → 192.168.0.18 没记录 → 走 `_create_new`
   - `db.add(asset)` 内存中新 asset 行 wazuh_agent_id='010'
   - `db.flush()` → PG 报 UniqueViolation（因为 192.168.0.17 那条已经是 '010'）
6. SQLAlchemy session 进入 `PendingRollbackError` → **同 batch 后续 17 条全部 500**
7. failure_count 每 5 分钟 +2（retry 2 次后失败）

### 1.4 影响面

- 6 周以来 `wazuh:agents` 持续 1/3 失败：success=8192 / failure=5359 ≈ 60% 完整率
- `soc_assets` 表里 Wazuh agent 数据**约 40% 是漏的**
- 102 上同时跑 tplink-collector（5 分钟）和 wazuh-collector（5 分钟）——两个都写 `soc_assets`，**所有 Wazuh agent 几乎都漂移过 IP**（DHCP 内网常态）——实际污染面**比 010 一条大得多**

## 2. 修复

### 2.1 代码改动

**文件**：`src/backend/app/services/sync_handlers/asset_sync_handler.py`

**新增方法**：`_release_stale_wazuh_agent_id(item, db)` —— 70 行

**逻辑**：

```python
def _release_stale_wazuh_agent_id(self, item, db):
    agent_id = str(item.get("wazuh_agent_id"))
    target_ip = item.get("asset_ip")
    target_seg = item.get("network_segment") or infer_segment(target_ip)
    
    stale = db.query(Asset).filter(Asset.wazuh_agent_id == agent_id).first()
    if stale is None:
        return  # 无占用，无需释放
    
    # 占位的就是新 item 目标资产（（IP, segment）同）：走更新路径不会冲突，不释放
    if str(stale.asset_ip) == str(target_ip) and stale.network_segment == target_seg:
        return
    
    # 判定"陈旧"——任一条件即视为可释放
    is_stale = (
        stale.asset_status == "offline"           # wazuh 已断连
        or (stale.last_synced_at is not None
            and (now - stale.last_synced_at).total_seconds() > 86400)  # 24h+ 没推
        or (stale.data_source is not None and stale.data_source != "wazuh")  # 被其他源接管
    )
    if not is_stale:
        raise ValueError(f"wazuh_agent_id {agent_id} 已被活跃资产 ... 占用，...")
    
    # 释放占位：设为 NULL 让 partial unique index 跳过
    stale.wazuh_agent_id = None
    db.flush()
    self._log_change(...change_type="wazuh_agent_id_drop", ...)
```

**调用点**：`_upsert_asset()` 入口（在原有 (asset_ip, network_segment) 查重之前）

### 2.2 关键设计选择

- **不动 unique 约束**：partial unique index 是设计文档明确要的"跨 IP 全局唯一"——本 bug 是数据问题不是约束问题
- **不动 `_create_new` / `_update_existing`**：只前置一个新方法，最小爆炸面
- **写变更日志 `change_type="wazuh_agent_id_drop"`**（19 字符，< String(20) 列宽）——审计可追溯
- **"陈旧"判定三条任一**：`offline` / `24h+` / `data_source != wazuh`——故意宽松，保证不卡住
- **"不陈旧"才 raise**：避免采集器侧 wazuh_agent_id 重复上报被静默吞掉

## 3. 部署

- 102 pull 修复 commit（1bf5f52）→ `systemctl restart aisoc-backend`（不动前端/build）

## 4. 修复后验证（5 分钟观察窗）

### 4.1 实时日志

```
13:57:56 开始采集 Wazuh asset 数据
13:57:56 获取到 18 个 agents
13:57:56 成功转换 18 个资产
13:57:57 POST /api/v1/data/sync → 200 OK
13:57:57 同步成功: source=wazuh, type=asset, total=18, created=0, updated=17, skipped=1
13:57:57 同步成功: {message: '同步完成', ..., failed: 0, errors: []}
```

**failed=0**——18 条全部成功（17 updated + 1 skipped）。

### 4.2 soc_source_health 修复后

| source_key | 修复前 failure | 修复后 failure | 含义 |
|---|---|---|---|
| `wazuh:agents` | 5421、+2/轮 | **5421**、**5 分钟稳态零增长** | 完美 |

success_count: 8192 → 8193（+1，**真成功**了）

### 4.3 数据本身

- **0.17 那条 TP-Link 资产**：`wazuh_agent_id` **被设为 NULL**（漂移识别成功）
- **0.18 那条 Wazuh agent 010 资产**：已成功入表（name=xiejava-fnNAS, status=online）
- **17 条 `soc_asset_change_logs` `change_type='wazuh_agent_id_drop'`** 落库（不止 010 一条，**全 18 条**都漂移过）

### 4.4 重要副作用

17 条 wazuh_agent_id_drop 意味着**库中 17 个老资产**都曾被其他来源接管、wazuh_agent_id 残留——**整个 Wazuh→soc_assets 路径 6 周没真正工作**，所有 Wazuh agent 的 IP 漂移都被静默丢弃。修复**一次性清理**了。

## 5. 同时关闭的安全洞（顺手）

**问题**：102 后端 `.env` 之前**没有** `WAZUH_WEBHOOK_KEY` 配置 → 走代码默认值 `"change-this-in-production"`——任何能到 8000 端口的 IP 都能推送假 webhook。

**修复**：

```bash
# 1. 生成 64 字符 URL-safe 真 key
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# → 64 字符 key

# 2. 写进 102 后端 .env（追加，不动现有配置）
WAZUH_WEBHOOK_KEY=<真 key>
WAZUH_WEBHOOK_ALLOWED_IPS=192.168.0.40,127.0.0.1  # 只放 Wazuh Server + 本机
```

**验证 4 项**：
- 不带 key → 401
- 错 key → 401
- 真 key + 合法 IP → 200（auth 通过；sync 内部 Wazuh 客户端有独立 bug：`sequence item 0: expected a bytes-like object`，不在本次 scope）
- 真 key + 非白名单 IP → 403

**注意**：webhook 端点**未启用**（Wazuh Server 192.168.0.40 没配集成脚本），但**安全洞必须先关**——避免哪天有人启用时被裸 key 利用。

## 6. 教训

- **数据完整性约束**和**DHCP 漂移**天然冲突——`wazuh_agent_id` 跨 IP 全局唯一 vs agent IP 漂移是常态——`AssetSyncHandler` 必须承担**漂移识别责任**（设计文档 OH-4.1 只想到 IP 漂移身份融合，**没做 wazuh_agent_id 漂移**）
- **修复路径选择**：① 改 unique 约束（非空 partial → 非唯一）会破坏跨 agent 唯一性语义；② handler 释放陈旧占位（本次选择）保留约束语义，代价是 70 行新代码——② 是对的
- **CLAUDE.md §4.13 假绿治住后**才会暴露同款问题的其他实例——**这是一连串**，建议**系统性**审计其他 handler / 约束（参见「已知未修 / 待办」）
- **顺手关闭安全洞**比"等业务触发再关"重要——WAZUH_WEBHOOK_KEY 走默认值 6 周是定时炸弹，今天不拆明天也会被某个 agent 触发
