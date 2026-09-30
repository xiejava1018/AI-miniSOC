#!/usr/bin/env python3
"""行为分析模块博文配图：生成 4 张 draw.io 源文件（.drawio XML）。

导出命令（drawio desktop CLI）：
  drawio --export --format png --scale 2 --output ../images/behavior-arch.png behavior-arch.drawio
风格与 docs/blog/images/gen_diagrams.py 调色板保持一致（Tailwind 系）。
"""
import os
from xml.sax.saxutils import escape


def xesc(s: str) -> str:
    """转义 XML：含双引号（属性值内使用）。"""
    return escape(s, {'"': "&quot;"})


DIR = os.path.dirname(os.path.abspath(__file__))

# ── 调色板（与既有 gen_diagrams.py 一致）─────────────────
INK, SUB = "#0f172a", "#64748b"
BLUE, BLUE_BG, BLUE_ST = "#2563eb", "#eff6ff", "#93c5fd"
INDIGO_BG, INDIGO_ST = "#eef2ff", "#a5b4fc"
TEAL_BG, TEAL_ST = "#f0fdfa", "#5eead4"
AMBER_BG, AMBER_ST = "#fffbeb", "#fcd34d"
RED_BG, RED_ST = "#fee2e2", "#fca5a5"
GREEN_BG, GREEN_ST = "#ecfdf5", "#6ee7b7"
PURPLE_BG, PURPLE_ST = "#ede9fe", "#c4b5fd"
GRAY_BG, GRAY_ST = "#f8fafc", "#cbd5e1"
ORANGE_BG, ORANGE_ST = "#fff7ed", "#fdba74"
PINK_BG, PINK_ST = "#fdf2f8", "#f9a8d4"
WHITE = "#ffffff"


