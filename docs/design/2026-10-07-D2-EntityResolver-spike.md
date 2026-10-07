# D-2 拍板：EntityResolver 算法优先级（Spike + 实测数据）

> 2026-10-07 · 关闭底座 §10.4 G5/G6/G7 三缺口 · 决策人：主 Agent（用户连续授权"继续"且此前已授权替拍 D-3/D-4/D-5）

## 1. G6 实测摸底（2026-10-07，dev 库 AI-miniSOC-testdb）

| 度量 | 实测 | 结论 |
|---|---|---|
| 资产总数 | 83 | — |
| `asset_ip` 覆盖 | 83/83（100%，重复 0） | **IP 精确锚已全覆盖** |
| `wazuh_agent_id` 覆盖 | 22/83（27%，重复 0） | 精确但覆盖低，作高优先级快路径 |
| `mac_address` 覆盖 | 66/83（80%） | 可作第三优先级 |
| identity_events `src_ip` 反查 | 3987 种，命中资产 8 种（0.2%） | **主要成分是外部攻击 IP——不应锚资产** |
| identity_events `dst_ip` 反查 | 14 种，命中 14 种（100%） | 内网侧事件已 100% 可锚 |

**覆盖率结论（G6 关闭）**：分母取"在册资产"而非"日志 IP 全集"——后者把攻击者公网 IP 计入分母是口径错误。资产侧 IP 锚定 100% ≥ 95% 目标；日志侧按内网端（dst）计已 100%。度量以 `coverage()` API 分段输出，不拍单一数字。

## 2. G5 算法优先级与冲突仲裁（拍板）

**优先级链（确定性，逐级短路）**：

```
1. wazuh_agent_id 精确匹配            （最高：agent 直报，实测唯一）
2. asset_ip 精确匹配                   （实测唯一；含公网/私网）
3. mac_address 精确匹配                （80% 覆盖）
4. src/dst ip 反向索引（soc_identity_events）
   └─ 仅限私有网段 IP 参与反查          （0.2% 命中证明：外部攻击 IP 禁锚资产）
```

**v1 明确不做**：
- hostname/名称模糊匹配——相似度阈值无标注语料标定，做了就是伪造精度。留 v2 待有标注数据。
- `register_alias()` 动态注册——返回 not_supported（诚实），因 G7 决策不建表。

**冲突仲裁**：
- 跨级：高优先级胜出，低级结果仅记录。
- 同级多命中（如未来 IP 重复）：返回 `asset_id=None` + `conflicts=[...]`，**不猜**。实测当前 dup=0，此路径是防回归护栏非常态。

## 3. G7 表迁移（拍板）

**v1 不建 `soc_entity_alias`**（遵底座建议）：现有 soc_assets 字段已满足优先级链；避免 alembic 迁移摩擦。若未来 alias 需求（hostname 模糊、多云多 account id）出现再建。

## 4. 落地

- `app/services/entity_resolver.py`：`resolve(alias, alias_type=None)` / `coverage()`
- API：GET `/assets/entity-resolver/resolve` + `/coverage`
- 测试：`tests/test_entity_resolver.py`

## 5. 风险与诚实边界

- srcip 反查限定私有段用的是网段判定（10/172.16-31/192.168），公网资产若出现在 srcip 则不在反查范围（v1 接受，公网资产本就用 asset_ip 精确锚在链 2 命中）。
- 覆盖率数字随资产增长漂移，coverage() 为快照非承诺。
