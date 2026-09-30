#!/usr/bin/env python3
"""行为分析模块博文截图占位图（与 gen_diagrams.py placeholder 同风格）。"""
import html
import os

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "images")
os.makedirs(DIR, exist_ok=True)

FONT = "'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC',sans-serif"
INK, SUB, BLUE = "#0f172a", "#64748b", "#2563eb"


def esc(s):
    return html.escape(s, quote=False)


def placeholder(name, title, desc, page):
    p = []
    p.append('<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">')
    p.append('<rect width="1280" height="720" fill="#f8fafc"/>')
    p.append(f'<rect x="34" y="34" width="1212" height="652" rx="18" fill="none" stroke="#94a3b8" stroke-width="2.5" stroke-dasharray="10 8"/>')
    p.append('<circle cx="640" cy="260" r="58" fill="#e2e8f0"/>')
    p.append('<rect x="622" y="234" width="22" height="12" rx="4" fill="#475569"/>')
    p.append('<rect x="606" y="244" width="68" height="48" rx="8" fill="#475569"/>')
    p.append('<circle cx="640" cy="268" r="15" fill="#f8fafc"/>')
    p.append('<circle cx="640" cy="268" r="9" fill="#94a3b8"/>')
    for i, (s, y, c, w) in enumerate([
        ("截图占位 · " + title, 392, "#334155", 700),
        (desc, 446, SUB, 400),
        ("拍摄位置：" + page, 492, BLUE, 600),
        (f"docs/blog/images/{name}.png", 570, INK, 700),
        ("按此文件名保存截图并覆盖本文件即可，Markdown 无需改动", 604, SUB, 400),
    ]):
        p.append(f'<text x="640" y="{y}" font-size="{30 if i == 0 else 17 if i < 4 else 13.5}" fill="{c}" font-weight="{w}" text-anchor="middle" font-family="{FONT}">{esc(s)}</text>')
    p.append("</svg>")
    with open(os.path.join(DIR, f"{name}.svg"), "w") as f:
        f.write("".join(p))
    print("wrote", name + ".svg")


SHOTS = [
    ("shot-behavior-events", "异常事件列表", "分值/等级/命中规则/处置动作，top 域名应聚焦真可疑", "页面 /browsing/event"),
    ("shot-behavior-stats", "行为统计", "24h 趋势 / TOP 域名 / 应用类型分布 / 凌晨活跃 IP", "页面 /browsing/statistics"),
    ("shot-behavior-config", "规则配置", "18 项可热生效配置：阈值 / tunnel_keywords / 白名单", "页面 /browsing/config"),
    ("shot-behavior-baseline", "行为基线", "IP × 域名 7 天滚动基线（22937 行）", "页面 /browsing/baseline"),
    ("shot-profile-l1", "行为画像 L1 群体概览", "73 主体 / 人设分布 / 全网节律与兴趣 / 主体列表", "页面 /browsing/profile"),
    ("shot-profile-l2-behavior", "L2 画像详情 · 行为 Tab", "标签卡 + 24h 曲线 + 星期热力 + 分类×时段 + 域名 TOP", "页面 /browsing/profile/detail/:ip（如 192.168.0.17）"),
    ("shot-profile-l2-relation", "L2 画像详情 · 关系拓扑", "力导向图：出站绿 / 入站蓝 / 外部攻击红，点节点钻取", "详情页关系 Tab（如 192.168.0.102：xiejava ×1176）"),
    ("shot-profile-l2-anomaly", "L2 画像详情 · 异常判定", "信号清单 + 证据 + 生成安全事件/加白按钮 + 免责声明", "详情页异常 Tab"),
]

if __name__ == "__main__":
    for a in SHOTS:
        placeholder(*a)
