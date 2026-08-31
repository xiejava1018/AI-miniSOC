#!/usr/bin/env python3
"""AI-miniSOC 博文配图生成器：纯 stdlib 生成 SVG，再用 Chrome headless 转 PNG。"""
import html
import os

DIR = os.path.dirname(os.path.abspath(__file__))
SVG_DIR = os.path.join(DIR, "svg")
os.makedirs(SVG_DIR, exist_ok=True)

FONT = "'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC',sans-serif"

INK = "#0f172a"
SUB = "#64748b"
BLUE = "#2563eb"
BLUE_BG, BLUE_ST = "#eff6ff", "#93c5fd"
INDIGO_BG, INDIGO_ST = "#eef2ff", "#a5b4fc"
TEAL_BG, TEAL_ST = "#f0fdfa", "#5eead4"
AMBER_BG, AMBER_ST = "#fffbeb", "#fcd34d"
ORANGE = "#d97706"
ORANGE_BG, ORANGE_ST = "#fff7ed", "#fdba74"
RED = "#dc2626"
RED_BG, RED_ST = "#fee2e2", "#fca5a5"
GREEN = "#059669"
GREEN_BG, GREEN_ST = "#ecfdf5", "#6ee7b7"
PURPLE_BG, PURPLE_ST = "#ede9fe", "#c4b5fd"
GRAY_BG, GRAY_ST = "#f8fafc", "#cbd5e1"
PINK_BG, PINK_ST = "#fdf2f8", "#f9a8d4"


def esc(s):
    return html.escape(s, quote=False)


def tw(s, size):
    """估算文本宽度：CJK 算 1em，其它算 0.62em。"""
    return sum(size if ord(ch) > 0x2E80 else size * 0.62 for ch in s)


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.p = []

    def rect(self, x, y, w, h, fill="none", stroke=None, rx=10, sw=1.5, dash=None, opacity=1):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.p.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{st}{d} opacity="{opacity}"/>'
        )

    def line(self, x1, y1, x2, y2, color=SUB, sw=1.5, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, size=14, fill=INK, weight=400, anchor="start", spacing=None):
        sp = f' letter-spacing="{spacing}"' if spacing else ""
        self.p.append(
            f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'text-anchor="{anchor}" font-family="{FONT}"{sp}>{esc(s)}</text>'
        )

    def mline(self, cx, y, rows, size=14, lh=None, fill=INK, weight=400, anchor="middle"):
        lh = lh or int(size * 1.55)
        for i, r in enumerate(rows):
            self.text(cx, y + i * lh, r, size=size, fill=fill, weight=weight, anchor=anchor)

    def arrow(self, x1, y1, x2, y2, color="#475569", sw=2, dash=None, head=9):
        import math
        self.line(x1, y1, x2, y2, color=color, sw=sw, dash=dash)
        ang = math.atan2(y2 - y1, x2 - x1)
        a1, a2 = ang + math.radians(153), ang - math.radians(153)
        p1 = (x2 + head * math.cos(a1), y2 + head * math.sin(a1))
        p2 = (x2 + head * math.cos(a2), y2 + head * math.sin(a2))
        self.p.append(
            f'<polygon points="{x2},{y2} {p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}" fill="{color}"/>'
        )

    def chip(self, cx, cy, s, size=13, fg=INK, bg=GRAY_BG, st=GRAY_ST, pad=14, h=30, weight=500):
        w = tw(s, size) + pad * 2
        self.rect(cx - w / 2, cy - h / 2, w, h, fill=bg, stroke=st, rx=h / 2)
        self.text(cx, cy + size * 0.36, s, size=size, fill=fg, weight=weight, anchor="middle")
        return w

    def chip_row(self, y, items, x0=60, x1=1180, size=13, h=30, gap=12, bg=GRAY_BG, st=GRAY_ST, fg=INK):
        widths = [tw(s, size) + 28 for s in items]
        total = sum(widths) + gap * (len(items) - 1)
        x = x0 + (x1 - x0 - total) / 2
        for s, w in zip(items, widths):
            self.rect(x, y - h / 2, w, h, fill=bg, stroke=st, rx=h / 2)
            self.text(x + w / 2, y + size * 0.36, s, size=size, fill=fg, anchor="middle", weight=500)
            x += w + gap

    def badge_num(self, x, y, n, color=BLUE):
        self.p.append(f'<circle cx="{x}" cy="{y}" r="11" fill="{color}"/>')
        self.text(x, y + 4.5, str(n), size=12, fill="#ffffff", weight=700, anchor="middle")

    def header(self, title, sub=None):
        self.text(48, 56, title, size=24, weight=700)
        if sub:
            self.text(48, 84, sub, size=14, fill=SUB)
        self.text(self.w - 48, 56, "AI-miniSOC", size=13, fill="#94a3b8", anchor="end", weight=600)

    def svg(self):
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}">'
            f'<rect width="{self.w}" height="{self.h}" fill="#ffffff"/>'
            + "".join(self.p)
            + "</svg>"
        )


