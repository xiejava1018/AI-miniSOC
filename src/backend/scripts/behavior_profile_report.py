"""
行为画像报告生成器
==================
把 behavior_profile_collect.py 产出的 JSON 渲染成单页 HTML 报告。

包含五个层次：
  1. 身份档案   —— 设备是谁、什么类型
  2. 活跃节律   —— 24h 曲线 / 星期×小时热力图 / 时段分布
  3. 访问构成   —— 域名 TOP N / 兴趣分类占比 / 分类×时段堆叠
  4. 画像标签   —— 规则引擎给出的性格标签（每项附证据）
  5. 数据说明   —— 样本量、置信度、已知偏差

用法: python scripts/behavior_profile_report.py
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(HERE, "behavior_profile_data.json")
OUT = os.path.join(REPO, "docs", "reports", "2026-09-05-行为画像报告.html")

E = lambda s: html.escape(str(s if s is not None else ""))
NN = lambda s: s if s not in (None, "", "None") else "—"
NUM = lambda v: int(v) if isinstance(v, (int, float)) else int(str(v or 0))

WD = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
BLOCK_ORDER = ["深夜", "早晨", "上午", "午间", "下午", "傍晚", "夜间"]


def fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return "0"


# ─────────────────────────────────────────────────────────────
# 组件
# ─────────────────────────────────────────────────────────────
def metric(v, label, sub="", color="#1971c2"):
    s = f'<div class="sub">{E(sub)}</div>' if sub else ""
    return (f'<div class="metric"><div class="mv" style="color:{color}">{v}</div>'
            f'<div class="ml">{E(label)}</div>{s}</div>')


def hour_bars(by_hour, blocks):
    """24 小时活跃柱状图（按所处时段着色）。"""
    mx = max(by_hour) or 1
    cells = []
    for h in range(24):
        v = by_hour[h]
        pct = v / mx * 100
        color = "#adb5bd"
        for b in blocks:
            if b["label"].startswith(f"{h:02d}"):
                color = b["color"]
        peak = "peak" if v == mx else ""
        cells.append(
            f'<div class="hb-col {peak}">'
            f'<div class="hb-track"><div class="hb-fill" style="height:{pct:.1f}%;'
            f'background:{color}"></div></div>'
            f'<div class="hb-lbl">{h:02d}</div></div>')
    return f'<div class="hb">{"".join(cells)}</div>'


def heatmap(wd_hour):
    """星期 × 小时热力图。"""
    flat = [v for row in wd_hour for v in row]
    mx = max(flat) or 1
    rows = []
    head = "".join(f'<div class="hm-c hm-h">{h:02d}</div>' for h in range(24))
    rows.append(f'<div class="hm-row"><div class="hm-rl"></div>{head}</div>')
    for i, row in enumerate(wd_hour):
        cells = []
        for v in row:
            if v == 0:
                bg = "#f1f3f5"
            else:
                t = v / mx
                # 浅蓝 → 深蓝
                bg = f"rgba(25,113,194,{0.12 + t * 0.88:.3f})"
            fg = "#fff" if v / mx > 0.55 else "transparent"
            tip = f"{WD[i]} {v:,}"
            cells.append(f'<div class="hm-c" style="background:{bg}" title="{tip}">'
                         f'<span style="color:{fg}"></span></div>')
        rows.append(f'<div class="hm-row"><div class="hm-rl">{WD[i]}</div>'
                    f'{"".join(cells)}</div>')
    return f'<div class="hm">{"".join(rows)}</div>'


def block_bars(by_block, total):
    """7 个时段分布横条。"""
    order = [b for b in BLOCK_ORDER]
    out = []
    for name in order:
        v = by_block.get(name, 0)
        pct = v / total * 100 if total else 0
        color = next((b["color"] for b in TIME_BLOCKS if b["name"] == name), "#adb5bd")
        out.append(
            f'<div class="bb-row"><div class="bb-name">{E(name)}</div>'
            f'<div class="bb-track"><div class="bb-fill" style="width:{max(pct,0.6):.1f}%;'
            f'background:{color}"></div></div>'
            f'<div class="bb-v">{fmt(v)}<span class="bb-p">{pct:.1f}%</span></div></div>')
    return f'<div class="bb">{"".join(out)}</div>'


def cat_bars(cat_share, cat_visit, cats):
    """兴趣分类占比（只统计主动行为 ACT 层）。"""
    out = []
    for c, pct in list(cat_share.items()):
        meta = cats.get(c, {})
        color = meta.get("color", "#adb5bd")
        icon = meta.get("icon", "·")
        v = cat_visit.get(c, 0)
        out.append(
            f'<div class="cb-row"><div class="cb-name">'
            f'<span class="cb-ico" style="background:{color}">{E(icon)}</span>{E(c)}</div>'
            f'<div class="cb-track"><div class="cb-fill" style="width:{max(pct,0.5):.1f}%;'
            f'background:{color}"></div></div>'
            f'<div class="cb-v">{fmt(v)}<span class="cb-p">{pct:.1f}%</span></div></div>')
    return f'<div class="cb">{"".join(out)}</div>'


def cat_block_stack(cat_by_block, cats, top_n=7):
    """分类 × 时段 堆叠条：看「深夜到底在干什么」。"""
    rows = []
    for b in BLOCK_ORDER:
        cnt = cat_by_block.get(b, {})
        tot = sum(cnt.values()) or 1
        segs = []
        for c, v in sorted(cnt.items(), key=lambda t: -t[1])[:top_n]:
            meta = cats.get(c, {})
            color = meta.get("color", "#adb5bd")
            pct = v / tot * 100
            segs.append(
                f'<div class="st-seg" style="width:{pct:.2f}%;background:{color}" '
                f'title="{E(c)} {fmt(v)} ({pct:.1f}%)"></div>')
        legend = " · ".join(
            f'<span class="lg"><i style="background:{cats.get(c,{}).get("color","#adb5bd")}"></i>'
            f'{E(c)} {v/tot*100:.0f}%</span>'
            for c, v in sorted(cnt.items(), key=lambda t: -t[1])[:3])
        rows.append(
            f'<div class="st-row"><div class="st-b">{E(b)}</div>'
            f'<div class="st-bar">{"".join(segs)}</div>'
            f'<div class="st-lg">{legend}</div></div>')
    return f'<div class="st">{"".join(rows)}</div>'


def domain_table(top_domains, cats, total, limit=20):
    mx = top_domains[0]["visits"] if top_domains else 1
    rows = []
    for r in top_domains[:limit]:
        c = r.get("category", "其他")
        meta = cats.get(c, {})
        color = meta.get("color", "#adb5bd")
        pct = r["visits"] / mx * 100
        rows.append(
            f'<tr><td class="dt-d">{E(r["domain"])}</td>'
            f'<td><span class="chip" style="background:{color}1a;color:{color}">'
            f'{E(meta.get("icon","·"))} {E(c)}</span></td>'
            f'<td class="dt-bar"><div style="width:{pct:.1f}%;background:{color}"></div></td>'
            f'<td class="dt-n">{fmt(r["visits"])}</td>'
            f'<td class="dt-n">{r.get("share",0):.2f}%</td></tr>')
    return ('<table class="dt"><thead><tr><th>域名</th><th>分类</th>'
            '<th></th><th>访问量</th><th>占比</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def tag_cards(tags):
    if not tags:
        return '<div class="empty">标签规则未命中 —— 该主体的行为强度或多样性不足</div>'
    out = []
    for t in tags:
        out.append(
            f'<div class="tag" style="--tc:{t["color"]}">'
            f'<div class="tag-n">{E(t["name"])}</div>'
            f'<div class="tag-d">{E(t["desc"])}</div>'
            f'<div class="tag-e">{E(t["evidence"])}</div></div>')
    return f'<div class="tags">{"".join(out)}</div>'


def layer_note(layer_visit, total):
    """主动 / 系统 / 广告 三层占比说明。"""
    lv = layer_visit or {}
    a, s, ad = lv.get("ACT", 0), lv.get("SYS", 0), lv.get("AD", 0)
    t = max(total, 1)
    return (f'<div class="layer"><span class="li" style="--c:#1971c2">'
            f'<i style="background:#1971c2"></i>主动行为 {a/t*100:.1f}%</span>'
            f'<span class="li" style="--c:#adb5bd"><i style="background:#adb5bd"></i>'
            f'系统背景 {s/t*100:.1f}%</span>'
            f'<span class="li" style="--c:#ced4da"><i style="background:#ced4da"></i>'
            f'广告追踪 {ad/t*100:.1f}%</span></div>')


# ─────────────────────────────────────────────────────────────
def render_target(t, ctx):
    s = t["stats"]
    cats = ctx["categories"]
    blocks = ctx["time_blocks"]
    a = t.get("asset") or {}
    total = max(s["total"], 1)

    name = a.get("name") or "(无资产记录)"
    atype = a.get("asset_type") or "未知类型"
    os_ = a.get("os_name") or ""

    tags_html = tag_cards(t.get("tags") or [])
    trunc = s.get("truncated_windows", 0)

    return f"""
