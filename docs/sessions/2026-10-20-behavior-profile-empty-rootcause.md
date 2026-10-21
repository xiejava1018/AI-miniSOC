# 行为画像全空：根因定位（2026-10-20）

## 现象
`/browsing/profile` 页面：
- 「人设群体分布」空
- 「全网兴趣构成」空（`global_cat_share: {}`）
- 每个画像主体的「画像标签」空（`tags: []`）

## 观测到的 API 返回（生产 192.168.0.102）

`GET /api/v1/behavior-profile/overview?days=7`：
```json
{"days":7,"subject_total":77,
 "confidence_dist":{"high":0,"mid":0,"low":77},
 "tag_distribution":[],
 "global_by_hour":[0]*24,
 "global_cat_share":{},
 "global_top_domains":[],
 "data_freshness":{"latest_date":"2026-10-19","snapshot_days":6}}
```

`GET /api/v1/behavior-profile/list` → 每条 `total:0, tags:[], confidence:0`。

**77 个主体全部是"空壳"**：`status` 走的是 `ok`（不是 `gap`），但 `total=0`。
→ `aggregate_day([])` 的输出就是全 0，**所有图表、标签、兴趣构成全部由 `total` 派生，所以一起为空**。
这是典型的 §4.1 假绿：`code=200` + 数据行存在，但内容全零。

## 根因（两处独立缺陷，都在上游采集，不是前端 bug）

### 缺陷 A：日志格式正则不匹配 —— 主因
`src/backend/app/services/behavior_profile/loki_source.py:27`
```python
RE_DOM = re.compile(r"网址:([^\s:：]+)")   # OpenWrt 上网行为日志格式
```
实际 Loki 里的日志是 **iStoreOS `behavior_ctl`** 格式：
```
<134>Oct 20 14:00:37 iStoreOS behavior_ctl: ... behavior:a:IPGROUP_ANY a:192.168.0.100
      apptype:Web HTTPS dst:docker.1ms.run rule:GeoIP(cn) policy:DIRECT
```
域名载体是 **`dst:`**，不是 `网址:`。

实测（2026-10-20 单日，287 行原始日志）：
| 正则 | 抽出 events 数 |
|---|---|
| `网址:` （现有代码） | **0** |
| `dst:` | **287**（178 个 distinct 域名）|

`fetch_day_events()` 第 93 行 `if not m: continue` 把 287 行全丢掉 → `aggregate_day([])` → 全 0。

### 缺陷 B：`ip` label 语义搞反 —— 次因
`loki_source.py:47` 用 `{ip="<客户端IP>"}` 做 label 选择。

实测 Loki labels 只有 `exporter=OTLP, ip=192.168.0.100, service_name=unknown_service`。
`ip=192.168.0.100` 是**路由器/采集源自身的 IP**，不是客户端 IP。
客户端 IP 藏在 body 的 `a:` 字段里。

而 `snapshot_job.py:discover_targets()` 从 `soc_assets` 取了 **77 个内网资产 IP**，
拿它们去查 `{ip="192.168.0.x"}` → 全部 0 命中。

> 注：当前 Loki 里只采集到 1 个 IP，且 `a:` 字段值也全是 `192.168.0.100`
> （路由器 IPGROUP_ANY 没展开到真实客户端），所以即使修好 A，
> 主体维度仍只有 1 个（路由器自己）。需要先修路由器的 `behavior_ctl` 配置让它输出真实客户端 IP。

## 追问：为什么 Loki 里只有 192.168.0.100 一个 IP？（2026-10-20 追加调查）

### 采集链路真貌（192.168.0.30 = `xiejavahost`）

不是 Promtail，是 **Grafana Alloy**（systemd `alloy.service`，无 docker）：

```
otelcol.receiver.syslog.local  (UDP :514)
   └─> otelcol.exporter.loki.local
        └─> loki.process.extract_ip  ──> loki.write.local
loki.source.file.openresty_files ──> loki.process.add_server_name_label ──> loki.write.local
```
Alloy 组件总数只有 **7 个**，`/api/v0/web/components` 全 healthy。