def save(name, c):
    with open(os.path.join(SVG_DIR, name + ".svg"), "w", encoding="utf-8") as f:
        f.write(c.svg())
    print("svg:", name, c.w, "x", c.h)


# ───────────────────────── 1. 架构总览 ─────────────────────────
def d_arch():
    c = Canvas(1240, 940)
    c.header("AI-miniSOC 系统架构总览", "开源零件拼整车：Wazuh/Loki/Grafana/OpenSearch 继续做擅长的，平台补上 SOC 运营层与 AI 解读层")

    # 前端
    c.rect(60, 110, 1120, 132, fill=BLUE_BG, stroke=BLUE_ST)
    c.text(620, 148, "前端控制台 · Vue 3 + Element Plus + Pinia", size=18, weight=700, anchor="middle")
    c.chip_row(196, ["概览", "资产台账", "脆弱性", "事件", "告警", "上网行为", "扫描", "报告", "系统管理"],
               x0=90, x1=1150, bg="#ffffff", st=BLUE_ST)

    c.arrow(620, 248, 620, 300, color=BLUE)
    c.text(648, 280, "HTTP / WS · 统一响应 {code, msg, data}", size=13, fill=SUB)

    # 后端
    c.rect(60, 304, 1120, 190, fill=INDIGO_BG, stroke=INDIGO_ST)
    c.text(620, 340, "后端 API · FastAPI（Python 3.13 · async）", size=18, weight=700, anchor="middle")
    c.text(620, 364, "43 个路由模块 · 60+ 服务 · 52 张表（soc_ 前缀）· 39 个 Alembic 迁移", size=13, fill=SUB, anchor="middle")
    for i, (t, rows) in enumerate([
        ("API 路由层", ["统一鉴权 · 权限矩阵", "审计日志 · 响应包装"]),
        ("业务服务层", ["对账 · 评分 · 报告", "推送 · 调度 · 同步"]),
        ("AI 服务层", ["受限查询 · 模板路由", "诚实降级 · 反馈闭环"]),
    ]):
        x = 92 + i * 360
        c.rect(x, 386, 336, 90, fill="#ffffff", stroke=INDIGO_ST, rx=8)
        c.text(x + 168, 412, t, size=14, weight=700, anchor="middle")
        c.mline(x + 168, 436, rows, size=12.5, fill=SUB)

    # 中间件 4 盒
    mids = [
        ("PostgreSQL 16", ["52 张业务表", "Alembic 39 迁移"], GREEN_BG, GREEN_ST),
        ("AI 层 · 智谱 GLM", ["9 个消费点", "诚实降级"], AMBER_BG, AMBER_ST),
        ("可观测性", ["Prometheus", "OpenTelemetry"], GRAY_BG, GRAY_ST),
        ("通知渠道", ["邮件 / 钉钉 / 企微", "WebSocket 站内"], PINK_BG, PINK_ST),
    ]
    for i, (t, rows, bg, st) in enumerate(mids):
        x = 66 + i * 286
        c.arrow(x + 128, 494, x + 128, 546, color="#94a3b8")
        c.rect(x, 550, 256, 122, fill=bg, stroke=st)
        c.text(x + 128, 584, t, size=15, weight=700, anchor="middle")
        c.mline(x + 128, 612, rows, size=12.5, fill=SUB)

    # 采集器带
    c.rect(60, 726, 1120, 92, fill=TEAL_BG, stroke=TEAL_ST)
    c.text(88, 762, "采集器（Docker · 只做出向请求 · 穿透 NAT）", size=15, weight=700)
    c.text(88, 790, "心跳 30s · 拉任务 10s · 推数据 → POST /api/v1/data_sync", size=12.5, fill=SUB)
    for i, s in enumerate(["wazuh-collector", "tplink-collector", "scanner-collector"]):
        c.chip(985 + (i - 1) * 0, 772, s, bg="#ffffff", st=TEAL_ST, size=12.5) if False else None
    cw = [tw(s, 12.5) + 26 for s in ["wazuh-collector", "tplink-collector", "scanner-collector"]]
    cx0 = 1148 - (sum(cw) + 24)  # 右对齐，chip 间距 12
    for w, s in zip(cw, ["wazuh-collector", "tplink-collector", "scanner-collector"]):
        c.rect(cx0, 754, w, 30, fill="#ffffff", stroke=TEAL_ST, rx=15)
        c.text(cx0 + w / 2, 774, s, size=12.5, anchor="middle", weight=500)
        cx0 += w + 12

    # 基础设施带
    c.rect(60, 846, 1120, 64, fill=GRAY_BG, stroke=GRAY_ST)
    c.text(620, 884, "基础设施：Wazuh SIEM · Loki · Grafana · OpenSearch（生产部署于内网私有网段）",
           size=14.5, weight=600, anchor="middle", fill="#334155")
    return c


