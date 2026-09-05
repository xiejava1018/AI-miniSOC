#!/usr/bin/env python3
"""
AI-miniSOC 实体行为画像 POC · 数据采集

从 PostgreSQL(52张soc_表) + OpenSearch(wazuh-alerts) 采集指定 IP 的全维度数据，
输出 JSON 供报告生成使用。

用法:
    cd src/backend
    ../../venv/bin/python scripts/profile_poc_collect.py <ip1> [ip2 ...]
"""
import os
import sys
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

import httpx
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.config import settings

db = SessionLocal()

# ── OpenSearch 客户端 ──────────────────────────────────
OS_URL = settings.OPENSEARCH_URL.rstrip("/")
OS_AUTH = (settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD) if settings.OPENSEARCH_USER else None

# 认证类 Wazuh 规则（身份桥接原料）
AUTH_RULES = {
    "5715": ("sshd: authentication success", "success"),
    "5501": ("PAM: Login session opened", "success"),
    "5502": ("PAM: Login session closed", "close"),
    "5503": ("PAM: User login failed", "fail"),
    "5710": ("sshd: Attempt to login using a non-existent user", "fail"),
    "5760": ("sshd: authentication failed", "fail"),
    "5763": ("sshd: brute force", "attack"),
    "5551": ("PAM: Multiple failed logins", "attack"),
    "99904": ("sshd: Authentication failed from a malicious IP", "attack"),
}

# 从 full_log 提取用户名与源 IP
RE_PUBKEY = re.compile(r"Accepted \w+ for (\S+) from (\d+\.\d+\.\d+\.\d+)")
RE_PASSWD = re.compile(r"Accepted password for (\S+) from (\d+\.\d+\.\d+\.\d+)")
RE_FAILED = re.compile(r"Failed \w+ for (?:invalid user )?(\S+) from (\d+\.\d+\.\d+\.\d+)")
RE_SESSION_OPEN = re.compile(r"session opened for user (\S+)")
RE_SESSION_CLOSE = re.compile(r"session closed for user (\S+)")


def q(sql, **params):
    try:
        db.rollback()
        return [dict(r._mapping) for r in db.execute(text(sql), params).fetchall()]
    except Exception as e:
        db.rollback()
        print(f"  [SQL ERR] {str(e)[:160]}")
        return []


def os_search(query, size=0):
    try:
        with httpx.Client(timeout=60, verify=False) as c:
            r = c.post(f"{OS_URL}/wazuh-alerts-4.x-*/_search", auth=OS_AUTH,
                       json={"size": size, "query": query})
            if r.status_code != 200:
                return {}
            return r.json()
    except Exception as e:
        print(f"  [OS ERR] {str(e)[:160]}")
        return {}


def fmt_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


# ── 1. 身份档案 ────────────────────────────────────────
def collect_identity(ip):
    rows = q("""
        select id, name, asset_ip, mac_address, asset_type, criticality, owner,
               business_unit, os_name, os_version, network_segment, data_source,
               asset_status, asset_description, last_synced_at, created_at
        from soc_assets where asset_ip = :ip limit 1
    """, ip=ip)
    if not rows:
        return {"found": False}
    a = rows[0]
    a["id"] = str(a["id"])
    for k in ("last_synced_at", "created_at"):
        a[k] = fmt_dt(a[k])
    a["mac_address"] = str(a["mac_address"]) if a["mac_address"] else None
    a["found"] = True
    return a


# ── 2. 告警画像（PG 聚合表）────────────────────────────
def collect_alerts(ip, asset_id=None):
    out = {}
    tot = q("""
        select count(*) n, coalesce(sum(count),0) raw_n, min(first_seen) f, max(last_seen) l,
               count(distinct rule_id) rules
        from soc_alert_groups where agent_ip = :ip
    """, ip=ip)
    out["summary"] = tot[0] if tot else {}
    for k in ("f", "l"):
        if out["summary"].get(k):
            out["summary"][k] = fmt_dt(out["summary"][k])

    out["by_rule"] = q("""
        select rule_id, left(max(rule_description),70) as descr,
               count(*) groups, coalesce(sum(count),0) events,
               max(level_max) lvl
        from soc_alert_groups where agent_ip = :ip
        group by rule_id order by events desc limit 15
    """, ip=ip)

    out["by_level"] = q("""
        select level_max as lvl, count(*) groups, coalesce(sum(count),0) events
        from soc_alert_groups where agent_ip = :ip
        group by level_max order by lvl
    """, ip=ip)

    # AI 判决（去噪维度）
    out["ai_verdict"] = q("""
        select coalesce(ai_priority,'(null)') as priority,
               coalesce(cast(ai_is_noise as text),'(null)') as is_noise,
               count(*) groups, coalesce(sum(count),0) events
        from soc_alert_groups where agent_ip = :ip
        group by 1,2 order by events desc
    """, ip=ip)

    # 每日告警趋势
    out["daily"] = q("""
        select to_char(snapshot_at,'YYYY-MM-DD') d, sum(count) n
        from soc_alert_groups where agent_ip = :ip
        group by 1 order by 1
    """, ip=ip)

    # 时序：最近告警
    out["recent"] = q("""
        select rule_id, left(rule_description,60) descr, count, level_max lvl,
               first_seen, last_seen
        from soc_alert_groups where agent_ip = :ip
        order by last_seen desc limit 10
    """, ip=ip)
    for r in out["recent"]:
        for k in ("first_seen", "last_seen"):
            r[k] = fmt_dt(r[k])
    return out