### 答案：Alloy 的 syslog receiver 只收到 1 台机器的 syslog，且把"发送方 IP"当成了 label

1. **`ip` label = syslog 发送方 IP**（`loki.process.extract_ip` 从 RFC3164 header 提的 `SRC IP`），
   不是被监控主机的业务 IP。所以 label 只有一个值 `192.168.0.100`
   = 唯一在往 `192.168.0.30:514` 发 syslog 的机器（大概率就是那台 iStoreOS 路由器本身）。
   它的客户端 IP 藏在 body 的 `a:` 字段里 —— **Alloy 层面就没有把它提升为 label**。

2. **没有任何其他数据源**。7 个组件里只有 openresty access log（文件采集，且 `.30` 上 80 端口是 openresty）
   和 syslog 两路。**内网 77 台资产/客户端的上网行为日志根本没进过 Alloy**。

3. **syslog 解析在持续报错**（近 2h 59 次，journald 甚至 `Suppressed 26074 messages`）：
   ```
   otelcol.receiver.syslog.local operator_type=syslog_parser
   error="expecting a version value in the range 1-999 [col 5]"
   ```
   → **RFC5424 解析器在解 RFC3164 格式**。iStoreOS 发的是 RFC3164（`<134>Oct 20 14:00:37 ...`），
   Alloy 配成了 5424。**大量日志被直接丢弃**，只有偶然符合 5424 格式的能进来
   —— 这解释了为什么 `service_name=unknown_service`、数据量极小且断续。

4. **数据量本来就极少**：近 14 天总 5000 行（已被 limit 截断），
   每天只有 3~48 行/小时，且集中在整点/半点（ntp 时间同步 + 偶发 docker 拉取）。
   对比内网真实上网行为应是**每小时数万行**。

### 结论
「只有 192.168.0.100」= **只有一台机器在发 syslog，且发的是被错误解析器的部分丢弃的日志**。
不是 Loki 存储/label 配置问题，是**采集入口就没接全 + 解析格式配错**。

## 追问 2：上机确认“有没有其他 SYSLOG 送过来”（2026-10-20 第二次追查）

### 重要修正：之前说“只有一个 IP”不准确，实际是 **2 个**，且只有一个还在发

| stream `ip` label | 行数 | 时间范围 | 状态 |
|---|---|---|---|
| `192.168.0.100` | 2759 | 10-14 19:23 → **10-20 21:08**（连续 7 天） | ✅ 活着 |
| `192.168.0.8` | 2241 | **只有 10-13 22:30 → 23:21**（51 分钟） | ❌ 已停 7 天 |

（用 `{ip=~".+"}` 查才看得到两个 stream；`label/ip/values` 那个接口在7 天保留窗口外
已经只剩 `.100` 了 —— **label values 接口受 retention 影响，不能用它判断“有几台在发”**。）

### `.30` 上 UDP :514 的归属：Alloy，没有端口冲突

- `/proc/net/udp6` 里 `:0202`(=514) inode=14514 → `/usr/local/bin/alloy`（PID 843）
- `rsyslog.service` 虽然 running，但 `/etc/rsyslog.conf` 里
  `module(load="imudp")` 和 `input(type="imudp" port="514")` **全是注释掉的**
  → rsyslog 只收本机 imuxsock，**不抢 514**
- Alloy `ActiveEnterTimestamp = 2026-10-15 04:00:17`

### 假警报澄清：`/var/log/syslog` 里那 84 个 IP 全是假的

第一次 grep `192.168.0.100` 在 `/var/log/syslog` 命中 23236 行，看着像“海量主机在送”，
实际逐行看**全部是 Loki 自己打的查询日志**：
```
loki[727]: ... msg="flushing stream" labels="{exporter=\"OTLP\", ip=\"192.168.0.100\", ...}"
loki[727]: ... msg="executing query" query="{ip=\"192.168.0.100\"}"
```
我们自己的 `behavior-profile` 快照任务每轮都查 `{ip="192.168.0.100"}`，Loki 把查询和
stream flush 写进 syslog，又被我的 grep 当成了“来源 IP”。