# ───────────────────────── 2. 拉模型对比 ─────────────────────────
def d_pull():
    c = Canvas(1240, 800)
    c.header("采集器为什么全是「拉模型」？", "现实内网：NAT 后、防火墙只许出不许进、路由器根本装不了 agent —— 那就让采集器只发出向请求")

    # 左：传统
    c.rect(40, 116, 560, 560, fill="#fffbfb", stroke=RED_ST, dash="6 4")
    c.text(320, 150, "传统模式：平台主动连 Agent", size=17, weight=700, anchor="middle", fill=RED)
    c.rect(70, 320, 140, 84, fill=GRAY_BG, stroke=GRAY_ST)
    c.mline(140, 354, ["SOC 平台", "(server)"], size=13, weight=600)
    c.line(430, 136, 430, 650, color=RED, sw=2, dash="7 5")
    c.mline(452, 168, ["NAT / 防火墙", "只许出不许进"], size=12, fill=RED, anchor="start", lh=18)
    devs = [(["服务器", "（装了 agent）"], 230), (["路由器", "（无法装 agent）"], 350), (["IoT / 打印机", "（装不了）"], 470)]
    for rows, y in devs:
        c.rect(470, y - 26, 124, 52, fill="#ffffff", stroke=GRAY_ST, rx=8)
        c.mline(532, y - 4, rows, size=11, lh=17, anchor="middle")
    for _, y in devs:
        c.arrow(210, 362, 464, y, color=RED, sw=1.8, dash="5 4")
        c.text(424, y - 10, "✗", size=17, fill=RED, weight=700, anchor="middle")
    c.text(320, 630, "✗ 设备在 NAT 后不可达，逐台开洞/装 agent 成本高", size=13.5, fill=RED, anchor="middle", weight=600)

    # 右：拉模型
    c.rect(640, 116, 560, 560, fill="#f6fffd", stroke=TEAL_ST, dash="6 4")
    c.text(920, 150, "AI-miniSOC：采集器主动出站（拉模型）", size=17, weight=700, anchor="middle", fill=GREEN)
    cols = [("wazuh-collector", 235, "心跳 30s"), ("tplink-collector", 355, "拉任务 10s"), ("scanner-collector", 475, "推数据")]
    for name, y, lbl in cols:
        c.rect(668, y - 26, 160, 52, fill="#ffffff", stroke=TEAL_ST, rx=8)
        c.text(748, y + 4, name, size=12, anchor="middle", weight=600)
        c.arrow(838, y, 1042, y, color=GREEN, sw=2.2)
        c.text(940, y - 12, lbl, size=12, fill=GREEN, anchor="middle", weight=600)
    c.line(1000, 136, 1000, 650, color="#94a3b8", sw=2, dash="7 5")
    c.text(1000, 676, "NAT / 防火墙（不变）", size=12, fill=SUB, anchor="middle")
    c.rect(1076, 320, 100, 120, fill=INDIGO_BG, stroke=INDIGO_ST)
    c.mline(1126, 360, ["AI-miniSOC", "平台", "(API)"], size=12.5, weight=700, lh=20)
    for _, y, _lbl in cols:
        c.p.append('<circle cx="1042" cy="%d" r="5" fill="%s"/>' % (y, GREEN))
    c.text(920, 630, "✓ 出向请求天然穿透 NAT · 任何设备都不需要开洞", size=13.5, fill=GREEN, anchor="middle", weight=600)

    # 底部策略条
    c.rect(60, 706, 1120, 60, fill=GRAY_BG, stroke=GRAY_ST)
    c.text(620, 742, "覆盖策略：装不了 agent 的设备，由路由器发现（tplink）+ 主动扫描（scanner）补齐 —— 采集器只部署在「能装软件」的主机上",
           size=13.5, weight=600, anchor="middle", fill="#334155")
    return c