# ── 3. 上网行为画像 ────────────────────────────────────
def collect_browsing(ip):
    out = {}
    # 基线（该 IP 历史访问过的全部域名 —— 行为富矿）
    base = q("""
        select count(*) domains, coalesce(sum(total_count),0) visits,
               min(first_seen) f, max(last_seen) l
        from soc_browsing_baseline where ip = :ip
    """, ip=ip)
    out["baseline_summary"] = base[0] if base else {}
    for k in ("f", "l"):
        if out["baseline_summary"].get(k):
            out["baseline_summary"][k] = fmt_dt(out["baseline_summary"][k])

    out["top_domains"] = q("""
        select domain, total_count visits, first_seen, last_seen
        from soc_browsing_baseline where ip = :ip
        order by total_count desc limit 30
    """, ip=ip)
    for r in out["top_domains"]:
        for k in ("first_seen", "last_seen"):
            r[k] = fmt_dt(r[k])

    # 异常事件
    ev = q("""
        select count(*) n, count(distinct domain) domains,
               min(created_at) f, max(created_at) l
        from soc_browsing_events where ip = :ip
    """, ip=ip)
    out["event_summary"] = ev[0] if ev else {}
    for k in ("f", "l"):
        if out["event_summary"].get(k):
            out["event_summary"][k] = fmt_dt(out["event_summary"][k])

    out["events"] = q("""
        select domain, score, severity, status, source_count, rule_hits,
               window_start, created_at
        from soc_browsing_events where ip = :ip
        order by created_at desc limit 30
    """, ip=ip)
    for r in out["events"]:
        for k in ("window_start", "created_at"):
            r[k] = fmt_dt(r[k])

    # 规则命中频次
    out["rule_hits"] = q("""
        select rh->>'rule' as rule, count(*) n
        from soc_browsing_events, jsonb_array_elements(rule_hits) rh
        where ip = :ip group by 1 order by n desc
    """, ip=ip)

    # 活跃时段（按检测小时聚合）
    out["hourly"] = q("""
        select extract(hour from created_at + interval '8 hour')::int as h,
               count(*) n
        from soc_browsing_events where ip = :ip
        group by 1 order by 1
    """, ip=ip)
    return out


# ── 4. 脆弱性与暴露面 ──────────────────────────────────
def collect_risk(ip, asset_id):
    out = {}
    if not asset_id:
        return out
    out["ports"] = q("""
        select port, protocol, state, service, version, last_seen
        from soc_asset_ports where asset_id = :a order by port
    """, a=asset_id)
    for r in out["ports"]:
        r["last_seen"] = fmt_dt(r["last_seen"])

    out["vuln_summary"] = q("""
        select av.status, count(*) n
        from soc_asset_vulnerabilities av where av.asset_id = :a group by 1
    """, a=asset_id)

    out["vulns"] = q("""
        select v.cve_id, v.severity, v.cvss_score, v.title, av.status, av.detected_at
        from soc_asset_vulnerabilities av
        join soc_vulnerabilities v on v.id = av.vulnerability_id
        where av.asset_id = :a
        order by coalesce(v.cvss_score,0) desc limit 20
    """, a=asset_id)
    for r in out["vulns"]:
        r["detected_at"] = fmt_dt(r["detected_at"])

    out["risk_history"] = q("""
        select risk_score, score_breakdown, scored_at
        from soc_asset_risk_history where asset_id = :a order by scored_at
    """, a=asset_id)
    for r in out["risk_history"]:
        r["scored_at"] = fmt_dt(r["scored_at"])

    out["incidents"] = q("""
        select i.id, i.title, i.severity, i.status, i.created_by, i.created_at
        from soc_asset_incidents ai join soc_incidents i on i.id = ai.incident_id
        where ai.asset_id = :a
    """, a=asset_id)
    for r in out["incidents"]:
        r["id"] = str(r["id"])
        r["created_at"] = fmt_dt(r["created_at"])
    return out