验证：找真正的远端 syslog 报文格式（RFC5424 header）→ **0 行**；
排除 `loki[727]` 后含 `.100` 的行 → **0 行**。

**→ 全网只有 2 台机器在往 .30:514 发 syslog（.100 和 .8），其中 .8 已停。**
`/var/log/syslog` 400MB 里有 99.9% 是本机 systemd + Loki 自身噪音。

### 真正的病根：syslog 报文 99.99% 被丢弃

```
journalctl -u alloy --since "-7d" | grep -c "Failed to process entry"  →  8978
journalctl -u alloy --since "-7d" | grep -c "Failed to write entry"     →  8978
journalctl -u alloy --since "-7d" | grep -v "level=error"              →  只有 reporting Alloy stats / usage report
```
**近 7 天 8978 次解析失败，0 次成功痕迹**（非 error 日志只有 Alloy 自己的统计上报）。
error 一一对应（parse 失败 → write 失败），说明**进来的报文 99.99% 被 rfc5424 解析器拒了**，
只剩极少数恰好符合 5424 的进来 —— 所以：

- `.100` 每天只有 200~350 行（真实应该数万行）
- `.8` 只在 10-13 那个 51 分钟窗口有 2241 行，之后彻底静默
  （**很可能就是当时 .8 发了 RFC5424 或改过配置，之后改回 3164 就全被丢了**）
- `service_name=unknown_service`（解析失败 → 拿不到 hostname）

## 完整因果链

```
iStoreOS 路由器发 RFC3164 syslog（<134>Oct 20 ...）
   └─> .30:514/udp (Alloy otelcol.receiver.syslog)
        └─> 解析器配成 rfc5424 → 8978/8978 失败  ← 病根
             └─> 偶尔漏进来的 → loki.process.extract_ip 提"发送方IP"当 label
                  └─> Loki 只得 2 个 stream，且 .8 已断
                       └─> miniSOC behavior_profile 查 {ip="客户端IP"} 必然 0 命中
                            └─> 77 个空壳画像 total=0
```

## 待你确认（需 sudo）
1. `.100` 和 `.8` 分别是什么设备？（.8 的日志里出现 `smbcloud-remote.tplinkcloud.com.cn`、`main.vscode-cdn.net`、`gateway.icloud.com.cn`，像台 Windows/Mac 开发机）
2. 修 `syslog_format` 后确认 `.8` 是否恢复；
3. 是否还有**其他设备配了 syslog 转发到 .30 但没在发**？（目前只能看到实际到达的，无法看到配置）

## 附带发现：CLAUDE.md §0/§2.1 的"Loki 不可达"结论已过期
```
http://192.168.0.30:3100/ready → 200 ready
```
Loki **一直是通的**。之前判定"不可达"可能是从 Mac 测 `192.168.0.102:3100`（Connection refused）
或别的瞬时故障。**§0 表格和 §4.1 里"当前不可达 / 持续降级"的描述需要更正** ——
降级的真实原因是缺陷 A/B，不是网络。

## Loki 数据实际覆盖
- label 值：仅 `192.168.0.100` 一个
- 2026-10-20 单日 287 行；近 3 天 1137 行
- 全量历史只有 3 天（2026-03-06/07/08，各 ~5000 行上限截断）→ 历史段也被 limit 截断

## 2026-10-21 PTR 过滤已实施并上线

**两层防御**：

1. **主防线（入库前丢弃）** `loki_source.py`
   ```python
   RE_PTR_ARPA = re.compile(r"\.(?:in-addr\.arpa|ip6\.arpa)\.?$")
   def is_ptr_lookup(domain: str) -> bool: ...
   # fetch_day_events 内
   if is_ptr_lookup(domain):
       ptr_dropped += 1
       continue
   ```
   同时 `logger.info("过滤 DNS 反查噪声 ip=%s day=%s dropped=%d kept=%d")`，
   让过滤量可见（避免“静默丢弃”变成新假绿）。