# ───────────────────────── 3. 扫描器控制面/数据面 ─────────────────────────
def d_scanner():
    c = Canvas(1240, 840)
    c.header("攻击面扫描：控制面 / 数据面分离", "扫描器不自己决定扫什么 —— 显式注册、中央调度、结果回推，任何一台内网主机都能成为扫描探针")

    # 控制面
    c.rect(60, 120, 80, 150, fill="none", stroke="none")
    c.chip(120, 146, "控制面", bg=INDIGO_BG, st=INDIGO_ST, fg="#4338ca", size=13, weight=700)
    c.rect(220, 116, 800, 154, fill=INDIGO_BG, stroke=INDIGO_ST)
    c.text(620, 150, "AI-miniSOC 平台 · 控制面", size=17, weight=700, anchor="middle")
    inner = [("① 扫描器注册", ["admin 下发", "scanner_id + API Key"]), ("② 中央调度", ["任务队列 · 按任务", "mode 路由"]), ("③ Watchdog", ["离线监测", "状态追踪"])]
    for i, (t, rows) in enumerate(inner):
        x = 244 + i * 254
        c.rect(x, 172, 234, 76, fill="#ffffff", stroke=INDIGO_ST, rx=8)
        c.text(x + 117, 200, t, size=13.5, weight=700, anchor="middle")
        c.mline(x + 117, 222, rows, size=11, fill=SUB, lh=16)

    # 数据面
    c.chip(120, 470, "数据面", bg=TEAL_BG, st=TEAL_ST, fg="#0f766e", size=13, weight=700)
    c.rect(300, 420, 300, 110, fill=TEAL_BG, stroke=TEAL_ST)
    c.mline(450, 452, ["scanner-collector A", "（Kali 主机 · 常驻）", "nmap + python3"], size=13, weight=600, lh=22)
    c.rect(680, 420, 300, 110, fill=TEAL_BG, stroke=TEAL_ST)
    c.mline(830, 452, ["scanner-collector B", "（任意内网主机）", "30s 心跳 · 10s 拉任务"], size=13, weight=600, lh=22)

    # 双向箭头：心跳下行 / 拉任务上行
    c.arrow(400, 274, 400, 414, color=GREEN, sw=2.2)
    c.text(414, 330, "心跳 30s", size=12.5, fill=GREEN, weight=600)
    c.arrow(500, 414, 500, 274, color=BLUE, sw=2.2)
    c.text(514, 380, "拉任务 10s", size=12.5, fill=BLUE, weight=600)
    c.arrow(830, 414, 830, 274, color="#7c3aed", sw=2.2)
    c.text(844, 330, "⑤ 回推发现明细（④ 执行 Nmap）", size=12.5, fill="#7c3aed", weight=600)

    # 离线告警
    c.rect(1020, 430, 180, 90, fill=RED_BG, stroke=RED_ST)
    c.mline(1110, 462, ["扫描器离线", "→ 主动推送", "（第 6 推送场景）"], size=12, weight=600, lh=19, fill=RED)
    c.arrow(980, 470, 1014, 470, color=RED, sw=1.8, dash="5 4")

    # 产出
    c.arrow(620, 530, 620, 588, color=ORANGE, sw=2.2)
    c.rect(60, 592, 1120, 140, fill=ORANGE_BG, stroke=ORANGE_ST)
    c.text(620, 624, "扫描产出（自动入平台，无需人工比对）", size=15, weight=700, anchor="middle", fill="#9a3412")
    outs = [["影子资产自动入稽核", "（shadow）"], ["公网暴露面测绘", "（has_public_ip）"], ["端口多源融合", "port_sources"], ["发现端口 → vulners", "CVE 映射"]]
    for i, rows in enumerate(outs):
        x = 100 + i * 268
        c.rect(x, 648, 248, 56, fill="#ffffff", stroke=ORANGE_ST, rx=8)
        c.mline(x + 124, 672, rows, size=11.5, lh=18, anchor="middle")
    return c


# ───────────────────────── 4. 资产对账 ─────────────────────────
def d_recon():
    c = Canvas(1240, 780)
    c.header("资产台账如何自动追上现实？", "多源数据汇入同一台账，对账引擎持续产出三类差异 —— 从「一张 Excel」到「自动对账的差异队列」")

    srcs = [("Wazuh 同步", "agent / SCA / SCAP", 150), ("TP-Link 路由器", "内网资产 + 上网行为", 290), ("Nmap 扫描", "端口 / 服务 / 暴露面", 430)]
    for t, s, y in srcs:
        c.rect(60, y - 42, 240, 84, fill=GRAY_BG, stroke=GRAY_ST)
        c.text(180, y - 8, t, size=14.5, weight=700, anchor="middle")
        c.text(180, y + 16, s, size=12, fill=SUB, anchor="middle")
        c.arrow(300, y, 448, 350 if y == 290 else (316 if y == 150 else 384), color="#64748b")

    c.rect(452, 236, 300, 228, fill=BLUE_BG, stroke=BLUE_ST)
    c.text(602, 274, "统一资产台账", size=17, weight=700, anchor="middle")
    c.text(602, 298, "soc_assets", size=12.5, fill=BLUE, anchor="middle", weight=600)
    c.mline(602, 330, ["data_source / source_id 溯源", "标签 · 业务单元 · 风险评分", "公网 IP 属性 · EOL 生命周期"], size=12, fill=SUB, lh=22)
    c.rect(472, 400, 260, 48, fill="#ffffff", stroke=BLUE_ST, rx=8)
    c.mline(602, 420, ["端口多源汇聚", "soc_asset_port_sources"], size=11.5, lh=16, anchor="middle")

    c.arrow(756, 350, 828, 350, color="#64748b", sw=2.2)
    c.rect(832, 280, 130, 140, fill=PURPLE_BG, stroke=PURPLE_ST)
    c.mline(897, 336, ["对账引擎", "reconciliation", "（定时/触发）"], size=13, weight=700, lh=22)

    diffs = [
        ("shadow 影子资产", "现实有 · 台账无", "扫描发现自动入稽核", RED_BG, RED_ST, RED, 150),
        ("offline 失联资产", "台账有 · 现实无", "下线 / 淘汰确认", GRAY_BG, GRAY_ST, "#475569", 300),
        ("mismatch 属性漂移", "IP / 系统 / agent 不一致", "人工核实修正", AMBER_BG, AMBER_ST, "#92400e", 450),
    ]
    for t, l1, l2, bg, st, fg, y in diffs:
        c.arrow(962, 350, 1006, y, color="#94a3b8")
        c.rect(1010, y - 44, 200, 88, fill=bg, stroke=st)
        c.text(1110, y - 18, t, size=13, weight=700, anchor="middle", fill=fg)
        c.mline(1110, y + 2, [l1, l2], size=11, lh=17, anchor="middle", fill=SUB)

    c.rect(60, 620, 1120, 68, fill="#f1f5f9", stroke=GRAY_ST)
    c.text(620, 660, "差异 → 处理队列 + 主动推送（影子资产发现）+ 对账 AI 解读报告 —— 运营者只处理「该处理的事」",
           size=14, weight=600, anchor="middle", fill="#334155")
    return c


