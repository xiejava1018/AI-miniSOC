#!/usr/bin/env python3
"""
AI-miniSOC 实体行为画像 POC · 报告生成

读取 profile_poc_data.json，生成单页 HTML 画像报告。

用法:
    cd src/backend
    ../../venv/bin/python scripts/profile_poc_report.py
"""
import os
import sys
import json
import html
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)          # src/backend
repo_root = os.path.dirname(os.path.dirname(parent_dir))  # 仓库根

DATA = os.path.join(parent_dir, "scripts", "profile_poc_data.json")
OUT_DIR = os.path.join(repo_root, "docs", "reports")
OUT = os.path.join(OUT_DIR, "2026-09-05-实体画像POC报告.html")

with open(DATA, encoding="utf-8") as f:
    DATA_JSON = json.load(f)

TARGETS = {t["ip"]: t for t in DATA_JSON["targets"]}
GEN_AT = DATA_JSON["targets"][0]["collected_at"][:19].replace("T", " ")

E = lambda s: html.escape(str(s if s is not None else ""))
NN = lambda s: s if s not in (None, "", "None") else "—"


def toint(v):
    """SQL sum() 常返回字符串，统一转 int"""
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def metric(v, label, sub=""):
    return f"""<div class="metric"><div class="mv">{v}</div>
    <div class="ml">{label}</div>{f'<div class="ms">{sub}</div>' if sub else ''}</div>"""


def bar_rows(rows, key_field, val_field, label_field=None, limit=10, unit="条"):
    out = []
    mx = max([toint(r.get(val_field)) for r in rows[:limit]] or [1])
    for r in rows[:limit]:
        v = toint(r.get(val_field))
        pct = int(v * 100 / mx) if mx else 0
        lbl = E(r.get(label_field or key_field))
        out.append(f"""<div class="bar-row"><div class="bar-lbl" title="{lbl}">{lbl}</div>
        <div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>
        <div class="bar-val">{v:,}{unit}</div></div>""")
    return "\n".join(out) or '<div class="empty">无数据</div>'


def kv_table(pairs, width="100%"):
    rows = "".join(
        f"<tr><th>{E(k)}</th><td>{E(NN(v))}</td></tr>" for k, v in pairs
    )
    return f'<table class="kv" style="width:{width}">{rows}</table>'