2. **二次防御（classifier）** `classifier.py`
   ```python
   if is_ptr_lookup(d):
       return "系统背景", CATEGORIES["系统背景"]
   ```
   归入“系统背景”而非“其他”——它确实是机器行为而非人的兴趣。
   挡住历史脏数据与`browsing_detection` 等其他写入方。
   注意：`classifier` 现在 `import loki_source.is_ptr_lookup`，
   反向不import（无循环依赖，已验证）。

**实测效果**（回退水位强制重算2026-10-21）：

| 指标 | 过滤前 | 过滤后 |
|---|---|---|
| 残留 in-addr.arpa 域名行 | — | **0** |
| global_cat_share「其他」 | 45.4% | **27.2%** |
| global_cat_share「系统背景」 | 21.8% | **29.2%** |
| global_cat_share「开发技术」 | 20.1% | **26.9%** |
| global_cat_share「工作办公」 | 5.2% | **6.9%** |
| 标签「码农」 | 9 | **10** |
| 标签新增 | — | **AI 重度用户** |

`.42` 主体：domains 下钻从 50 个（98% 是 PTR）降到 **1 个**（`version.goauthentik.io`），
`cat_share` 依旧 `{"其他": 100.0}` 是因为它**真的**只有这一个域名、且词典未收录——
这是真实情况而非噪声。

**新踩坑：`run_snapshot` 幂等保护会挡住重跑**。
`watermark.last_completed_date >= target_date` 时直接返回 `up_to_date`，
所以“改了聚合格式想重算同一天”必须先回退水位：
```python
wm.last_completed_date = DAY - dt.timedelta(days=1); db.commit()
run_snapshot(db, target_date=DAY)
```

**测试**：`src/backend/tests/test_behavior_profile_ptr_filter.py`（24 passed）
覆盖 `is_ptr_lookup` 正反用例、classifier 二次防御、
`fetch_day_events` 丢弃 PTR（monkeypatch `pull_window`）、全天 PTR → 空列表、
以及裸 IP 仍走“IP 直连”不被抢走。

> `test_behavior_profile_api.py::test_profile_rejects_non_admin` 失败是**预先存在**的
> （stash 掉本次改动后同样失败），与本改动无关。

## 2026-10-21 手动回补结果：页面已有数据 ✅

**做法**：写了运维脚本 `scripts/run_behavior_snapshot.py`（调`run_snapshot(db, target_date=...)`），
在生产服务器上跑 `venv/bin/python run_behavior_snapshot_tmp.py 2026-10-21`。
```
行为画像快照完成: {'targets': 72, 'days': 1, 'snapshots': 72, 'gaps': 0, 'errors': 0,
                   'status': 'ok', 'last_completed': '2026-10-21'}
```
> 注：脚本调的是快照主流程（写库），**不是** `POST /behavior-profile/{ip}/refresh`
> （那个只返回 realtime JSON，不落库）。

**回补后 API 实测**：
```
subject_total: 77    confidence_dist: {high:5, mid:3, low:69}
traffic_type: {human:74, machine:2, mixed:1}
tag_distribution: 夜猫子18 / 间歇上线型18 / 作息极规律15 / 早起鸟10 / 码农9 / 学生党3 / AI尝鲜者2 ...
global_cat_share: 其他45.4% 系统背景21.8% 开发技术20.1% 工作办公5.2% AI工具2.6% ...
global_top_domains: stun-heyuan-v6.easytier.cn 629 / open.feishu.cn 482 / www.workbuddy.cn 288 ...
global_by_hour: 0~9点均有数据（此前全 0）
list: 77 个主体中 18 个 total>0，全部 tags 非空
```