# ───────────────────────── 5. 受限查询 ─────────────────────────
def d_guarded():
    c = Canvas(1240, 880)
    c.header("自然语言查资产：LLM 永远不生成 SQL", "模型只负责「翻译意图」：L1 出受控参数、L2 选模板填参数；越权的部分由代码和校验拦住")

    c.rect(60, 350, 210, 120, fill=GRAY_BG, stroke=GRAY_ST)
    c.mline(165, 396, ["运营者提问", "“哪些资产开着 3389", "且临近 EOL？”"], size=13, weight=600, lh=21)
    c.arrow(270, 410, 330, 410, color="#64748b")
    c.rect(334, 350, 170, 120, fill=PURPLE_BG, stroke=PURPLE_ST)
    c.mline(419, 392, ["意图路由", "L1 简单查询", "L2 复合查询"], size=13, weight=700, lh=21)

    c.arrow(504, 396, 554, 250, color=BLUE)
    c.arrow(504, 424, 554, 570, color="#7c3aed")
    c.rect(558, 170, 280, 110, fill="#ffffff", stroke=BLUE_ST)
    c.text(698, 202, "L1：翻译为受控查询参数", size=13.5, weight=700, anchor="middle")
    c.mline(698, 228, ["单实体条件查询", "（字段 / 值 / 逻辑均受控）"], size=11.5, lh=18, anchor="middle", fill=SUB)
    c.rect(558, 508, 280, 130, fill="#ffffff", stroke=PURPLE_ST)
    c.text(698, 540, "L2：只允许「选模板 + 填参数」", size=13.5, weight=700, anchor="middle")
    c.mline(698, 566, ["模板库 query_templates.yaml", "（4 个复合查询模板）", "模型不接触任何 SQL"], size=11.5, lh=18, anchor="middle", fill=SUB)

    # 安全围栏
    c.line(880, 130, 880, 700, color=ORANGE, sw=2.5, dash="8 6")
    c.text(880, 112, "安全围栏（代码实现）", size=13, fill=ORANGE, weight=700, anchor="middle")
    c.arrow(838, 225, 906, 300, color=BLUE)
    c.arrow(838, 573, 906, 500, color="#7c3aed")

    c.rect(908, 268, 300, 150, fill=GREEN_BG, stroke=GREEN_ST)
    c.text(1058, 296, "受限执行器", size=15, weight=700, anchor="middle")
    c.mline(1058, 320, ["① 参数三层校验（类型/范围/枚举）", "② 查询维度白名单", "③ SQL 由代码按白名单生成", "④ 统计类强制返回 coverage"], size=11.5, lh=20, anchor="middle")
    c.arrow(1058, 418, 1058, 456, color=GREEN)
    c.rect(908, 460, 300, 92, fill="#ffffff", stroke=GREEN_ST)
    c.mline(1058, 492, ["查询结果 + coverage 覆盖率", "统计结论必须说明覆盖了多少资产"], size=12, lh=20, anchor="middle")

    c.rect(60, 690, 780, 92, fill=RED_BG, stroke=RED_ST)
    c.text(88, 724, "✗ 模型不生成 SQL · 无原始数据库访问", size=14.5, weight=700, fill=RED)
    c.text(88, 752, "提示词注入样本 → 全部拒绝（W0 对抗样本 5/5 拒绝）；模型犯错的爆炸半径 =「结果不对」，而不是「拖库」", size=12.5, fill="#7f1d1d")
    c.arrow(840, 736, 874, 736, color=RED, sw=2, dash="5 4")

    c.text(620, 836, "W0 评测集：50 条用例 · 基线准确率 98% · 对抗样本 5/5 拒绝", size=15, weight=700, anchor="middle", fill="#334155")
    return c