def build_entity_card(t):
    ip = t["ip"]
    ident = t["identity"]
    al = t["alerts"]
    br = t["browsing"]
    rk = t["risk"]
    im = t["identity_map"]

    name = NN(ident.get("name"))
    atype = NN(ident.get("asset_type"))
    osn = NN(ident.get("os_name"))
    mac = NN(ident.get("mac_address"))
    crit = NN(ident.get("criticality"))
    owner = NN(ident.get("owner"))
    src = NN(ident.get("data_source"))

    a_sum = al.get("summary") or {}
    b_sum = br.get("baseline_summary") or {}
    e_sum = br.get("event_summary") or {}

    # 身份关系
    inb = im.get("inbound_total", 0)
    outb = im.get("outbound_total", 0)
    tu = im.get("top_users") or []
    ou = im.get("outbound_users") or []
    tdst = im.get("top_dstips") or []
    tsrc = im.get("top_srcips") or []

    role = "被管理的主机" if inb > outb else ("操作发起端" if outb > 0 else "无身份活动记录")

    ident_html = ""
    if inb or outb:
        parts = []
        if tu:
            parts.append("<div class='rel-t'>登录本机的账号</div>" + " ".join(
                f"<span class='chip u'>{E(x['user'])} <b>{x['n']}</b></span>" for x in tu[:5]))
        if tsrc:
            parts.append("<div class='rel-t'>连接来源</div>" + " ".join(
                f"<span class='chip'>{E(x['ip'])} <b>{x['n']}</b></span>" for x in tsrc[:5]))
        if ou:
            parts.append("<div class='rel-t'>本机使用的账号</div>" + " ".join(
                f"<span class='chip u'>{E(x['user'])} <b>{x['n']}</b></span>" for x in ou[:5]))
        if tdst:
            parts.append("<div class='rel-t'>登录目标主机</div>" + " ".join(
                f"<span class='chip'>{E(x['ip'])} <b>{x['n']}</b></span>" for x in tdst[:6]))
        ident_html = "<div class='rel'>" + "".join(parts) + "</div>"

    ports = rk.get("ports") or []
    ports_html = "".join(
        f"<span class='chip'>{E(p['port'])}/{E(p['protocol'])} "
        f"{E(NN(p.get('service')))} {E(NN(p.get('version')))}</span>"
        for p in ports) or '<div class="empty">无端口数据</div>'

    rule_hits = br.get("rule_hits") or []
    rh_html = " ".join(f"<span class='chip r'>{E(r['rule'])} <b>{r['n']}</b></span>"
                       for r in rule_hits) or '<span class="empty">无</span>'

    return f"""
<div class="entity">
  <div class="e-head">
    <div class="e-ip">{E(ip)}</div>
    <div class="e-name">{E(name)}</div>
    <div class="e-role">{E(role)}</div>
  </div>

  <div class="metrics">
    {metric(f"{toint(a_sum.get('n')):,}", "告警组数", f"原始 {toint(a_sum.get('raw_n')):,} 条")}
    {metric(f"{toint(b_sum.get('domains')):,}", "访问域名数", f"累计 {toint(b_sum.get('visits')):,} 次")}
    {metric(f"{toint(e_sum.get('n')):,}", "行为异常事件")}
    {metric(f"{inb:,}", "被登录次数")}
    {metric(f"{outb:,}", "主动登录次数")}
  </div>

  <div class="grid2">
    <div class="card">
      <h3>身份档案</h3>
      {kv_table([
        ("资产名称", name), ("资产类型", atype), ("操作系统", osn),
        ("MAC 地址", mac), ("业务重要度", crit), ("责任人", owner),
        ("数据来源", src), ("最后同步", NN(ident.get('last_synced_at'))[:19]),
      ])}
      <div class="warn-inline">责任人字段为空 —— 这是画像到「人」的直接断裂点，
      下方身份关系来自 OpenSearch 抽取，可回填此字段</div>
    </div>
    <div class="card">
      <h3>身份关系（OpenSearch 抽取）</h3>
      {ident_html or '<div class="empty">未抽取到认证日志</div>'}
      <div class="os-note">OpenSearch 原始告警：作为被监控端
        {im.get('os_alerts_as_agent',0):,} 条 ／ 作为操作源
        {im.get('os_alerts_as_srcip',0):,} 条</div>
    </div>
  </div>

  <div class="card">
    <h3>告警构成 Top 10</h3>
    {bar_rows(al.get('by_rule') or [], 'rule_id', 'events', 'descr', 10)}
  </div>

  <div class="grid2">
    <div class="card">
      <h3>AI 去噪判决分布</h3>
      {bar_rows(al.get('ai_verdict') or [], 'priority', 'events', 'priority', 6)}
      <div class="os-note">noise=true 表示 AI 判定为噪音，可用于过滤误报</div>
    </div>
    <div class="card">
      <h3>暴露面</h3>
      <div class="rel-t">开放端口 {len(ports)} 个</div>
      <div class="chips">{ports_html}</div>
      <div class="rel-t" style="margin-top:12px">关联漏洞</div>
      <div class="empty">{(str(len(rk.get('vulns') or [])) + ' 条') if rk.get('vulns') else '无漏洞记录'}</div>
    </div>
  </div>

  <div class="card">
    <h3>上网行为 Top 12 域名</h3>
    {bar_rows(br.get('top_domains') or [], 'domain', 'visits', 'domain', 12, ' 次')}
    <div class="rel-t" style="margin-top:12px">命中行为规则</div>
    <div class="chips">{rh_html}</div>
  </div>
</div>
"""