<section class="ent" id="ip-{E(t['ip']).replace('.','-')}">
  <div class="ent-hd">
    <div class="ent-id">
      <div class="ent-ip">{E(t['ip'])}</div>
      <div class="ent-nm">{E(name)}</div>
      <div class="ent-meta">
        <span class="chip c-gray">{E(atype)}</span>
        {'<span class="chip c-gray">' + E(os_) + '</span>' if os_ else ''}
        {'<span class="chip c-owner">owner: ' + E(a.get('owner')) + '</span>' if a.get('owner') else ''}
        {f'<span class="chip c-warn">⚠ {trunc} 个窗口被截断</span>' if trunc else ''}
      </div>
    </div>
    <div class="ent-kpi">
      {metric(fmt(s['total']), '总访问次数', f"{s['days']} 天")}
      {metric(fmt(s['daily_avg']), '日均访问')}
      {metric(fmt(s['domain_count']), '覆盖域名')}
      {metric(f"{s['peak_hour']:02d}:00", '活跃峰值时段')}
      {metric(f"{s['active_hours']}", '活跃小时数', f"/ {s['days']*24}")}
    </div>
  </div>

  <div class="sec-t">画像标签 <span class="sec-s">基于主动行为+时段节律的规则判定，每项附触发证据</span></div>
  {tags_html}

  <div class="grid2">
    <div class="card">
      <div class="card-t">24 小时活跃曲线</div>
      {hour_bars(s['by_hour'], blocks)}
      {layer_note(s['layer_visit'], total)}
    </div>
    <div class="card">
      <div class="card-t">时段分布</div>
      {block_bars(s['by_block'], total)}
      <div class="hint">
        工作日占 {s['workday_share']}%（{fmt(s['workday'])} 次） ·
        周末 {fmt(s['weekend'])} 次
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-t">星期 × 小时 行为热力图 <span class="sec-s">颜色越深访问越密集</span></div>
    {heatmap(s['wd_hour'])}
  </div>

  <div class="grid2">
    <div class="card">
      <div class="card-t">访问习惯构成 <span class="sec-s">仅统计主动行为</span></div>
      {cat_bars(s['cat_share'], s['cat_visit'], cats)}
    </div>
    <div class="card">
      <div class="card-t">各时段在干什么 <span class="sec-s">分类 × 时段堆叠</span></div>
      {cat_block_stack(s.get('cat_by_block') or {}, cats)}
    </div>
  </div>

  <div class="card">
    <div class="card-t">访问域名 TOP 20</div>
    {domain_table(s['top_domains'], cats, total)}
  </div>
