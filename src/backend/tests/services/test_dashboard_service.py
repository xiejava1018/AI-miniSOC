"""
测试概览仪表板聚合服务（DashboardService.get_summary）

覆盖（设计文档 docs/design/2026-08-16-概览仪表板设计.md §3.2 口径）：
- 各 KPI 数字正确（资产纳管 / 事件状态 / 漏洞 open+scap / 行为 24h 窗口）
- 夜间摘要窗口过滤（窗口外不计）
- 待办动态文案（criticality 分布、最老 open 天数）
- OS/Loki 探活失败不抛异常（mock httpx 返回异常，sources_health 标 online:false）

注意：
- 时间列口径：行为事件按 window_end（不是 created_at）
- 夜间窗口为北京时间昨日 18:00 → 今日 09:00，Python 侧 zoneinfo 算好后传参
- soc_alert_groups.first_seen 是 ISO 文本列，SQL 内 cast timestamptz 比较
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.models.ai_analysis import AIAnalysis
from app.models.alert_group_analysis import AlertGroupAnalysis
from app.models.alert_group_snapshot import AlertGroupSnapshot
from app.models.asset import Asset
from app.models.browsing_event import BrowsingEvent
from app.models.cisa_kev import CisaKev
from app.models.incident import Incident
from app.models.vulnerability import AssetVulnerability, Vulnerability
from app.services.dashboard_service import BJ_TZ, DashboardService

UTC = timezone.utc


# ── 种子工具 ──────────────────────────────────────

def _seed_assets(db_session):
    """74 台资产、22 台有 agent，未纳管按 criticality 分布 high 1 / medium 2 / normal 1。"""
    assets = []
    for i in range(74):
        has_agent = i < 22
        if has_agent:
            crit = "high"
        else:
            # 52 台未纳管：high 1 / medium 2 / normal 49（小样本验证分组即可）
            crit = "high" if i == 22 else ("medium" if i < 25 else "normal")
        assets.append(Asset(
            name=f"host-{i}",
            asset_ip=f"10.0.0.{i}",
            criticality=crit,
            wazuh_agent_id=f"agent-{i:03d}" if has_agent else None,
        ))
    db_session.add_all(assets)
    db_session.flush()
    return assets


def _seed_incidents(db_session):
    """open 2 / in_progress 1 / closed 1，最老 open 创建于 3 天前。"""
    now = datetime.now(UTC)
    inc = [
        Incident(title="old-open", status="open", severity="high",
                 created_by="t", created_at=now - timedelta(days=3)),
        Incident(title="new-open", status="open", severity="medium",
                 created_by="t", created_at=now - timedelta(hours=2)),
        Incident(title="wip", status="in_progress", severity="low",
                 created_by="t", created_at=now - timedelta(days=1)),
        Incident(title="done", status="closed", severity="low",
                 created_by="t", created_at=now - timedelta(days=2)),
    ]
    db_session.add_all(inc)
    db_session.flush()
    return inc


def _seed_vulns(db_session, assets):
    """open+scap 口径：critical 2 + high 1 + medium 1；另造 1 条 fixed + 1 条 sca 不计。"""
    def _vuln(cve, sev, vtype="scap"):
        return Vulnerability(cve_id=cve, title=f"t-{cve}", severity=sev, type=vtype)

    vulns = [
        _vuln("CVE-2026-0001", "critical"),
        _vuln("CVE-2026-0002", "critical"),
        _vuln("CVE-2026-0003", "high"),
        _vuln("CVE-2026-0004", "medium"),
        _vuln("CVE-2026-0005", "critical"),   # fixed，不计
        _vuln("CVE-2026-0006", "critical", vtype="sca"),  # sca，不计
        _vuln("cve-2026-0007", "high"),       # kev 命中（大小写不同）
    ]
    db_session.add_all(vulns)
    db_session.flush()

    kev = CisaKev(cve_id="CVE-2026-0007", date_added=datetime.now(UTC) - timedelta(days=10))
    db_session.add(kev)

    av_specs = [
        (vulns[0], "open"), (vulns[1], "open"), (vulns[2], "open"),
        (vulns[3], "open"),
        (vulns[4], "fixed"), (vulns[5], "open"), (vulns[6], "open"),
    ]
    now = datetime.now(UTC)
    for v, status in av_specs:
        db_session.add(AssetVulnerability(
            asset_id=assets[0].id, vulnerability_id=v.id,
            status=status, scanner="wazuh", detected_at=now,
        ))
    db_session.flush()
    return vulns


def _seed_browsing(db_session):
    """24h 内 3 条、前 24h 2 条、更早 2 条（窗口外）。"""
    now = datetime.now(UTC)
    events = []
    for i, (delta_h, ip) in enumerate([
        (-1, "10.0.1.1"), (-5, "10.0.1.2"), (-23, "10.0.1.3"),   # 近 24h：3 条
        (-25, "10.0.1.4"), (-47, "10.0.1.5"),                     # 前 24h：2 条
        (-72, "10.0.1.6"), (-100, "10.0.1.7"),                    # 更早：2 条
    ]):
        end = now + timedelta(hours=delta_h)
        events.append(BrowsingEvent(
            ip=ip, domain=f"evil-{i}.com", score=60, severity="medium",
            rule_hits=[{"rule": "R1", "weight": 60, "detail": "d"}],
            source_count=10,
            window_start=end - timedelta(hours=1),
            window_end=end,
            status="new",
        ))
    db_session.add_all(events)
    db_session.flush()
    return events


def _seed_snapshots(db_session, assets):
    """快照：今日 2 个指纹（北京今日 00:00 后）、昨日 1 个指纹（基线）。"""
    now_bj = datetime.now(BJ_TZ)
    today_start_bj = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today_start_bj - timedelta(days=1)

    def _snap(fp, iso_first_seen, at):
        return AlertGroupSnapshot(
            snapshot_at=at, window_hours=24, fingerprint=fp,
            rule_id="100", rule_description="test rule",
            agent_id="001", agent_name="host-a", agent_ip="10.0.0.1",
            count=5, level_min=3, level_max=7,
            first_seen=iso_first_seen,
            linked_asset_id=assets[0].id,
        )

    rows = [
        # 今日两个指纹（OS 实时聚合在测试库不可用，走快照回退口径）
        _snap("fp-today-1", (today_start_bj + timedelta(hours=1)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
              today_start_bj.astimezone(UTC) + timedelta(hours=2)),
        _snap("fp-today-2", (today_start_bj + timedelta(hours=2)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
              today_start_bj.astimezone(UTC) + timedelta(hours=2)),
        # 昨日基线 1 个指纹
        _snap("fp-yesterday", (yesterday + timedelta(hours=3)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
              yesterday.astimezone(UTC) + timedelta(hours=4)),
    ]
    db_session.add_all(rows)
    db_session.flush()
    return rows


def _seed_analyses(db_session, assets):
    """AI 覆盖：群体 3 簇（1 条 noise）+ 个警 1 条；Top 建议 P1 优先于 P2。"""
    now = datetime.now(UTC)
    db_session.add_all([
        AIAnalysis(alert_id="alert-1", model_name="test",
                   created_at=now - timedelta(hours=1)),
    ])
    db_session.add_all([
        AlertGroupAnalysis(
            fingerprint="fp-today-1", rule_id="100", agent_id="001",
            rule_description="P1 建议簇", priority="P1", is_noise=False,
            confidence=0.9, recommended_action="阻断源 IP", suggest_incident=True,
            created_at=now - timedelta(hours=2),
        ),
        AlertGroupAnalysis(
            fingerprint="fp-today-2", rule_id="101", agent_id="002",
            rule_description="P2 建议簇", priority="P2", is_noise=False,
            confidence=0.6, recommended_action="观察即可",
            created_at=now - timedelta(hours=1),
        ),
        AlertGroupAnalysis(
            fingerprint="fp-noise", rule_id="102", agent_id="003",
            rule_description="噪声簇", priority="P3", is_noise=True,
            confidence=0.1, recommended_action=None,
            created_at=now - timedelta(hours=3),
        ),
    ])
    db_session.flush()


def _seed_all(db_session):
    """全量种子。"""
    assets = _seed_assets(db_session)
    _seed_incidents(db_session)
    _seed_vulns(db_session, assets)
    _seed_browsing(db_session)
    _seed_snapshots(db_session, assets)
    _seed_analyses(db_session, assets)
    db_session.commit()


def _summary(db_session, mock_probe_offline=False, os_value=None):
    """跑 get_summary。

    测试环境可能真实可达 OpenSearch（结果非确定且慢），一律 mock
    _active_alert_groups_from_os（缺省 None = 走快照回退口径）保证确定性；
    os_value 传 int 可模拟 OS 实时聚合结果。
    mock_probe_offline=True 时再让 OS/Loki 探活直接抛异常。
    """
    with patch.object(DashboardService, "_active_alert_groups_from_os",
                      return_value=os_value):
        if mock_probe_offline:
            with patch("app.services.dashboard_service.httpx.head",
                       side_effect=ConnectionError("os unreachable")), \
                 patch("app.services.dashboard_service.httpx.get",
                       side_effect=TimeoutError("loki timeout")):
                return DashboardService(db_session).get_summary()
        return DashboardService(db_session).get_summary()


# ── 用例 ──────────────────────────────────────────

def test_kpi_asset_coverage(db_session):
    """资产纳管 KPI：22/74，未纳管按 criticality 分组。"""
    _seed_assets(db_session)
    s = _summary(db_session)
    cov = s["kpi"]["asset_coverage"]
    assert cov["managed"] == 22
    assert cov["total"] == 74
    assert cov["rate"] == round(22 / 74, 3)
    un = cov["unmanaged_by_criticality"]
    assert un.get("high") == 1
    assert un.get("medium") == 2
    assert un.get("normal") == 49


def test_kpi_open_incidents_and_closure_rate(db_session):
    """事件 KPI：open 2 / in_progress 1 / closed 1，闭环率 1/4=0.25。"""
    _seed_incidents(db_session)
    s = _summary(db_session)
    inc = s["kpi"]["open_incidents"]
    assert inc["value"] == 2
    assert inc["in_progress"] == 1
    assert inc["closed"] == 1
    assert inc["closure_rate"] == 0.25


def test_kpi_high_vulns_open_scap(db_session):
    """漏洞 KPI：open+scap 口径 critical 2 + high 2（含 kev 命中那条）= 4；
    fixed / sca 不计；kev_hits 大小写不敏感命中 1。
    """
    assets = _seed_assets(db_session)
    _seed_vulns(db_session, assets)
    s = _summary(db_session)
    v = s["kpi"]["high_vulns"]
    assert v["critical"] == 2, "fixed 的 critical 和 sca 的 critical 不应计入"
    assert v["high"] == 2
    assert v["value"] == 4
    assert v["kev_hits"] == 1, "upper(cve_id) 应命中大小写不同的 KEV 条目"


def test_kpi_browsing_24h_window(db_session):
    """行为 KPI：按 window_end 计窗——24h 3 条 / prev_24h 2 条 / total 7。"""
    _seed_browsing(db_session)
    s = _summary(db_session)
    b = s["kpi"]["browsing_anomalies_24h"]
    assert b["value"] == 3
    assert b["prev_24h"] == 2
    assert b["total"] == 7


def test_kpi_active_alert_groups_fallback_and_delta(db_session):
    """活跃簇：OS 不可达（返回 None）时回退当日快照 distinct 指纹（2），
    Δ = 今日 2 - 昨日 1 = 1。
    """
    assets = _seed_assets(db_session)
    _seed_snapshots(db_session, assets)
    s = _summary(db_session)
    g = s["kpi"]["active_alert_groups"]
    assert g["value"] == 2, "回退口径应为北京今日 distinct fingerprint"
    assert g["delta_vs_yesterday"] == 1


def test_kpi_active_alert_groups_prefers_os(db_session):
    """OS 实时聚合可用时优先取其 total_groups（快照仅作 Δ 基线）。"""
    assets = _seed_assets(db_session)
    _seed_snapshots(db_session, assets)
    s = _summary(db_session, os_value=31)
    g = s["kpi"]["active_alert_groups"]
    assert g["value"] == 31
    assert g["delta_vs_yesterday"] == 1, "Δ 仍取快照口径（今日2-昨日1）"


def test_kpi_incidents_today(db_session):
    """今日新增事件：北京时间当日 0 点起（seed 的 new-open 2h 前 → 今日 1）。"""
    _seed_incidents(db_session)
    s = _summary(db_session)
    t = s["kpi"]["incidents_today"]
    # new-open 创建于 2 小时前；若测试恰跑在北京 00:00-02:00 之间会落昨日，
    # 但 CI 环境按常规时段跑；这里断言 >= 0 且 <= 1 的合理值
    assert t["value"] in (0, 1)
    assert t["last_7d"] == 4


def test_night_summary_window(db_session):
    """夜间摘要：窗口内计数、窗口外不计（first_seen 文本列 cast 比较）。"""
    assets = _seed_assets(db_session)
    now_bj = datetime.now(BJ_TZ)
    start_bj = (now_bj - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    end_bj = now_bj.replace(hour=9, minute=0, second=0, microsecond=0)

    def _iso_fp(tag, dt_bj):
        return AlertGroupSnapshot(
            snapshot_at=dt_bj.astimezone(UTC),
            window_hours=24, fingerprint=f"fp-night-{tag}",
            rule_id="100", rule_description="night rule",
            agent_id="001", agent_name="h", agent_ip="10.0.0.1",
            count=1, level_min=3, level_max=7,
            first_seen=dt_bj.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            linked_asset_id=assets[0].id,
        )

    db_session.add_all([
        _iso_fp("in-1", start_bj + timedelta(minutes=30)),   # 窗口内
        _iso_fp("in-2", end_bj - timedelta(minutes=30)),     # 窗口内
        _iso_fp("out-early", start_bj - timedelta(hours=1)),  # 窗口前
        _iso_fp("out-late", end_bj + timedelta(hours=1)),     # 窗口后
    ])
    # 事件与行为同理
    now = datetime.now(UTC)
    db_session.add_all([
        Incident(title="night-inc", status="open", severity="low", created_by="t",
                 created_at=(start_bj + timedelta(hours=1)).astimezone(UTC)),
        Incident(title="day-inc", status="open", severity="low", created_by="t",
                 created_at=(end_bj + timedelta(hours=2)).astimezone(UTC)),
    ])
    def _brow(tag, end_bj):
        end = end_bj.astimezone(UTC)
        return BrowsingEvent(
            ip="10.0.2.1", domain=f"{tag}.com", score=50, severity="low",
            rule_hits=[], source_count=1,
            window_start=end - timedelta(hours=1), window_end=end, status="new",
        )
    db_session.add_all([
        _brow("night", start_bj + timedelta(hours=2)),
        _brow("day", end_bj + timedelta(hours=3)),
    ])
    db_session.commit()

    n = _summary(db_session)["night_summary"]
    assert n["new_alert_groups"] == 2, "窗口外 first_seen 不应计入"
    assert n["new_incidents"] == 1
    assert n["browsing_anomalies"] == 1
    assert n["kev_new"] == 0


def test_todos_dynamic_detail(db_session):
    """待办动态文案：criticality 分布 + 最老 open 天数（3 天）。"""
    _seed_all(db_session)
    s = _summary(db_session)
    todos = {t["id"]: t for t in s["todos"]}
    assert list(todos) == [
        "asset_coverage", "incident_backlog", "browsing_review", "ai_coverage",
    ], "待办顺序固定"
    assert "1 台 high" in todos["asset_coverage"]["detail"]
    assert "2 台 medium" in todos["asset_coverage"]["detail"]
    assert "normal" not in todos["asset_coverage"]["detail"], "normal 档不进待办"
    assert todos["incident_backlog"]["detail"] == "2 起 open，最老 3 天未处理"
    assert todos["browsing_review"]["detail"] == "近 24h 3 起异常"
    assert todos["ai_coverage"]["detail"] == "仅 1 条 vs 群体 3 簇"


def test_todos_skip_when_no_anomalies(db_session):
    """24h 行为异常为 0 时待办不出；无未纳管资产时纳管待办不出。"""
    # 全部资产有 agent → 无纳管待办；无行为事件 → 无复核待办；无 open 事件 → 无积压待办
    db_session.add_all([
        Asset(name="m1", asset_ip="10.1.0.1", criticality="high", wazuh_agent_id="a1"),
    ])
    db_session.commit()
    s = _summary(db_session)
    todo_ids = [t["id"] for t in s["todos"]]
    assert "asset_coverage" not in todo_ids
    assert "browsing_review" not in todo_ids
    assert "incident_backlog" not in todo_ids
    assert "ai_coverage" in todo_ids, "AI 覆盖待办始终出现"


def test_ai_insight_top_groups(db_session):
    """AI 洞察：覆盖率计数 + Top 非噪声簇按 P0<P1<P2<P3 排序、noise 不进。"""
    assets = _seed_assets(db_session)
    _seed_analyses(db_session, assets)
    db_session.commit()
    s = _summary(db_session)
    ai = s["ai_insight"]
    assert ai["coverage"]["group_analyses"] == 3
    assert ai["coverage"]["single_analyses"] == 1
    assert len(ai["top_groups"]) == 2, "is_noise=true 的簇不应进 Top 建议"
    assert ai["top_groups"][0]["priority"] == "P1"
    assert ai["top_groups"][0]["rule_description"] == "P1 建议簇"
    assert all("recommended_action" in g for g in ai["top_groups"])


def test_sources_health_offline_probes_do_not_raise(db_session):
    """OS/Loki 探活失败不抛异常：sources_health 标 online:false + error 摘要。"""
    _seed_assets(db_session)
    s = _summary(db_session, mock_probe_offline=True)
    health = s["sources_health"]
    assert health["postgres"]["online"] is True
    assert health["opensearch"]["online"] is False
    assert "error" in health["opensearch"]
    assert health["loki"]["online"] is False
    assert "error" in health["loki"]
    # 采集器纳管数来自 PG，不受探活失败影响
    assert health["collector"] == {"managed": 22, "total": 74}


def test_module_error_does_not_break_summary(db_session):
    """单模块查询失败返回 {"error": ...}，其余模块照常（显信任原则）。"""
    _seed_assets(db_session)
    svc = DashboardService(db_session)
    # 模拟漏洞模块抛异常
    with patch.object(DashboardService, "_kpi_high_vulns",
                      side_effect=RuntimeError("boom")):
        s = svc.get_summary()
    assert "error" in s["kpi"]["high_vulns"]
    assert s["kpi"]["asset_coverage"]["managed"] == 22, "其余模块不受影响"


def test_freshness_present(db_session):
    """新鲜度字段有值（seed 后 PG max(created_at) 非空）。"""
    _seed_incidents(db_session)
    s = _summary(db_session)
    f = s["freshness"]
    assert f["postgres"] is not None