# ── 5. 身份映射（OpenSearch —— 用户画像的关键）──────────
def collect_identity_mapping(ip):
    out = {"available": False}

    # 5.1 谁登录了这个 IP（该 IP 是被登录的目标）
    inbound = []
    for rid, (descr, kind) in AUTH_RULES.items():
        res = os_search({
            "bool": {
                "must": [
                    {"term": {"rule.id": rid}},
                    {"term": {"agent.ip": ip}},
                ]
            }
        }, size=200)
        hits = res.get("hits", {}).get("hits", [])
        for h in hits:
            s = h.get("_source", {})
            log = s.get("full_log") or ""
            user, srcip = None, (s.get("data", {}) or {}).get("srcip")
            for rx in (RE_PUBKEY, RE_PASSWD, RE_FAILED):
                m = rx.search(log)
                if m:
                    user, srcip = m.group(1), m.group(2)
                    break
            if user is None:
                m = RE_SESSION_OPEN.search(log) or RE_SESSION_CLOSE.search(log)
                if m:
                    user = m.group(1)
            inbound.append({
                "rule": rid, "kind": kind, "user": user,
                "srcip": srcip, "ts": s.get("timestamp"),
                "log": log[:170],
            })
    out["inbound"] = inbound
    out["inbound_total"] = len(inbound)

    # 5.2 这个 IP 登录了谁（该 IP 是操作源）
    outbound = []
    for rid, (descr, kind) in AUTH_RULES.items():
        res = os_search({
            "bool": {
                "must": [
                    {"term": {"rule.id": rid}},
                    {"term": {"data.srcip": ip}},
                ]
            }
        }, size=200)
        for h in res.get("hits", {}).get("hits", []):
            s = h.get("_source", {})
            log = s.get("full_log") or ""
            user = None
            for rx in (RE_PUBKEY, RE_PASSWD, RE_FAILED):
                m = rx.search(log)
                if m:
                    user = m.group(1)
                    break
            if user is None:
                m = RE_SESSION_OPEN.search(log) or RE_SESSION_CLOSE.search(log)
                if m:
                    user = m.group(1)
            ag = s.get("agent", {}) or {}
            outbound.append({
                "rule": rid, "kind": kind, "user": user,
                "dstip": ag.get("ip"), "dstname": ag.get("name"),
                "ts": s.get("timestamp"), "log": log[:170],
            })
    out["outbound"] = outbound
    out["outbound_total"] = len(outbound)

    # 5.3 该 IP 在 OpenSearch 的告警总量（作为 agent）
    res = os_search({"term": {"agent.ip": ip}})
    out["os_alerts_as_agent"] = res.get("hits", {}).get("total", {}).get("value", 0)

    # 5.4 该 IP 作为源 IP 出现的告警量
    res = os_search({"term": {"data.srcip": ip}})
    out["os_alerts_as_srcip"] = res.get("hits", {}).get("total", {}).get("value", 0)

    # 5.5 最活跃的源 IP（针对 inbound）
    src_counter = Counter(x["srcip"] for x in inbound if x.get("srcip"))
    out["top_srcips"] = [{"ip": k, "n": v} for k, v in src_counter.most_common(10)]
    user_counter = Counter(x["user"] for x in inbound if x.get("user"))
    out["top_users"] = [{"user": k, "n": v} for k, v in user_counter.most_common(10)]

    # outbound 侧
    dst_counter = Counter(x["dstip"] for x in outbound if x.get("dstip"))
    out["top_dstips"] = [{"ip": k, "n": v} for k, v in dst_counter.most_common(10)]
    ouser_counter = Counter(x["user"] for x in outbound if x.get("user"))
    out["outbound_users"] = [{"user": k, "n": v} for k, v in ouser_counter.most_common(10)]

    out["available"] = True
    return out


def collect_one(ip):
    print(f"\n=== 采集 {ip} ===")
    data = {"ip": ip, "collected_at": datetime.now(timezone.utc).isoformat()}

    ident = collect_identity(ip)
    data["identity"] = ident
    asset_id = ident.get("id") if ident.get("found") else None
    print(f"  身份: {'命中 ' + str(ident.get('name')) if ident.get('found') else '未找到'}")

    alerts = collect_alerts(ip)
    data["alerts"] = alerts
    print(f"  告警: {alerts['summary'].get('n',0)} 组 / "
          f"{alerts['summary'].get('raw_n',0)} 条")

    br = collect_browsing(ip)
    data["browsing"] = br
    print(f"  基线域名: {br['baseline_summary'].get('domains',0)} / "
          f"异常事件: {br['event_summary'].get('n',0)}")

    data["risk"] = collect_risk(ip, asset_id)
    print(f"  端口: {len(data['risk'].get('ports',[]))} / "
          f"漏洞: {len(data['risk'].get('vulns',[]))}")

    ident_map = collect_identity_mapping(ip)
    data["identity_map"] = ident_map
    print(f"  身份映射: 入站 {ident_map.get('inbound_total',0)} / "
          f"出站 {ident_map.get('outbound_total',0)} / "
          f"OS告警(作为agent) {ident_map.get('os_alerts_as_agent',0)} / "
          f"OS告警(作为srcip) {ident_map.get('os_alerts_as_srcip',0)}")

    return data


def main():
    ips = sys.argv[1:] or ["192.168.0.102", "192.168.0.8"]
    result = {"targets": [collect_one(ip) for ip in ips]}
    out_path = os.path.join(parent_dir, "scripts", "profile_poc_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ 已写出 {out_path}")
    db.close()


if __name__ == "__main__":
    main()