# ───────────────────────── 6. AI 全景与降级 ─────────────────────────
def d_landscape():
    c = Canvas(1240, 820)
    c.header("AI 是解释者，不是决策者", "9 个消费点共用一个 GLM 底座；每个消费点都有非 AI 降级路径，且明确告诉用户「这是降级输出」")

    c.text(200, 132, "9 个 AI 消费点", size=15, weight=700, fill="#4338ca")
    pts = ["自然语言资产查询（L1 + L2）", "风险摘要 · 态势解读", "AI 安全报告（4 种触发）", "变更影响分析", "资产对账 AI 解读", "合规基线 AI 解读", "AI Chat", "AI Agent", "审计覆盖（AI 消费可审计）"]
    for i, s in enumerate(pts):
        y = 152 + i * 56
        c.rect(60, y, 290, 44, fill="#ffffff", stroke=INDIGO_ST, rx=8)
        c.text(205, y + 28, s, size=12.5, weight=500, anchor="middle")
        c.line(350, y + 22, 380, y + 22, color="#a5b4fc", sw=1.5)
    c.line(380, 174, 380, 600, color="#a5b4fc", sw=2)
    c.arrow(380, 387, 468, 387, color="#a5b4fc", sw=2)

    c.rect(472, 290, 210, 194, fill=AMBER_BG, stroke="#f59e0b", sw=2)
    c.mline(577, 336, ["智谱 GLM", "统一大模型底座", "glm-4-flash", "单点可禁用 / 换模型"], size=14, weight=700, lh=25)

    c.text(1030, 132, "失败时 → 诚实降级", size=15, weight=700, fill=ORANGE)
    drops = [("规则统计摘要", "风险摘要 → 纯规则计算"), ("模板化报告", "AI 报告 → 模板生成"), ("受控模板应答", "Chat / 查询 → 模板兜底")]
    for i, (t, s) in enumerate(drops):
        y = 170 + i * 150
        c.arrow(682, 387, 906, y + 50, color="#fbbf24", sw=1.8, dash="6 5")
        c.rect(910, y, 290, 110, fill=ORANGE_BG, stroke=ORANGE_ST)
        c.text(1055, y + 40, t, size=14, weight=700, anchor="middle", fill="#9a3412")
        c.text(1055, y + 68, s, size=11.5, fill=SUB, anchor="middle")
    c.rect(452, 540, 250, 92, fill="#f1f5f9", stroke=GRAY_ST)
    c.mline(577, 576, ["每个消费点都标注", "「降级输出」——", "绝不静默编造"], size=12.5, weight=600, lh=20)

    c.rect(60, 690, 1120, 76, fill="#f1f5f9", stroke=GRAY_ST)
    rules = ["① 不生成 SQL（受限执行）", "② 诚实降级（明示非 AI 输出）", "③ 解释者而非决策者（确定性归代码）"]
    for i, s in enumerate(rules):
        x = 260 + i * 360
        c.text(x, 734, s, size=14.5, weight=700, anchor="middle", fill="#334155")
    return c


# ───────────────────────── 7. 数据健康 ─────────────────────────
def d_health():
    c = Canvas(1240, 760)
    c.header("数据链路的「静默失败」怎么破？", "三层聚合把沉默变成信号：源健康 → 死信队列 → 对账差异，再由 6 场景主动推送找人")

    layers = [
        ("① 源健康 source_health", ["每个数据源的最近心跳 · 延迟 · 错误率，", "链路断没断一眼可见"], BLUE_BG, BLUE_ST, 130),
        ("② 同步死信 sync_dead_letter", ["同步失败的记录进死信队列", "→ 可查 · 可重放，而不是悄悄丢掉"], AMBER_BG, AMBER_ST, 300),
        ("③ 对账差异 reconciliation", ["用「现实」反推数据链路：", "影子 / 失联 / 属性漂移三层兜底"], GREEN_BG, GREEN_ST, 470),
    ]
    for t, rows, bg, st, y in layers:
        c.rect(60, y, 620, 130, fill=bg, stroke=st)
        c.text(90, y + 42, t, size=16, weight=700)
        c.mline(90, y + 74, rows, size=12.5, fill=SUB, anchor="start", lh=20)
    c.arrow(370, 260, 370, 294, color="#94a3b8")
    c.arrow(370, 430, 370, 464, color="#94a3b8")

    c.arrow(690, 365, 748, 365, color="#db2777", sw=2.2)
    c.rect(754, 130, 426, 470, fill=PINK_BG, stroke=PINK_ST)
    c.text(967, 170, "主动推送 · 6 场景", size=17, weight=700, anchor="middle", fill="#9d174d")
    pushes = ["数据链路异常", "风险评分突变", "EOL 临近 / 到期", "影子资产发现", "报告生成完成", "扫描器离线"]
    for i, s in enumerate(pushes):
        y = 210 + i * 54
        c.p.append(f'<circle cx="800" cy="{y - 5}" r="4" fill="#db2777"/>')
        c.text(818, y, s, size=13.5, weight=600)
    c.rect(784, 532, 366, 44, fill="#ffffff", stroke=PINK_ST, rx=8)
    c.text(967, 560, "邮件 · 钉钉 · 企业微信 · 站内 WebSocket", size=12.5, anchor="middle", weight=600, fill="#9d174d")

    c.text(620, 682, "设计信条：平台的「沉默」本身，也是一次需要告警的事件", size=17, weight=700, anchor="middle", fill="#334155")
    c.text(620, 712, "一个基于错误数据做出的「一切安全」判断，比没有平台更危险", size=13, fill=SUB, anchor="middle")
    return c