</section>"""


def render(data):
    cats = data["categories"]
    blocks = data["time_blocks"]
    targets = sorted(data["targets"], key=lambda t: -t["stats"]["total"])
    nav = "".join(
        f'<a href="#ip-{E(t["ip"]).replace(".","-")}" class="nav-i">'
        f'<b>{E(t["ip"])}</b>'
        f'<span>{E((t.get("asset") or {}).get("name") or "未知设备")}</span></a>'
        for t in targets)
    secs = "".join(render_target(t, data) for t in targets)

    total_all = sum(t["stats"]["total"] for t in targets)
    all_dom = sum(t["stats"]["domain_count"] for t in targets)

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI-miniSOC · 上网行为画像报告</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#f5f6f8;color:#1f2937;line-height:1.6;font-size:14px}}
.wrap{{max-width:1280px;margin:0 auto;padding:28px 20px 80px}}
h1{{font-size:26px;font-weight:700;letter-spacing:-.4px}}
.sub-t{{color:#6b7280;margin-top:6px;font-size:13px}}
.hd{{padding:26px 0 18px;border-bottom:2px solid #e5e7eb;margin-bottom:22px}}
.badges{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}
.badge{{background:#fff;border:1px solid #e5e7eb;border-radius:6px;padding:5px 11px;
  font-size:12px;color:#4b5563}}
.badge b{{color:#111827}}
.nav{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:26px}}
.nav-i{{display:flex;flex-direction:column;background:#fff;border:1px solid #e5e7eb;
  border-radius:8px;padding:8px 13px;text-decoration:none;transition:.15s}}
.nav-i:hover{{border-color:#1971c2;transform:translateY(-1px)}}
.nav-i b{{font-size:12.5px;color:#111827;font-family:ui-monospace,monospace}}
.nav-i span{{font-size:11px;color:#6b7280;max-width:150px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}}

.ent{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:22px;margin-bottom:26px}}
.ent-hd{{display:flex;gap:22px;flex-wrap:wrap;justify-content:space-between;
  padding-bottom:18px;border-bottom:1px solid #f1f3f5;margin-bottom:6px}}
.ent-ip{{font-family:ui-monospace,monospace;font-size:19px;font-weight:700;color:#0b3d91}}
.ent-nm{{font-size:15px;color:#374151;margin-top:2px}}
.ent-meta{{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}}
.chip{{font-size:11px;padding:2px 8px;border-radius:4px;background:#f1f3f5;color:#4b5563}}
.c-gray{{background:#eef2f7;color:#475569}}
.c-owner{{background:#e7f5ff;color:#1864ab}}
.c-warn{{background:#fff4e6;color:#d9480f}}
.ent-kpi{{display:flex;gap:20px;flex-wrap:wrap}}
.metric{{text-align:right;min-width:78px}}
.mv{{font-size:21px;font-weight:700;line-height:1.15;font-family:ui-monospace,monospace}}
.ml{{font-size:11.5px;color:#6b7280}}
.sub{{font-size:10.5px;color:#9ca3af}}

.sec-t{{font-size:14px;font-weight:600;margin:20px 0 11px;color:#111827}}
.sec-s{{font-weight:400;color:#9ca3af;font-size:11.5px;margin-left:6px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
@media(max-width:980px){{.grid2{{grid-template-columns:1fr}}}}
.card{{background:#fff;border:1px solid #e9ecef;border-radius:10px;padding:16px;margin-bottom:16px}}
.card-t{{font-size:13px;font-weight:600;margin-bottom:13px;color:#374151}}
.hint{{font-size:11.5px;color:#6b7280;margin-top:10px}}
.empty{{color:#9ca3af;font-size:12.5px;padding:14px;background:#f8f9fa;border-radius:8px}}

/* 画像标签 */
.tags{{display:grid;grid-template-columns:repeat(auto-fill,minmax(196px,1fr));gap:10px}}
.tag{{border:1px solid var(--tc);border-left:4px solid var(--tc);border-radius:8px;
  padding:11px 13px;background:linear-gradient(90deg,color-mix(in srgb,var(--tc) 6%,#fff),#fff)}}
.tag-n{{font-size:14.5px;font-weight:700;color:var(--tc)}}
.tag-d{{font-size:11.5px;color:#4b5563;margin-top:3px}}
.tag-e{{font-size:10.5px;color:#9ca3af;margin-top:6px;font-family:ui-monospace,monospace}}

/* 24h 柱状 */
.hb{{display:flex;align-items:flex-end;gap:2px;height:132px}}
.hb-col{{flex:1;display:flex;flex-direction:column;align-items:center;height:100%}}
.hb-track{{flex:1;width:100%;display:flex;align-items:flex-end}}
.hb-fill{{width:100%;border-radius:2px 2px 0 0;min-height:2px}}
.hb-lbl{{font-size:9px;color:#9ca3af;margin-top:4px}}
.hb-col.peak .hb-lbl{{color:#d9480f;font-weight:700}}

/* 热力图 */
.hm{{overflow-x:auto}}
.hm-row{{display:flex;gap:2px;margin-bottom:2px;align-items:center}}
.hm-rl{{width:34px;font-size:10.5px;color:#6b7280;flex-shrink:0}}
.hm-c{{flex:1;height:16px;border-radius:2px;min-width:0}}
.hm-h{{height:auto;font-size:8.5px;color:#9ca3af;text-align:center;background:none}}

/* 时段条 */
.bb-row,.cb-row{{display:flex;align-items:center;gap:10px;margin-bottom:7px}}
.bb-name{{width:34px;font-size:12px;color:#4b5563;flex-shrink:0}}
.bb-track,.cb-track{{flex:1;height:16px;background:#f1f3f5;border-radius:3px;overflow:hidden}}
.bb-fill,.cb-fill{{height:100%;border-radius:3px}}
.bb-v,.cb-v{{width:96px;text-align:right;font-size:11.5px;color:#374151;
  font-family:ui-monospace,monospace;flex-shrink:0}}
.bb-p,.cb-p{{color:#9ca3af;margin-left:6px}}
.cb-name{{width:88px;font-size:11.5px;color:#4b5563;display:flex;align-items:center;
  gap:5px;flex-shrink:0}}
.cb-ico{{width:15px;height:15px;border-radius:3px;color:#fff;font-size:9px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}}

/* 堆叠条 */
.st-row{{display:flex;align-items:center;gap:9px;margin-bottom:8px}}
.st-b{{width:34px;font-size:11.5px;color:#4b5563;flex-shrink:0}}
.st-bar{{flex:1;height:19px;display:flex;border-radius:3px;overflow:hidden;background:#f1f3f5}}
.st-seg{{height:100%}}
.st-lg{{width:230px;font-size:10px;color:#6b7280;flex-shrink:0}}
.lg{{display:inline-flex;align-items:center;gap:3px;margin-right:7px}}
.lg i{{width:7px;height:7px;border-radius:2px;display:inline-block}}

/* 域名表 */
.dt{{width:100%;border-collapse:collapse;font-size:12px}}
.dt th{{text-align:left;padding:6px 8px;color:#6b7280;font-weight:500;font-size:11px;
  border-bottom:1px solid #e5e7eb}}
.dt td{{padding:5px 8px;border-bottom:1px solid #f8f9fa}}
.dt-d{{font-family:ui-monospace,monospace;font-size:11.5px;color:#1f2937;
  max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.dt-bar{{width:110px}}
.dt-bar div{{height:7px;border-radius:2px}}
.dt-n{{text-align:right;font-family:ui-monospace,monospace;color:#374151;white-space:nowrap}}
.chip{{font-size:10.5px;padding:2px 7px;border-radius:4px;white-space:nowrap}}

.layer{{display:flex;gap:16px;margin-top:12px;padding-top:11px;border-top:1px solid #f1f3f5;
  font-size:11.5px;color:#4b5563;flex-wrap:wrap}}
.li{{display:inline-flex;align-items:center;gap:5px}}
.li i{{width:9px;height:9px;border-radius:2px;display:inline-block}}

.foot{{margin-top:34px;padding:20px;background:#fff;border:1px solid #e5e7eb;
  border-radius:10px;font-size:12px;color:#4b5563}}
.foot h3{{font-size:13px;margin-bottom:9px;color:#111827}}
.foot ul{{margin:8px 0 0 18px}}
.foot li{{margin-bottom:5px}}
.foot code{{background:#f1f3f5;padding:1px 5px;border-radius:3px;font-size:11px}}
</style></head><body><div class="wrap">

<div class="hd">
  <h1>AI-miniSOC · 上网行为画像报告</h1>
  <div class="sub-t">基于路由器上网行为日志（Loki）的实体行为节律与兴趣构成分析</div>
  <div class="badges">
    <span class="badge">生成时间 <b>{E(data['generated_at'][:19].replace('T',' '))}</b></span>
    <span class="badge">数据源 <b>{E(data['loki'])}</b></span>
    <span class="badge">窗口 <b>最近 {E(data['days'])} 天</b></span>
    <span class="badge">主体 <b>{len(targets)} 个</b></span>
    <span class="badge">总访问 <b>{fmt(total_all)}</b> 次</span>
    <span class="badge">覆盖域名 <b>{fmt(all_dom)}</b> 个</span>
  </div>
</div>

<div class="nav">{nav}</div>
{secs}

<div class="foot">
  <h3>数据说明与已知偏差</h3>
  <ul>
    <li><b>采集方式</b>：所有时段统计均以 <code>Loki 原始日志时间戳</code> 逐条计数，
      未使用 <code>count_over_time</code> 聚合 —— 实测该聚合在 step=1h 下存在
      <b>窗口标签错位</b>与<b>边界重复计数</b>，会导致时段画像失真。</li>
    <li><b>时间窗</b>：Loki 保留期仅 7 天，本报告为最近 {E(data['days'])} 天，
      无法反映月度/季度级长期节律。</li>
    <li><b>行为分层</b>：访问被分为「主动行为 / 系统背景 / 广告追踪」三层。
      NTP 校时、DNS 查询、系统更新、遥测上报、广告 SDK 回传属于机器行为，
      已单独隔离；<b>画像标签只基于主动行为计算</b>。</li>
    <li><b>分类方法</b>：域名分类为关键词规则匹配，存在误判可能
      （如 <code>apple.com</code> 同时承载系统与个人服务）。路由器日志的
      「网站分组」字段恒为「所有网站」，无法提供现成分类。</li>
    <li><b>IP ≠ 人</b>：本报告主体是 IP/设备。同一 IP 背后可能有多个使用者
      （如家庭共享设备），需结合认证日志建立身份管道才能落到自然人。</li>
    <li><b>覆盖偏差</b>：画像丰富度直接取决于设备是否持续在线。
      离线设备的画像会显著偏薄，不能据此推断其使用者「行为简单」。</li>
  </ul>
</div>

</div></body></html>"""


def main():
    global TIME_BLOCKS
    data = json.load(open(DATA, encoding="utf-8"))
    TIME_BLOCKS = [(b["name"], b["label"], b["color"]) for b in data["time_blocks"]]
    # block_of / block_bars 依赖名称→颜色映射
    TIME_BLOCKS = [{"name": b["name"], "label": b["label"], "color": b["color"]}
                   for b in data["time_blocks"]]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    html_out = render(data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"已生成 {OUT}")
    print(f"  {len(data['targets'])} 个主体, {len(html_out):,} 字节")


TIME_BLOCKS = []

if __name__ == "__main__":
    main()