TOP 主体：
| IP | hostname | total | conf | tags |
|---|---|---|---|---|
| .8 | xiejavadeMini | 3162 | 100 | 夜猫子/早起鸟/间歇上线型 |
| .42 | pve-LXC-ubuntu02 | 1448 | 100 | 夜猫子/早起鸟/间歇上线型 |
| .30 | fnos-vm-ubuntu01 | 1365 | 100 | 同上 |
| .17 | xiejava-fnNAS | 1295 | 100 | 同上 |
| .45 | pve-kail-linux | 961 | 98 | 夜猫子/间歇上线型/作息极规律 |
| .100 | iStoreOS路由器 | 332 | 35 | 同上 |

**→ `a:IPGROUP_ANY` 的担忧解除**：这些 IP 的 hostname 都是真实终端/服务器
（pve-LXC、fnos-vm、ThinkPad 等），不是网关。`ip` label 就是真实客户端 IP。

**但发现严重数据质量问题：`in-addr.arpa` PTR 反查把分类彻底污染**：
```
192.168.0.42: cat_share = {"其他": 100.0}
                domains 总数 50，其中 in-addr.arpa = 49（98%）
192.168.0.8 : cat_share = {"其他": 47.0, ...}   ← 相对好一些
```
`192.168.0.42` 的 TOP 域名里 18visits 的 PTR 反查域名排到第2~5 位：
`1.0.168.192.in-addr.arpa` / `173.0.168.192.in-addr.arpa` / `109.0.168.192.in-addr.arpa` ...

→ **必修**：在 `loki_source.fetch_day_events` 或 `classifier` 过滤
`*.in-addr.arpa` / `*.ip6.arpa`（这是路由器把 DNS 反查失败也记成上网行为）。
过滤后需重跑当日快照才能看到干净的 `cat_share` / TOP 域名。

## 2026-10-21 复验：Alloy 侧已修好，根因变成纯时间差

你在我上一轮回答后修了 Alloy 配置（syslog_format）。对比验证：

| 项 | 10-20（修前） | 10-21（修后） |
|---|---|---|
| Loki stream 数 | 2（.100/.8，且 .8 已断） | **17，全部活跃** |
| 日志格式 | iStoreOS `dst:` | **TP-Link `网址:`**（`TL-R479GPE-AC behavior_ctl`） |
| `RE_DOM=网址:` 命中 | **0/5000** | **4955/5000** |
| `{ip="X"}` 能否命中 | 只有 .100 | 17 个全部命中 |
| Alloy 解析失败（7d） | 8978 | 17595（含新增设备，仍在报错） |

→ **缺陷 A（正则）和 alloy 格式问题都已解决**。TP-Link 路由器的
`网址:` 格式与现有 `RE_DOM` 完全匹配。

### 现在的唯一阻塞：快照任务按整天聚合，尚未跑到有数据的那天

```
10-21 02:00:22  行为画像快照完成: {'targets': 72, 'days': 1, 'snapshots': 72,
                                 'gaps': 0, 'errors': 0, 'last_completed': '2026-10-20'}
Loki 每日行数（近10天）:  {'10-21': 5000}      ← 只有 10-21 有数据
```

时间线：
1. 每天 02:00 跑一次，聚合**昨天一整天**
2. 10-21 02:00 那轮拉的是 **10-20 全天** → Loki 里10-20 根本没数据 → 72 个快照全 `total=0`
3. Loki 从 **10-21 当天**才开始有数据（5000 行 / 17 streams）
4. 拉 **10-21 全天**要等 **10-22 02:00** 那轮

**→ 代码侧无需再改。等 10-22 02:00 自动跑完，页面就会有数据。**

立即验证（不等明天）：
```bash
# 手动触发拉 10-21（POST /behavior-profile/{ip}/refresh 或直接等明早）
curl -s "http://192.168.0.30:3100/loki/api/v1/query_range?query={ip=\"192.168.0.42\"}&limit=5" | jq '.data.result[0].values[:3]'
```