# ───────────────────────── 8. 告警坟场示意 ─────────────────────────
def d_graveyard():
    c = Canvas(1240, 700)
    c.header("为什么告警的价值不在「产生」，而在「被读懂」？", "SIEM 把告警生产到了百万量级，人的消化能力几乎是条水平线")

    ox, oy, top = 110, 560, 150
    c.line(ox, top, ox, oy, color="#334155", sw=2)
    c.line(ox, oy, 1150, oy, color="#334155", sw=2)
    for i in range(1, 5):
        x = ox + i * 240
        c.line(x, top, x, oy, color="#e2e8f0", sw=1)
        c.text(x, 584, f"第 {i} 个月", size=12, fill=SUB, anchor="middle")
    for v, y in [(20, 474), (40, 388), (60, 302), (80, 216), (100, 130)]:
        c.text(96, y + 4, str(v), size=11.5, fill=SUB, anchor="end")
        c.line(ox, y, 1150, y, color="#e2e8f0", sw=1)
    c.text(60, 118, "累计告警（万条）", size=12.5, fill=SUB)

    alert_path = "M 110 552 C 300 520, 420 470, 560 400 C 700 330, 860 240, 1000 190 C 1060 168, 1110 156, 1130 152"
    c.p.append(f'<path d="{alert_path} L 1130 560 L 110 560 Z" fill="#fee2e2" opacity="0.55"/>')
    c.p.append(f'<path d="{alert_path}" fill="none" stroke="#dc2626" stroke-width="3.5"/>')
    human_path = "M 110 548 C 350 542, 700 536, 1130 528"
    c.p.append(f'<path d="{human_path}" fill="none" stroke="#059669" stroke-width="3.5" stroke-dasharray="10 6"/>')
    c.text(1130, 518, "人工能深度审阅的量级 →", size=12.5, fill=GREEN, anchor="end", weight=600)
    c.text(1078, 142, "累计 103 万+（实测规模）", size=12.5, fill=RED, anchor="end", weight=600)

    c.text(560, 300, "告警坟场：产生 ≠ 价值", size=28, weight=700, fill=RED, anchor="middle")
    c.mline(560, 336, ["一百万条技术性极强的 JSON 告警，对兼职网管来说等于零：", "既看不完，也看不懂"], size=14, lh=22, anchor="middle", fill="#7f1d1d")

    c.text(620, 640, "AI-miniSOC 的切入点：不是再造一个「产生告警」的系统，而是给存量告警配一个「翻译官」", size=14.5, weight=600, anchor="middle", fill="#334155")
    c.text(620, 668, "示意图：以本项目环境实测规模（OpenSearch 中 103 万+ 告警文档）为参照的趋势示意，非逐日统计", size=11.5, fill="#94a3b8", anchor="middle")
    return c