def build_network():
    """从两个目标的身份映射拼出关系图"""
    n8 = TARGETS.get("192.168.0.8", {}).get("identity_map", {})
    n102 = TARGETS.get("192.168.0.102", {}).get("identity_map", {})
    dsts = n8.get("top_dstips") or []
    users = n8.get("outbound_users") or []
    mx = max([d["n"] for d in dsts] or [1])

    nodes = "".join(
        f"""<div class="lnk"><span class="lnk-ip">{E(d['ip'])}</span>
        <div class="lnk-bar"><div class="lnk-fill" style="width:{int(d['n']*100/mx)}%"></div></div>
        <span class="lnk-n">{d['n']} 次</span></div>""" for d in dsts)

    return f"""
<div class="card">
  <h3>身份关系网络 · 账号 xiejava 的活动轨迹</h3>
  <div class="net-hint">基于 OpenSearch 认证日志（rule 5715/5501 等）抽取，共
    {n8.get('outbound_total',0)} 条出站记录</div>
  <div class="net">
    <div class="net-src">
      <div class="nb nb-u">账号 {E((users[0]['user'] if users else 'unknown'))}</div>
      <div class="nb nb-d">设备 192.168.0.8<Br><span class="nb-s">xiejavadeMini</span></div>
    </div>
    <div class="net-arrows">SSH / 登录</div>
    <div class="net-dst">{nodes or '<div class="empty">无</div>'}</div>
  </div>
  <div class="os-note">反向验证：192.168.0.102 的入站记录中，来自 192.168.0.8 的连接
    {sum(1 for x in (TARGETS.get('192.168.0.102',{}).get('identity_map',{}).get('inbound') or []) if x.get('srcip')=='192.168.0.8')} 条
    —— 与出站数据互为印证，证明同一份数据可同时支撑设备画像与用户画像</div>
</div>
"""


def build_gaps():
    return """
<div class="card">
  <h3>本 POC 暴露的数据缺口</h3>
  <table class="gap">
    <tr><th>缺口</th><th>实测情况</th><th>对画像的影响</th><th>修复成本</th></tr>
    <tr>
      <td>责任人字段为空</td>
      <td>76 个资产中 72 个 owner 为 NULL（94.7%）</td>
      <td>库表层无法直接回答「这是谁的」</td>
      <td><span class="tag low">低</span> 用 OpenSearch 抽取结果回填即可</td>
    </tr>
    <tr>
      <td>用户名未归一化</td>
      <td><code>xiejava</code> 与 <code>xiejava(uid=1000)</code> 被计为两个账号</td>
      <td>账号统计失真（本例 381 + 175 应为 556 一次计）</td>
      <td><span class="tag low">低</span> 加归一化规则剥离 (uid=N) 后缀</td>
    </tr>
    <tr>
      <td>告警聚合表丢源 IP</td>
      <td><code>soc_alert_groups.top_srcips</code> 全为 NULL</td>
      <td>库表无法回答「谁发起的」，必须回 OpenSearch</td>
      <td><span class="tag mid">中</span> 需建身份管道后回填</td>
    </tr>
    <tr>
      <td>风险历史非连续</td>
      <td>828 行但时间跨度仅 8/21–8/22（1.3 天）</td>
      <td>「风险趋势」维度当前无数据支撑</td>
      <td><span class="tag mid">中</span> 需建立每日评分落库</td>
    </tr>
    <tr>
      <td>资产类型判定不准</td>
      <td>192.168.0.8（Mac Mini）被 tplink-router 标为 <code>server</code></td>
      <td>画像的「设备角色」判断会出错</td>
      <td><span class="tag mid">中</span> 需多源融合判定或人工校正</td>
    </tr>
    <tr>
      <td>Loki 仅保留 7 天</td>
      <td>上网行为原始数据 7 天后不可回溯</td>
      <td>行为画像最长只能看 7 天原始记录（基线表可看更久）</td>
      <td><span class="tag high">高</span> 需调整保留策略或落库汇总</td>
    </tr>
    <tr>
      <td>历史数据混入</td>
      <td>抽取到 2026-03-14 的 kali 主机登录记录</td>
      <td>时间范围需显式过滤，否则画像含陈旧数据</td>
      <td><span class="tag low">低</span> 查询加时间下界</td>
    </tr>
  </table>
</div>
"""