### ⚠️ 仍然存在的两个真问题（不阻塞显示，但会导致画像不准）

1. **`a:` 字段全是 `IPGROUP_ANY`**（5000/5000）
   ```
   behavior:a:IPGROUP_ANY a:192.168.0.42 网址:version.goauthentik.io
   ```
   `a:`（客户端 IP）没被路由器展开，所有流量的 `a:` 都等于它自己的 IP。
   **所以每个 IP 的画像 = 该 IP 自己的上网行为，而不是它代理的客户端的行为。**
   如果这些 IP 是网关/旁路机，画像维度就全错了。

2. **in-addr.arpa 反查污染域名库**（`.42` 的 934 行里大量）
   ```
   网址:238.0.168.192.in-addr.arpa   ← PTR 反查，路由器把"连接失败"也记成行为
   网址:236.0.168.192.in-addr.arpa
   ```
   `.42` 的 distinct domain 83 个里相当一部分是 `*.in-addr.arpa`，
   会把"其他"分类撑大、污染 TOP 域名。建议 `classifier`/`loki_source` 过滤掉
   `in-addr.arpa` / `ip6.arpa`。

3. **Alloy 仍在报错**（7d 17595 次）：修好格式后又冒出新的解析失败，
   可能是多设备混合格式（TP-Link 3164 + 其他）。需再查一次具体报文。

## 修复清单

### 采集侧（新增，最高优先 — 前面 3 项做了也不出数据）
3. **修 Alloy syslog 解析格式**（`.30` 的 `/etc/alloy/config.alloy`）：
   `otelcol.receiver.syslog` 加 `syslog_format = "rfc3164"`（当前默认 rfc5424 在解 3164 报文）。
   ⚠️ 该文件需 sudo（`xiejava` 无免密 sudo），要本人上机改。
   改完：`sudo systemctl restart alloy` + `journalctl -u alloy -f` 看 error 消失。
   **验收标准：`journalctl -u alloy --since -10m | grep -c "Failed to process"` 应降到 0。**

4. **让客户端 IP 成为 label**（否则行为画像无法按主体聚合）：
   Alloy 加 `loki.process` 规则，从 body 用 `a:` 提客户端 IP 提升为 label；
   或在 iStoreOS 侧改 `behavior_ctl` 输出格式直接带真实客户端 IP。

5. **接全采集入口**：内网 77 台资产的上网行为日志目前完全没进 Alloy（组件只有 openresty 文件 + 单路 syslog）。

### 迷你 SOC 侧
6. **`loki_source.py` 支持 iStoreOS `dst:` 格式**（保留 `网址:` 兼容旧格式）
   ```python
   RE_DOM_DST = re.compile(r"\bdst:(\S+)")
   ```
   `fetch_day_events` 先试 `dst:` 再回落 `网址:`；两者都无则跳过。
   ⚠️ 注意 `dst:` 也可能是裸 IP（`202.118.1.81`），需要决定是否过滤/单列。

7. **确认 `ip` label 语义**并改查询方式：当前 `ip` 是 syslog 发送方，
   不是客户端 —— 需按修复 4 的结果决定用哪个 label。

8. **补一条"空壳画像"告警/可见化**（防再次假绿）
   现状 `total=0` 但 `status=ok`，前端照常渲染空图表。
   建议：`total=0` 且连续 N 日 → 前端显式提示"该主体无采集数据"，
   或 `status` 增 `no_data` 态。

### 文档
9. 更正 CLAUDE.md §0 / §2.1 关于 Loki 不可达的结论。
10. 归档到 `docs/sessions/INDEX.md`。

## 复现/验证脚本要点
```python
# 直接验证正则缺陷（无需后端）
RE_DOM  = re.compile(r"网址:([^\s:：]+)")
RE_DST  = re.compile(r"\bdst:(\S+)")
# 对 2026-10-20 拉 287 行：RE_DOM 0 命中，RE_DST 287 命中
```