# ───────────────────────── 9. CI/CD ─────────────────────────
def d_cicd():
    c = Canvas(1240, 640)
    c.header("发版 = 一次 git push", "CI 全绿自动部署，探活失败自动回滚 —— 发布和回滚都不需要人到场")

    boxes = [
        ("git push master", ["唯一发版动作"], GRAY_BG, GRAY_ST),
        ("CI", ["lint · pytest · build", "前后端 4 个 workflow"], BLUE_BG, BLUE_ST),
        ("自动部署", ["self-hosted runner", "pip + vite build", "systemctl restart"], PURPLE_BG, PURPLE_ST),
        ("部署探活", ["HTTP + DB 双检查", "失败即触发回滚"], AMBER_BG, AMBER_ST),
        ("✓ 上线", ["全流程约 1.5 分钟"], GREEN_BG, GREEN_ST),
    ]
    for i, (t, rows, bg, st) in enumerate(boxes):
        x = 60 + i * 232
        c.rect(x, 170, 196, 150, fill=bg, stroke=st)
        c.text(x + 98, 202, t, size=14.5, weight=700, anchor="middle")
        c.mline(x + 98, 230, rows, size=11.5, lh=19, anchor="middle", fill=SUB)
        if i < 4:
            c.arrow(x + 196, 245, x + 228, 245, color="#475569", sw=2.2)

    c.text(1180, 140, "sudoers：NOPASSWD 10 条最小权限 · 无人值守", size=12, fill=SUB, anchor="end")

    c.arrow(875, 320, 875, 400, color=RED, sw=2.2, dash="6 5")
    c.text(893, 368, "任一步失败", size=12.5, fill=RED, weight=600)
    c.rect(460, 404, 560, 110, fill=RED_BG, stroke=RED_ST)
    c.text(740, 444, "trap 全局回滚 → 自动还原到上一 commit", size=15, weight=700, anchor="middle", fill=RED)
    c.text(740, 476, "部署日志可追溯（/tmp/aisoc-deploy.log）；手动回滚 / 重部署走 workflow_dispatch 填 SHA", size=12, fill="#7f1d1d", anchor="middle")
    c.arrow(560, 404, 560, 330, color=RED, sw=1.8, dash="5 4")
    c.text(546, 368, "回滚", size=12, fill=RED, weight=600, anchor="end")

    c.rect(60, 404, 340, 110, fill="#f1f5f9", stroke=GRAY_ST)
    c.text(230, 444, "采集器同样覆盖", size=14, weight=700, anchor="middle")
    c.mline(230, 470, ["deploy_collectors.sh", "健康门禁 + 僵尸进程核查"], size=11.5, lh=19, anchor="middle", fill=SUB)
    return c


# ───────────────────────── 截图占位 ─────────────────────────
SHOTS = [
    ("shot-dashboard", "总览仪表板", "风险概览 + AI 态势摘要卡片", "页面 /dashboard/console"),
    ("shot-asset-list", "资产台账列表", "能看到 data_source 溯源列与风险评分", "页面 /asset/list"),
    ("shot-asset-ask", "自然语言资产问答", "输入一个业务问题 + AI 回答（展示 L1/L2 路由标识）", "资产列表页的 AI 问数入口"),
    ("shot-reconciliation", "资产稽核差异队列", "shadow / offline / mismatch 三类差异同框", "页面 /asset/reconciliation"),
    ("shot-data-health", "数据健康三层聚合", "源健康 + 同步死信 + 对账差异", "页面 /ops/data-health"),
    ("shot-scan-tasks", "扫描任务", "任务列表 + 详情（本次扫描端口 / 发现明细）", "页面 /scan/tasks"),
    ("shot-scan-findings", "发现清单 / 公网暴露面", "端口明细 + CVE 关联 + 批量操作", "页面 /scan/findings"),
    ("shot-report", "AI 安全报告", "生成完成的周报 / 月报内容", "页面 /reports/list"),
    ("shot-alert", "告警治理", "告警分级聚合（13/10/7/4 四档阈值）", "页面 /alert"),
]


def placeholder(name, title, desc, page):
    c = Canvas(1280, 720)
    c.rect(0, 0, 1280, 720, fill="#f8fafc")
    c.rect(34, 34, 1212, 652, fill="none", stroke="#94a3b8", rx=18, sw=2.5, dash="10 8")
    # 矢量相机图标（resvg 无彩色 emoji 字体）
    c.p.append('<circle cx="640" cy="260" r="58" fill="#e2e8f0"/>')
    c.rect(622, 234, 22, 12, fill="#475569", rx=4)
    c.rect(606, 244, 68, 48, fill="#475569", rx=8)
    c.p.append('<circle cx="640" cy="268" r="15" fill="#f8fafc"/>')
    c.p.append('<circle cx="640" cy="268" r="9" fill="#94a3b8"/>')
    c.text(640, 392, "截图占位 · " + title, size=30, weight=700, anchor="middle", fill="#334155")
    c.text(640, 446, desc, size=17, fill=SUB, anchor="middle")
    c.text(640, 492, "拍摄位置：" + page, size=15, fill=BLUE, anchor="middle", weight=600)
    c.text(640, 570, f"docs/blog/images/{name}.png", size=17, weight=700, anchor="middle", fill="#0f172a")
    c.text(640, 604, "按此文件名保存截图并覆盖本文件即可，Markdown 无需改动", size=13.5, fill=SUB, anchor="middle")
    save(name, c)


if __name__ == "__main__":
    for fn in [d_arch, d_pull, d_scanner, d_recon, d_guarded, d_landscape, d_health, d_graveyard, d_cicd]:
        save(fn.__name__.replace("d_", "diagram-"), fn())
    for args in SHOTS:
        placeholder(*args)
    print("done")