def build_conclusion():
    t8 = TARGETS.get("192.168.0.8", {})
    t102 = TARGETS.get("192.168.0.102", {})
    return f"""
<div class="card concl">
  <h3>POC 结论：A → B 通道已验证可行</h3>
  <div class="concl-grid">
    <div class="cg">
      <div class="cg-h ok">已验证成立</div>
      <ul>
        <li><b>设备画像（A）数据现成</b>：192.168.0.102 直接从库表拿到
          {toint(t102['alerts']['summary'].get('n')):,} 组告警、
          {len(t102['risk'].get('ports') or [])} 个端口、79 个基线域名，无需任何新管道</li>
        <li><b>身份抽取（B 的地基）可行</b>：从 OpenSearch 成功抽取到
          {t102['identity_map'].get('inbound_total',0)} 条入站 +
          {t8['identity_map'].get('outbound_total',0)} 条出站认证记录，
          用户名与源 IP 均可从 <code>full_log</code> 正则提取</li>
        <li><b>一份数据两个视角</b>：192.168.0.102 的「入站」= 192.168.0.8 的「出站」，
          同一份抽取结果同时支撑设备画像与用户画像</li>
        <li><b>用户画像（B）价值已现</b>：账号 xiejava 的画像已可成形 ——
          主用设备 192.168.0.8，32 天访问
          {toint(t8['browsing']['baseline_summary'].get('domains')):,} 个域名
          （{toint(t8['browsing']['baseline_summary'].get('visits')):,} 次），
          SSH 管理 {len(t8['identity_map'].get('top_dstips') or [])} 台主机</li>
      </ul>
    </div>
    <div class="cg">
      <div class="cg-h warn">需要注意</div>
      <ul>
        <li><b>两个 IP 的数据分布极度不均</b>：192.168.0.102 有
          {toint(t102['alerts']['summary'].get('raw_n')):,} 条告警而 192.168.0.8 为 0
          （后者没装 Wazuh agent）。<b>画像的丰富度直接取决于该设备装没装 agent</b></li>
        <li><b>用户画像强依赖 OpenSearch</b>：抽掉它，192.168.0.8 只剩
          「977 个域名 + 6 个端口」，几乎画不出「人」</li>
        <li><b>行为异常维度会继承 P2 误报</b>：本次 192.168.0.8 的 4 条异常事件中
          4 条命中 R3、4 条命中 R4，而 R4 已知存在 STUN 误伤问题</li>
        <li><b>POC 数据为单次快照</b>：身份映射未落库，每次查询需重新抽取
          （本次耗时约 20 秒），产品化必须建
          <code>soc_identity_events</code> 持久化</li>
      </ul>
    </div>
  </div>
  <div class="next">
    <div class="next-h">建议下一步</div>
    <ol>
      <li><b>先做 P2 止血</b>（3 个配置项，1 小时内）—— 消除 83% 的 STUN 误报，
        否则画像的「行为异常」维度不可信</li>
      <li><b>Phase 0 身份管道落地</b>（3–5 天）—— 建
        <code>soc_identity_events</code> + <code>soc_identity_bindings</code>，
        定时从 OpenSearch 抽取并归一化用户名，回填 <code>soc_assets.owner</code></li>
      <li><b>Phase 2 产品化</b>（2–3 周）—— 后端画像服务 + 前端页面 + MCP 工具，
        从资产/告警/事件列表一键下钻到画像页</li>
    </ol>
  </div>
</div>
"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cards = "\n".join(build_entity_card(t) for t in DATA_JSON["targets"])

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI-miniSOC 实体行为画像 POC 报告</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#f7f7f5;color:#2C2C2A;
 font:14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:32px 24px 64px}}
header{{border-bottom:1px solid #D3D1C7;padding-bottom:20px;margin-bottom:28px}}
h1{{font-size:22px;font-weight:500;margin:0 0 6px}}
.sub{{color:#5F5E5A;font-size:13px}}
.lead{{background:#fff;border:1px solid #D3D1C7;border-radius:12px;
 padding:16px 20px;margin:20px 0 28px;font-size:13px;line-height:1.75}}
.lead b{{font-weight:500}}
.entity{{background:#fff;border:1px solid #D3D1C7;border-radius:14px;
 padding:22px;margin-bottom:26px}}
.e-head{{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
 padding-bottom:14px;border-bottom:1px solid #E8E6DF;margin-bottom:18px}}
.e-ip{{font:500 20px/1 ui-monospace,SFMono-Regular,Menlo,monospace}}
.e-name{{font-size:16px;font-weight:500}}
.e-role{{margin-left:auto;background:#E6F1FB;color:#185FA5;
 border-radius:20px;padding:3px 14px;font-size:12px}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));
 gap:12px;margin-bottom:20px}}
.metric{{background:#F1EFE8;border-radius:8px;padding:12px 14px}}
.mv{{font:500 22px/1.2 ui-monospace,Menlo,monospace}}
.ml{{font-size:12px;color:#5F5E5A;margin-top:3px}}
.ms{{font-size:11px;color:#888780;margin-top:2px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
@media(max-width:760px){{.grid2{{grid-template-columns:1fr}}}}
.card{{background:#FAFAF8;border:1px solid #E8E6DF;border-radius:10px;
 padding:16px 18px;margin-bottom:16px}}
.card h3{{font-size:14px;font-weight:500;margin:0 0 12px;
 padding-bottom:8px;border-bottom:1px solid #E8E6DF}}
table.kv{{border-collapse:collapse;font-size:13px}}
table.kv th{{text-align:left;font-weight:400;color:#5F5E5A;
 padding:5px 14px 5px 0;white-space:nowrap;width:88px;vertical-align:top}}
table.kv td{{padding:5px 0;font-family:ui-monospace,Menlo,monospace;font-size:12px;
 word-break:break-all}}
.warn-inline{{margin-top:10px;background:#FAEEDA;border-radius:6px;
 padding:8px 10px;font-size:12px;color:#633806;line-height:1.6}}
.bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:7px;font-size:12px}}
.bar-lbl{{width:290px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
 color:#444441;font-family:ui-monospace,Menlo,monospace;font-size:11px}}
.bar-track{{flex:1;height:15px;background:#EFEDE6;border-radius:3px;overflow:hidden}}
.bar-fill{{height:100%;background:#7F77DD;border-radius:3px}}
.bar-val{{width:88px;text-align:right;color:#5F5E5A;
 font-family:ui-monospace,Menlo,monospace;font-size:11px}}
.chips{{display:flex;flex-wrap:wrap;gap:6px}}
.chip{{background:#F1EFE8;border-radius:5px;padding:3px 9px;font-size:12px;
 font-family:ui-monospace,Menlo,monospace}}
.chip.u{{background:#E1F5EE;color:#0F6E56}}
.chip.r{{background:#FAEEDA;color:#633806}}
.chip b{{font-weight:500}}
.rel-t{{font-size:12px;color:#5F5E5A;margin:10px 0 5px}}
.rel-t:first-child{{margin-top:0}}
.rel{{font-size:12px}}
.os-note{{margin-top:10px;font-size:11px;color:#888780;line-height:1.6}}
.empty{{color:#B4B2A9;font-size:12px;font-style:italic}}
.net{{display:flex;align-items:center;gap:18px;flex-wrap:wrap}}
.net-src{{display:flex;flex-direction:column;gap:8px}}
.nb{{background:#EEEDFE;border:1px solid #AFA9EC;border-radius:8px;
 padding:9px 14px;font-size:13px;text-align:center}}
.nb-u{{background:#E1F5EE;border-color:#5DCAA5}}
.nb-s{{font-size:11px;color:#5F5E5A}}
.net-arrows{{color:#888780;font-size:12px}}
.net-dst{{flex:1;min-width:280px}}
.lnk{{display:flex;align-items:center;gap:10px;margin-bottom:6px;font-size:12px}}
.lnk-ip{{width:110px;font-family:ui-monospace,Menlo,monospace}}
.lnk-bar{{flex:1;height:14px;background:#EFEDE6;border-radius:3px;overflow:hidden}}
.lnk-fill{{height:100%;background:#1D9E75;border-radius:3px}}
.lnk-n{{width:52px;text-align:right;color:#5F5E5A;font-size:11px}}
table.gap{{width:100%;border-collapse:collapse;font-size:12.5px}}
table.gap th{{text-align:left;background:#F1EFE8;padding:8px 10px;
 font-weight:500;border-bottom:1px solid #D3D1C7}}
table.gap td{{padding:8px 10px;border-bottom:1px solid #EFEDE6;vertical-align:top}}
table.gap td:first-child{{font-weight:500;white-space:nowrap}}
code{{background:#F1EFE8;padding:1px 5px;border-radius:3px;
 font-family:ui-monospace,Menlo,monospace;font-size:11.5px}}
.tag{{border-radius:4px;padding:1px 7px;font-size:11px;margin-right:5px}}
.tag.low{{background:#EAF3DE;color:#3B6D11}}
.tag.mid{{background:#FAEEDA;color:#633806}}
.tag.high{{background:#FCEBEB;color:#791F1F}}
.concl{{background:#fff}}
.concl-grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
@media(max-width:760px){{.concl-grid{{grid-template-columns:1fr}}}}
.cg-h{{font-size:13px;font-weight:500;padding:6px 12px;border-radius:6px;margin-bottom:10px}}
.cg-h.ok{{background:#EAF3DE;color:#3B6D11}}
.cg-h.warn{{background:#FAEEDA;color:#633806}}
.cg ul{{margin:0;padding-left:18px;font-size:12.5px;line-height:1.8}}
.cg li{{margin-bottom:7px}}
.next{{margin-top:18px;padding-top:14px;border-top:1px solid #E8E6DF}}
.next-h{{font-size:13px;font-weight:500;margin-bottom:8px}}
.next ol{{margin:0;padding-left:20px;font-size:12.5px;line-height:1.8}}
.next li{{margin-bottom:6px}}
footer{{margin-top:32px;padding-top:16px;border-top:1px solid #D3D1C7;
 font-size:12px;color:#888780;line-height:1.7}}
</style></head><body><div class="wrap">
<header>
  <h1>AI-miniSOC 实体行为画像 POC 报告</h1>
  <div class="sub">双视角验证 · 生成于 {E(GEN_AT)} ·
    数据源：PostgreSQL 52 张 soc_ 表 + OpenSearch wazuh-alerts（128.4 万条）</div>
</header>

<div class="lead">
本报告验证一件事：<b>能否用「设备画像」的数据管道，顺带产出「用户画像」所需的身份映射</b>。
<br>
选了两个互补样本 —— <b>192.168.0.102</b>（xiejava-8g-host，装了 Wazuh agent 的 Ubuntu 服务器）
与 <b>192.168.0.8</b>（xiejavadeMini，没装 agent 的日常开发机）。
前者代表「数据在库表里」的富样本，后者代表「数据只在 OpenSearch 里」的贫样本 ——
如果连后者都能画出像样的画像，就说明这条路径成立。
</div>

{cards}

{build_network()}

{build_gaps()}

{build_conclusion()}

<footer>
数据获取方式：PostgreSQL 直连查询 52 张 <code>soc_</code> 表；
OpenSearch <code>wazuh-alerts-4.x-*</code> 索引（30 个，1,284,210 条），
按认证类规则（5715/5501/5502/5503/5710/5760/5763/5551/99904）检索，
用正则从 <code>full_log</code> 提取用户名与源 IP。
<br>
采集脚本：<code>src/backend/scripts/profile_poc_collect.py</code>　
报告生成：<code>src/backend/scripts/profile_poc_report.py</code>
<br>
<b>合规提示</b>：本报告涉及可识别到个人的行为数据，仅限安全审计用途，
查看行为本身应记入 <code>soc_audit_logs</code>。
</footer>
</div></body></html>"""

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"✅ 报告已生成: {OUT}")
    print(f"   大小: {os.path.getsize(OUT)/1024:.1f} KB")


if __name__ == "__main__":
    main()