class Doc:
    def __init__(self, name, w, h, title, subtitle):
        self.name, self.w, self.h = name, w, h
        self.cells = []
        self.box("t", 32, 20, w - 64, 34, title, "none", "none",
                 font_size=22, bold=True, align="left")
        self.box("st", 32, 54, w - 64, 24, subtitle, "none", "none",
                 font_size=13, font_color=SUB, align="left")

    def _style(self, fill, stroke, font_size, bold, font_color, dashed,
               align, valign):
        s = (f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};"
             f"strokeColor={stroke};strokeWidth=1.5;"
             f"fontFamily=PingFang SC;"
             f"fontSize={font_size};fontColor={font_color};"
             f"align={align};verticalAlign={valign};")
        if bold:
            s += "fontStyle=1;"
        if dashed:
            s += "dashed=1;"
        return s

    def box(self, cid, x, y, w, h, label, fill=WHITE, stroke=GRAY_ST,
            font_size=13, bold=False, font_color=INK, dashed=False,
            align="center", valign="middle", spacing=6):
        self.cells.append(
            f'<mxCell id="{cid}" value="{xesc(label)}" style="{self._style(fill, stroke, font_size, bold, font_color, dashed, align, valign)}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def edge(self, cid, src, dst, label="", color=BLUE, dashed=False,
             exit_dir=None, entry_dir=None, font_size=11.5, font_color=SUB,
             rounded=True, exit_x=None, entry_x=None):
        anchors = ""
        if exit_dir:
            ex = {"down": (0.5, 1), "up": (0.5, 0), "right": (1, 0.5), "left": (0, 0.5)}[exit_dir]
            ex_x = exit_x if exit_x is not None else ex[0]
            anchors += f'exitX={ex_x};exitY={ex[1]};exitDx=0;exitDy=0;'
        if entry_dir:
            en = {"down": (0.5, 1), "up": (0.5, 0), "right": (1, 0.5), "left": (0, 0.5)}[entry_dir]
            en_x = entry_x if entry_x is not None else en[0]
            anchors += f'entryX={en_x};entryY={en[1]};entryDx=0;entryDy=0;'
        style = (f"edgeStyle=orthogonalEdgeStyle;html=1;rounded={1 if rounded else 0};"
                 f"strokeColor={color};strokeWidth=2;{anchors}"
                 f"fontFamily=PingFang SC;"
                 f"fontSize={font_size};fontColor={font_color};labelBackgroundColor=#ffffff;")
        if dashed:
            style += "dashed=1;"
        lbl = xesc(label)
        self.cells.append(
            f'<mxCell id="{cid}" value="{lbl}" style="{style}" edge="1" parent="1" '
            f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>')

    def save(self):
        xml = (f'<mxfile host="app.diagrams.net" version="24.7.7">'
               f'<diagram id="{self.name}" name="{self.name}">'
               f'<mxGraphModel dx="1200" dy="800" grid="0" gridSize="10" guides="1" '
               f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
               f'pageWidth="{self.w}" pageHeight="{self.h}">'
               f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
               + "".join(self.cells) +
               "</root></mxGraphModel></diagram></mxfile>")
        path = os.path.join(DIR, f"{self.name}.drawio")
        with open(path, "w", encoding="utf-8") as f:
            f.write(xml)
        print("wrote", path)


# ══════════════════════════════════════════════════════════
# 图 1：行为分析模块总体架构（数据自下而上流动）
# ══════════════════════════════════════════════════════════
def diagram_arch():
    d = Doc("behavior-arch", 1280, 1000,
            "AI-miniSOC 行为分析模块 · 总体架构",
            "数据自下而上：路由器日志 → 采集解析 → 双引擎（实时检测 + 每日画像）→ 业务库 → 前端消费；身份管道补上「IP → 人」的桥")

    # ── 消费层（最上） ──
    d.box("ui", 40, 96, 1200, 64, "", PINK_BG, PINK_ST)
    d.box("ui_t", 56, 102, 260, 20, "消费层 · 前端「行为分析」菜单", "none", "none",
          font_size=13, bold=True, font_color=SUB, align="left")
    d.box("n_ui", 320, 104, 900, 48,
          "异常事件 · 行为统计 · 行为日志 · 黑名单 · 规则配置 · 行为基线 · 行为画像 L1 群体概览 / L2 单 IP 详情（身份/行为/风险/关系/异常） · AI 研判 · MCP 工具",
          WHITE, PINK_ST, font_size=12)

    # ── 存储层 ──
    d.box("db", 40, 186, 1200, 96, "", AMBER_BG, AMBER_ST)
    d.box("db_t", 56, 194, 320, 20, "PostgreSQL（SOC 业务库）", "none", "none",
          font_size=13, bold=True, font_color=SUB, align="left")
    d.box("n_t1", 60, 220, 196, 48, "soc_browsing_events<br>异常事件（含 rule_hits）", WHITE, AMBER_ST, font_size=11.5)
    d.box("n_t2", 268, 220, 196, 48, "soc_browsing_baseline<br>IP×域名 7 天基线", WHITE, AMBER_ST, font_size=11.5)
    d.box("n_t3", 476, 220, 196, 48, "soc_browsing_blacklist<br>黑名单 + 威胁情报", WHITE, AMBER_ST, font_size=11.5)
    d.box("n_t4", 684, 220, 216, 48, "soc_behavior_profiles<br>画像快照（7 天滚动标签）", WHITE, AMBER_ST, font_size=11.5)
    d.box("n_t5", 912, 220, 196, 48, "soc_identity_events<br>/ bindings 身份绑定", WHITE, AMBER_ST, font_size=11.5)
    d.edge("e_ui1", "n_t1", "n_ui", "REST /api/v1/browsing", "#db2777", exit_dir="up", entry_dir="down", entry_x=0.3)
    d.edge("e_ui2", "n_t4", "n_ui", "REST /api/v1/behavior-profile", "#db2777", exit_dir="up", entry_dir="down", entry_x=0.7)

    # ── 双引擎层 ──
    # 左：检测引擎
    d.box("eng_l", 40, 306, 588, 336, "", BLUE_BG, BLUE_ST)
    d.box("eng_lt", 56, 316, 540, 44,
          "<b>实时检测引擎 · browsing_detection</b><br>BrowsingDetectorScheduler（asyncio · 每 5 分钟一轮）",
          "none", "none", font_size=14, bold=False, align="left")
    el1 = d.box("n_rules", 60, 368, 268, 180,
                "<b>RuleEngine 六类规则</b><hr>"
                "R1 恶意域名命中 · 100<br>R2 突发高频访问 · 40<br>R3 基线偏离 · 20<br>"
                "R4 隧道/穿透工具 · 35<br>R5 凌晨活跃 · 15（IP 级）<br>R6 可疑域名特征 · 15",
                WHITE, BLUE_ST, font_size=12.5, align="left", valign="top", spacing=10)
    el2 = d.box("n_score", 348, 368, 268, 84,
                "<b>加权打分与抑制</b><br>score = Σ(命中权重) ≥ 50 触发<br>同 (ip,domain) 30 分钟抑制期",
                WHITE, BLUE_ST, font_size=12.5)
    el3 = d.box("n_eventsvc", 348, 466, 268, 82,
                "<b>EventService 事件闭环</b><br>落 soc_browsing_events<br>severity ≥ high → 升级事件 + WS 通知",
                WHITE, BLUE_ST, font_size=12.5)
    d.edge("e_r3", el2, el1, "", BLUE, exit_dir="left", entry_dir="right")
    d.edge("e_r4", el3, el2, "≥ 阈值", BLUE, exit_dir="up", entry_dir="down")
    d.edge("e_db1", el3, "n_t1", "", "#94a3b8", exit_dir="down", entry_dir="up")

    # 右：画像引擎
    d.box("eng_r", 652, 306, 588, 336, "", PURPLE_BG, PURPLE_ST)
    d.box("eng_rt", 668, 316, 540, 44,
          "<b>行为画像引擎 · behavior_profile</b><br>BehaviorProfileSnapshotJob（每日 02:00 · 水位回溯补缺口）",
          "none", "none", font_size=14, bold=False, align="left")
    er1 = d.box("n_agg", 672, 368, 268, 180,
                "<b>聚合与画像计算</b><hr>"
                "aggregator · 24h 曲线 / 7 时段 / 星期热力<br>"
                "classifier · 14 类兴趣 × ACT/SYS/AD 三层<br>"
                "tagger · 17 条标签规则（夜猫子/码农/下载机…）<br>"
                "traffic_type · 人 / 机器 / 混合判定<br>"
                "confidence · 数据量 + 截断惩罚",
                WHITE, PURPLE_ST, font_size=12, align="left", valign="top", spacing=10)
    er2 = d.box("n_snap", 960, 368, 268, 84,
                "<b>快照落库（幂等 upsert）</b><br>soc_behavior_profiles<br>soc_behavior_domains（TOP 200）",
                WHITE, PURPLE_ST, font_size=12.5)
    er3 = d.box("n_rolling", 960, 466, 268, 82,
                "<b>滚动窗口口径</b><br>分布=当日 · 标签/兴趣=近 7 天<br>gap 占位防「假绿」· 180 天留存",
                WHITE, PURPLE_ST, font_size=12.5)
    d.edge("e_p2", er2, er1, "", "#7c3aed", exit_dir="left", entry_dir="right")
    d.edge("e_p3", er3, er2, "", "#7c3aed", exit_dir="up", entry_dir="down")
    d.edge("e_db2", er2, "n_t4", "", "#94a3b8", exit_dir="down", entry_dir="up")

    # ── 采集解析层 ──
    d.box("col", 40, 670, 1200, 118, "", TEAL_BG, TEAL_ST)
    d.box("col_t", 56, 678, 400, 20, "采集与解析层（后端 lifespan 后台任务）", "none", "none",
          font_size=13, bold=True, font_color=SUB, align="left")
    p1 = d.box("n_lokiclient", 72, 706, 276, 68,
               "<b>LokiClient</b><br>5 分钟轮询 · 分页拉取<br>硬上限 50 万条防静默截断",
               WHITE, TEAL_ST)
    p2 = d.box("n_parser", 400, 706, 276, 68,
               "<b>LogParser</b><br>正则提取 ip / domain / apptype<br>秒级去重 · 内外网分离",
               WHITE, TEAL_ST)
    p3 = d.box("n_identity", 728, 706, 480, 68,
               "<b>身份管道 identity.py（Phase 0）</b><br>OpenSearch 每日增量抽取 full_log 用户名<br>→ soc_identity_events / bindings（账号 ⇄ 设备双向绑定）",
               WHITE, TEAL_ST)
    d.edge("e_l2", p2, p1, "", BLUE, exit_dir="left", entry_dir="right")
    d.edge("e_eng1", p1, el1, "窗口记录", BLUE, exit_dir="up", entry_dir="down", entry_x=0.5)
    d.edge("e_eng2", p1, er1, "按日拉取", "#7c3aed", exit_dir="up", entry_dir="down", entry_x=0.85)
    d.edge("e_db3", p3, "n_t5", "", "#94a3b8", exit_dir="up", entry_dir="down")

    # ── 数据源层（最下） ──
    d.box("src", 40, 816, 1200, 128, "", GRAY_BG, GRAY_ST)
    d.box("src_t", 56, 824, 300, 20, "数据源层", "none", "none",
          font_size=13, bold=True, font_color=SUB, align="left")
    r1 = d.box("n_router", 72, 852, 280, 76,
               "<b>TP-Link 路由器 TL-R479GP-AC</b><br>上网行为日志（访问网址 / 使用应用）<br>≈ 20 万条 / 天 · OTLP 推送",
               WHITE, BLUE_ST)
    r2 = d.box("n_loki", 424, 852, 280, 76,
               "<b>Loki 日志聚合</b><br>{exporter=\"OTLP\"} · 仅保留 7 天<br>标签含 54 个内网 IP",
               WHITE, BLUE_ST)
    r3 = d.box("n_os", 776, 852, 432, 76,
               "<b>Wazuh → OpenSearch</b><br>wazuh-alerts-4.x-* · 128 万条原始告警<br>认证类规则 5715/5501/5763… full_log 含「谁登录了谁」",
               WHITE, BLUE_ST)
    d.edge("e_r1", r1, r2, "syslog / OTLP", BLUE, exit_dir="right", entry_dir="left")
    d.edge("e_l1", r2, p1, "query_range", BLUE, exit_dir="up", entry_dir="down")
    d.edge("e_l3", r3, p3, "认证日志抽取", "#94a3b8", exit_dir="up", entry_dir="down")

    d.save()


# ══════════════════════════════════════════════════════════
# 图 2：六规则打分引擎与闭环
# ══════════════════════════════════════════════════════════
def diagram_rules():
    d = Doc("behavior-rules", 1280, 880,
            "六规则加权打分引擎 · 从日志到处置闭环",
            "R1–R6 独立计分、加权求和、阈值分层；白名单前置过滤，30 分钟抑制防刷屏，高危自动升级并推送")

    # 左：输入与前置过滤
    i0 = d.box("i0", 48, 120, 220, 84,
               "<b>窗口内记录</b><br>(ip, domain, ts)<br>≈ 700 条 / 5 分钟",
               WHITE, BLUE_ST)
    i1 = d.box("i1", 48, 260, 220, 110,
               "<b>前置过滤</b><br>· 免检 IP（whitelist_ips）<br>· 域名白名单（exact + 通配）<br>· 公网 IP 剔除<br>· 按 (ip, domain) 聚合",
               GRAY_BG, GRAY_ST, font_size=12)
    d.edge("ei0", i0, i1, "去重后", BLUE, exit_dir="down", entry_dir="up")

    # 中：六规则 2x3
    d.box("rules_c", 300, 112, 640, 344, "", BLUE_BG, BLUE_ST)
    d.box("rules_ct", 316, 120, 400, 20, "RuleEngine · 六类检测规则（可配置启停）", "none", "none",
          font_size=13, bold=True, font_color=SUB, align="left")
    rules = [
        ("R1", "恶意域名命中", "100", "黑名单精确/通配匹配<br>+ 威胁情报 1000 条", RED_BG, RED_ST),
        ("R2", "突发高频访问", "40", "窗口内同 IP 同域名<br>&gt; 30 次（可调）", AMBER_BG, AMBER_ST),
        ("R3", "基线偏离", "20", "7 天基线中<br>未见过的域名", TEAL_BG, TEAL_ST),
        ("R4", "隧道/穿透工具", "35", "高风险 TLD 精确正则<br>stun.*.(xyz|top|cc|tk)", ORANGE_BG, ORANGE_ST),
        ("R5", "凌晨活跃", "15", "02–05 点 IP 级加成<br>（叠加到该 IP 每条域名）", INDIGO_BG, INDIGO_ST),
        ("R6", "可疑域名特征", "15", "熵 ≥ 4.0 / 超长 /<br>纯 IP 直连（DGA）", PURPLE_BG, PURPLE_ST),
    ]
    ids = []
    for idx, (rid, name, w_, desc, bg, st) in enumerate(rules):
        col, row = idx % 2, idx // 2
        x = 316 + col * 308
        y = 150 + row * 100
        cid = f"rule_{rid}"
        d.box(cid, x, y, 296, 90,
              f"<b>{rid} · {name}　+{w_} 分</b><br>{desc}",
              bg, st, font_size=12)
        ids.append(cid)
    d.edge("ei1", i1, "rule_R1", "逐条评估", BLUE, exit_dir="right", entry_dir="left")

    # 右：打分与分层
    s1 = d.box("s1", 992, 150, 240, 96,
               "<b>score = Σ 命中权重</b><br>rule_hits 记录命中明细<br>聚合一条事件取最高分",
               WHITE, BLUE_ST)
    s2 = d.box("s2", 992, 296, 240, 160,
              "<b>严重度分层</b><hr>"
              "score ≥ 100 → critical<br>score ≥ 80 → high<br>score ≥ 50 → medium<br>其余 → low（不落地）",
              WHITE, BLUE_ST, font_size=12.5)
    d.edge("es0", "rule_R2", s1, "", BLUE, exit_dir="right", entry_dir="left")
    d.edge("es1", s1, s2, "≥ 50 触发", BLUE, exit_dir="down", entry_dir="up")

    # 底：事件闭环
    d.box("loop", 300, 480, 932, 180, "", GREEN_BG, GREEN_ST)
    d.box("loop_t", 316, 488, 400, 20, "事件闭环（EventService + 前端处置）", "none", "none",
          font_size=13, bold=True, font_color=SUB, align="left")
    l1 = d.box("l1", 316, 516, 200, 120,
               "<b>事件入库</b><br>soc_browsing_events<br>状态 new → 处置流转<br>30 分钟抑制防刷屏",
               WHITE, GREEN_ST, font_size=12)
    l2 = d.box("l2", 544, 516, 200, 120,
               "<b>高危升级</b><br>severity ≥ high<br>→ soc_incidents<br>安全事件统一管理",
               WHITE, GREEN_ST, font_size=12)
    l3 = d.box("l3", 772, 516, 200, 120,
               "<b>实时通知</b><br>站内通知 + WebSocket<br>仅 high/critical 推送<br>防骚扰",
               WHITE, GREEN_ST, font_size=12)
    l4 = d.box("l4", 1000, 516, 216, 120,
               "<b>人工处置</b><br>确认 / 误报 / 忽略<br>一键加白名单<br>AI 研判 / 原始日志回溯",
               WHITE, GREEN_ST, font_size=12)
    d.edge("el1", s2, l1, "落库", "#059669", exit_dir="down", entry_dir="up")
    d.edge("el2", l1, l2, "", "#059669", exit_dir="right", entry_dir="left")
    d.edge("el3", l2, l3, "", "#059669", exit_dir="right", entry_dir="left")
    d.edge("el4", l3, l4, "", "#059669", exit_dir="right", entry_dir="left")
    # 误报回流
    d.edge("el5", l4, i1, "误报 → 加白名单回流", "#94a3b8", dashed=True,
           exit_dir="left", entry_dir="right")

    # 配置带
    d.box("cfg", 48, 700, 1184, 84,
          "<b>全部可运营（soc_system_config · category=browsing_detection · 18 项）</b><br>"
          "score_threshold / burst_threshold / night 窗口 / tunnel_keywords 正则 / 白名单域名与 IP / 抑制期 / 通知人 ……"
          "改配置 60 秒内热生效，规则试运行 POST /rules/test 可回放任意时间窗口不入库",
          GRAY_BG, GRAY_ST, font_size=12.5)
    d.save()


# ══════════════════════════════════════════════════════════
# 图 3：行为画像快照管道
# ══════════════════════════════════════════════════════════
def diagram_profile():
    d = Doc("behavior-profile", 1280, 880,
            "行为画像 · 快照管道与五层画像",
            "每日 02:00 水位回溯式快照：逐条日志聚合 → 三层分类 → 滚动 7 天打标签 → 快照表；查询层产出 L1 群体概览与 L2 单 IP 五层画像")

    # 顶部管道 6 步
    steps = [
        ("主体发现", "discover_targets", "近 7 天有行为 IP<br>∪ 内网资产<br>实测 73 个主体", TEAL_BG, TEAL_ST),
        ("按日拉取", "fetch_day_events", "Loki 逐条时间戳计数<br>（禁 count_over_time<br>防步长失真）", TEAL_BG, TEAL_ST),
        ("单日聚合", "aggregate_day", "by_hour[24] · wd_hour[7×24]<br>by_block[7] · domain_visits", BLUE_BG, BLUE_ST),
        ("域名分类", "classify", "14 类兴趣<br>× ACT/SYS/AD 三层<br>词典 5 分钟热更新", PURPLE_BG, PURPLE_ST),
        ("滚动合并", "merge_days(7)", "cat_share / top_domains<br>标签基于近 7 天口径", BLUE_BG, BLUE_ST),
        ("标签+置信度", "build_tags / confidence", "17 条规则带证据<br>数据量+截断惩罚 0–100", PURPLE_BG, PURPLE_ST),
    ]
    ids = []
    for i, (t, fn, desc, bg, st) in enumerate(steps):
        x = 48 + i * 198
        cid = f"st{i}"
        d.box(cid, x, 116, 184, 130,
              f"<b>{t}</b><br><font style=\"font-size:10.5px;color:#64748b\">{fn}</font><hr>{desc}",
              bg, st, font_size=12)
        ids.append(cid)
    for i in range(5):
        d.edge(f"es{i}", ids[i], ids[i + 1], "", "#2563eb", exit_dir="right", entry_dir="left")

    # 快照表
    snap = d.box("snap", 48, 296, 560, 96,
                 "<b>快照落库（幂等 upsert · 先删后插）</b><br>"
                 "soc_behavior_profiles：分布 + 标签 + traffic_type + confidence（status: ok / gap）<br>"
                 "soc_behavior_domains：每日 TOP 200 域名明细（可下钻单域名逐日曲线）",
                 AMBER_BG, AMBER_ST, font_size=12.5)
    d.edge("e_snap", ids[5], snap, "", "#94a3b8", exit_dir="down", entry_dir="up")

    # 机器判定
    mach = d.box("mach", 648, 296, 276, 96,
                 "<b>人 / 机器 / 混合判定</b><br>SYS 层占比 ≥ 50% → machine<br>辅助：TOP3 域名集中度 ≥ 50%<br>+ 24h 曲线变异系数 ≤ 0.15",
                 WHITE, PURPLE_ST, font_size=12)
    # 水位机制
    wm = d.box("wm", 952, 296, 280, 96,
               "<b>水位回溯与防假绿</b><br>last_completed_date 补缺口（≤8 天/轮）<br>超出 Loki 7 天窗口 → gap 占位<br>180 天留存自动清理",
               WHITE, TEAL_ST, font_size=12)
    d.edge("e_mach", "st3", mach, "layer_visit", "#7c3aed", exit_dir="down", entry_dir="up")

    # L2 五层画像
    d.box("l2c", 48, 440, 688, 396, "", INDIGO_BG, INDIGO_ST)
    d.box("l2ct", 64, 450, 500, 40,
          "<b>L2 · 单 IP 画像详情（/browsing/profile/detail/:ip）</b><br>左栏身份档案卡固定 · 右栏四个 Tab",
          "none", "none", font_size=13.5, align="left")
    layers = [
        ("层 1 · 身份档案", "IP/MAC/主机名/OS/责任人<br>关联账号（身份管道）<br>设备共享度 · 数据新鲜度"),
        ("层 2 · 行为画像", "标签卡置顶 → 24h 曲线 →<br>7 时段 → 星期×小时热力 →<br>分类×时段 → 域名 TOP 20"),
        ("层 3 · 风险画像", "告警分级/规则榜（AI 去噪）<br>漏洞 KEV 在野利用<br>危险端口 22/5901 · 评分趋势"),
        ("层 4 · 关系画像", "ECharts 力导向拓扑<br>出站绿/入站蓝/外部攻击红<br>点节点钻取对方画像"),
        ("层 5 · 异常判定", "访问量 5 倍激增 · 节律突变<br>机器流量 · 数据截断/缺失<br>信号+证据，人工复核定性"),
    ]
    for i, (t, desc) in enumerate(layers):
        y = 496 + i * 64
        d.box(f"ly{i}", 64, y, 656, 56,
              f"<b>{t}</b>　{desc}", WHITE, INDIGO_ST, font_size=11.5, align="left")

    # L1 概览 + 消费
    d.box("l1c", 776, 440, 456, 240, "", PINK_BG, PINK_ST)
    d.box("l1ct", 792, 450, 420, 20, "<b>L1 · 行为画像群体概览（/browsing/profile）</b>",
          "none", "none", font_size=13, align="left")
    d.box("l1a", 792, 478, 424, 190,
          "· 群体 KPI：主体数 / 人类 / 机器 / 数据完整度<br>"
          "· 人设分布：夜猫子 29 · 间歇上线 21 · 作息规律 20…<br>"
          "· 全网活跃节律（24h 曲线 + 时段占比）<br>"
          "· 全网兴趣构成：AI 工具 19.5% · 电商 15.2%…<br>"
          "· 风险分层 + 画像主体列表（筛选排序）<br>"
          "· 双 IP 余弦相似度对比 · 多日趋势 · MCP 工具",
          WHITE, PINK_ST, font_size=11.5, align="left", valign="top", spacing=8)
    d.box("entr", 776, 704, 456, 132,
          "<b>三个入口三级联动</b><br>资产列表点 IP · 告警详情点 agent_ip<br>行为基线点 IP → 直达画像详情<br><br>"
          "<b>合规约束</b><br>画像仅输出信号不定性，定性须人工复核<br>明细 ≥ 180 天自动清理",
          GRAY_BG, GRAY_ST, font_size=11.5)
    d.edge("e_l2a", snap, "l2c", "", "#94a3b8", exit_dir="down", entry_dir="up")
    d.edge("e_l1a", snap, "l1c", "", "#94a3b8", exit_dir="right", entry_dir="left")
    d.save()


# ══════════════════════════════════════════════════════════
# 图 4：误报治理前后对比
# ══════════════════════════════════════════════════════════
def diagram_fp():
    d = Doc("behavior-fp", 1280, 820,
            "误报治理 · 从「2353 条没人看」到「12 条值得看」",
            "上线 32 天的 0 处置 0 升级 0 通知 → 根因定位 → 三个配置项止血（1 小时）→ 告警量 -84%、有效率翻 4 倍")

    # 左：改造前（红）
    d.box("bad", 48, 112, 372, 420, "", RED_BG, RED_ST)
    d.box("badt", 64, 122, 340, 40, "<b>改造前 · 上线 32 天实测</b><br>（2026-08-03 ~ 09-04）",
          "none", "none", font_size=13, align="left")
    d.box("bad1", 64, 172, 340, 44,
          "2353 条告警 → <b>0 处置 · 0 升级 · 0 通知</b>", WHITE, RED_ST, font_size=12.5)
    d.box("bad2", 64, 228, 340, 64,
          "<b>96.9% 恰好 50 分</b><br>R4(35) + R5(15) = 50 正好压线<br>严重度分层实际退化为二元",
          WHITE, RED_ST, font_size=12)
    d.box("bad3", 64, 304, 340, 92,
          "<b>83% 告警来自 R4 误判 STUN</b><br>stun.miwifi.com（小米）· bilibili<br>stun.hitv.com（海信电视）…<br>均为 WebRTC/P2P 正常流量",
          WHITE, RED_ST, font_size=12)
    d.box("bad4", 64, 408, 340, 64,
          "<b>有效告警率仅 ~12%</b><br>真实可疑只有 stun.225284.xyz<br>等随机数字域名",
          WHITE, RED_ST, font_size=12)
    d.box("bad5", 64, 482, 340, 36,
          "基线只增不减：7 天语义 → 5 分钟", WHITE, RED_ST, font_size=12)

    # 中：根因链（amber）
    d.box("why", 452, 112, 340, 420, "", AMBER_BG, AMBER_ST)
    d.box("whyt", 468, 122, 308, 40, "<b>根因链（因果闭环死亡）</b>",
          "none", "none", font_size=13, align="left")
    whys = [
        "R4 把 STUN 当隧道工具<br><b>关键词语义误判</b>（设计缺陷）",
        "误报淹没列表<br>用户打开一次就再也不看",
        "R4+R5 恰好 50 分<br>永远够不到 high/critical",
        "升级与通知通道<br>从未打开过一次",
        "无人处置 → 无人调参<br>闭环彻底死亡",
    ]
    wids = []
    for i, t in enumerate(whys):
        y = 170 + i * 70
        cid = f"why{i}"
        d.box(cid, 468, y, 308, 56, t, WHITE, AMBER_ST, font_size=12)
        wids.append(cid)
    for i in range(4):
        d.edge(f"ew{i}", wids[i], wids[i + 1], "", "#d97706", exit_dir="down", entry_dir="up")

    # 右：止血（绿）
    d.box("fix", 824, 112, 408, 420, "", GREEN_BG, GREEN_ST)
    d.box("fixt", 840, 122, 376, 40, "<b>三步止血 N1–N3 · 1 小时完成</b><br>只改配置，不动代码",
          "none", "none", font_size=13, align="left")
    f1 = d.box("f1", 840, 172, 376, 88,
               "<b>N1 · tunnel_keywords 精确化</b><br>移除泛匹配 stun → 精确模式：<br>stun.[a-z0-9-]+.(xyz|top|cc|tk|buzz)<br>只命中高风险 TLD 的打洞域名",
               WHITE, GREEN_ST, font_size=12)
    f2 = d.box("f2", 840, 272, 376, 88,
               "<b>N2 · 默认白名单 8 条</b><br>*.miwifi.com · stun.chat.bilibili.com<br>*.heytapmobi.com · stun.l.google.com<br>…覆盖大厂/家电正常 P2P",
               WHITE, GREEN_ST, font_size=12)
    f3 = d.box("f3", 840, 372, 376, 64,
               "<b>N3 · EasyTier 白名单</b><br>*.easytier.cn 是知情自架组网<br>应白名单而非告警",
               WHITE, GREEN_ST, font_size=12)
    d.box("f4", 840, 448, 376, 70,
             "<b>规则试运行验证</b><br>POST /rules/test 回放历史窗口<br>改前改后同窗对比，不入库",
             WHITE, GREEN_ST, font_size=12)
    d.edge("ef1", f1, f2, "", "#059669", exit_dir="down", entry_dir="up")
    d.edge("ef2", f2, f3, "", "#059669", exit_dir="down", entry_dir="up")

    # 底：成效对比
    d.box("res", 48, 568, 1184, 120, "", INDIGO_BG, INDIGO_ST)
    d.box("rest", 64, 576, 400, 20, "<b>止血成效（2026-09-07 线上实测）</b>", "none", "none",
          font_size=13, bold=True, font_color=SUB, align="left")
    d.box("r1", 64, 602, 272, 72,
          "<b>日均告警 73.5 → 12 条</b><br>-84%，且全部聚焦<br>真可疑域名",
          WHITE, INDIGO_ST, font_size=12.5)
    d.box("r2", 352, 602, 272, 72,
          "<b>有效告警率 12% → 50%+</b><br>当日 top 域名即<br>stun.225284.xyz（18 次）",
          WHITE, INDIGO_ST, font_size=12.5)
    d.box("r3", 640, 602, 272, 72,
          "<b>基线规模受控</b><br>22937 行稳定在<br>7 天量级滚动",
          WHITE, INDIGO_ST, font_size=12.5)
    d.box("r4", 928, 602, 304, 72,
          "<b>Next：结构性修复</b><br>X1 基线清理挂载 · X2 延迟写入<br>X4 打分重构（R5 独立信号）",
          WHITE, INDIGO_ST, font_size=12.5)

    # 大箭头 前→后
    d.edge("ebig1", "bad2", "why1", "误报淹没", "#dc2626", exit_dir="right", entry_dir="left")
    d.edge("ebig2", "why4", f3, "止血", "#059669", exit_dir="right", entry_dir="left")
    d.save()


if __name__ == "__main__":
    diagram_arch()
    diagram_rules()
    diagram_profile()
    diagram_fp()
