"""
F1.1 资产风险评分规则引擎单元测试

覆盖（PRD v1.2.1 §八-C / §4.5）：
- 四维度齐备评分 + breakdown 可解释结构
- data_gap 半权降级 + 重归一化
- 四维全缺 → None（N/A，不误导为 0 分）
- 规则外置：save_rules 权重校验 / 深合并
- 历史落库 + 上升检测
- GLM 不可用 → 规则化文案降级
- 离线资产不参与告警密度计分（§4.5）
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Asset, AssetPort, AlertGroupAnalysis
from app.models.asset_risk import AssetRiskHistory
from app.models.vulnerability import Vulnerability, AssetVulnerability
from app.services.asset_risk import AssetRiskService, DEFAULT_RULES


def _now():
    return datetime.now(timezone.utc)


def _make_asset(**kw) -> Asset:
    defaults = dict(
        network_segment="3F", asset_ip="192.168.0.10", asset_status="online",
        asset_type="server", criticality="high", data_classification="internal",
        exposure_level="internal", os_name="Ubuntu", os_version="22.04",
        name="test-server",
    )
    defaults.update(kw)
    return Asset(**defaults)


# ---------------------------------------------------------------------------
# 维度评分
# ---------------------------------------------------------------------------

class TestExposure:
    def test_high_risk_ports_scored(self, db_session):
        a = _make_asset()
        db_session.add(a)
        db_session.flush()
        for port in (3389, 445):
            db_session.add(AssetPort(asset_id=a.id, asset_ip=a.asset_ip, port=port, protocol="tcp", state="open"))
        db_session.commit()
        svc = AssetRiskService(db_session)
        d = svc._score_exposure(a, svc.load_rules(force=True))
        assert d["score"] == 50  # 2 × 25
        assert d["data_gap"] is False
        assert "3389" in d["reasons"][0]

    def test_public_bonus_capped(self, db_session):
        a = _make_asset(exposure_level="public")
        db_session.add(a)
        db_session.flush()
        for port in (22, 23, 135, 445, 3389):  # 5 个已满 100
            db_session.add(AssetPort(asset_id=a.id, asset_ip=a.asset_ip, port=port, protocol="tcp", state="open"))
        db_session.commit()
        svc = AssetRiskService(db_session)
        d = svc._score_exposure(a, svc.load_rules(force=True))
        assert d["score"] == 100  # 封顶

    def test_no_port_records_is_data_gap(self, db_session):
        a = _make_asset()
        db_session.add(a)
        db_session.commit()
        svc = AssetRiskService(db_session)
        d = svc._score_exposure(a, svc.load_rules(force=True))
        assert d["data_gap"] is True
        assert d["score"] == 0


class TestHealth:
    def test_vulnerability_consumption(self, db_session):
        """系统健康度消费漏洞级评分（VulnerabilityAIService 口径，PRD v1.2.1 关系节）"""
        a = _make_asset(criticality="critical")
        db_session.add(a)
        db_session.flush()
        v = Vulnerability(cve_id="CVE-2026-9999", title="test", severity="critical", cvss_score=9.8, has_exploit=True)
        db_session.add(v)
        db_session.flush()
        db_session.add(AssetVulnerability(asset_id=a.id, vulnerability_id=v.id, scanner="wazuh", status="open"))
        db_session.commit()

        svc = AssetRiskService(db_session)
        d = svc._score_health(a, svc.load_rules(force=True))
        # 漏洞级评分被真实消费（62.45 = VulnerabilityAIService 口径输出），量级合理
        assert d["score"] > 60
        assert d["data_gap"] is False
        assert d["inputs"]["max_vuln_score"] > 55

    def test_fixed_vulns_not_counted_but_scanned(self, db_session):
        a = _make_asset()
        db_session.add(a)
        db_session.flush()
        v = Vulnerability(cve_id="CVE-2026-8888", title="t", severity="high", cvss_score=7.0)
        db_session.add(v)
        db_session.flush()
        db_session.add(AssetVulnerability(asset_id=a.id, vulnerability_id=v.id, scanner="wazuh", status="fixed"))
        db_session.commit()
        svc = AssetRiskService(db_session)
        d = svc._score_health(a, svc.load_rules(force=True))
        assert d["score"] == 0  # 已扫描且无活跃漏洞
        assert "无未修复漏洞" in " ".join(d["reasons"])

    def test_eol_fallback_when_no_scan(self, db_session):
        a = _make_asset(os_name="CentOS", os_version="7.9")
        db_session.add(a)
        db_session.commit()
        svc = AssetRiskService(db_session)
        d = svc._score_health(a, svc.load_rules(force=True))
        assert d["score"] == 100
        assert d["data_gap"] is True  # 无扫描数据 → 半权

    def test_all_missing_is_gap(self, db_session):
        a = _make_asset(os_name=None, os_version=None)
        db_session.add(a)
        db_session.commit()
        svc = AssetRiskService(db_session)
        d = svc._score_health(a, svc.load_rules(force=True))
        assert d["data_gap"] is True and d["score"] == 0


class TestAlerts:
    def test_priority_weighting(self, db_session):
        a = _make_asset()
        db_session.add(a)
        db_session.flush()
        for i, prio in enumerate(["P0", "P1", "P2", "P2", "P3"]):
            db_session.add(AlertGroupAnalysis(
                fingerprint=f"fp{i}", priority=prio, linked_asset_id=a.id,
            ))
        db_session.commit()
        svc = AssetRiskService(db_session)
        d = svc._score_alerts(a, svc.load_rules(force=True), _now())
        # 20+20+8+8+2 = 58
        assert d["score"] == 58

    def test_offline_asset_not_counted(self, db_session):
        """§4.5：离线资产告警密度不参与计分（半权 data_gap）"""
        a = _make_asset(asset_status="offline")
        db_session.add(a)
        db_session.flush()
        for i in range(5):
            db_session.add(AlertGroupAnalysis(fingerprint=f"x{i}", priority="P0", linked_asset_id=a.id))
        db_session.commit()
        svc = AssetRiskService(db_session)
        d = svc._score_alerts(a, svc.load_rules(force=True), _now())
        assert d["score"] == 0
        assert d["data_gap"] is True


# ---------------------------------------------------------------------------
# 聚合与降级
# ---------------------------------------------------------------------------

class TestAggregation:
    def test_full_data_score_in_range(self, db_session):
        a = _make_asset()
        db_session.add(a)
        db_session.flush()
        db_session.add(AssetPort(asset_id=a.id, asset_ip=a.asset_ip, port=445, protocol="tcp", state="open"))
        v = Vulnerability(cve_id="CVE-2026-1", title="t", severity="high", cvss_score=8.0)
        db_session.add(v)
        db_session.flush()
        db_session.add(AssetVulnerability(asset_id=a.id, vulnerability_id=v.id, scanner="wazuh", status="open"))
        db_session.add(AlertGroupAnalysis(fingerprint="f1", priority="P1", linked_asset_id=a.id))
        db_session.commit()

        svc = AssetRiskService(db_session)
        b = svc.score_asset(a, svc.load_rules(force=True))
        assert b is not None
        assert 0 <= b["total"] <= 100
        dims = b["dimensions"]
        assert set(dims.keys()) == {"exposure", "health", "alerts", "importance"}
        # 可解释性：每个维度有 score/weight/reasons
        for name, d in dims.items():
            assert "score" in d and "weight" in d and "reasons" in d and "data_gap" in d

    def test_data_gap_renormalized(self, db_session):
        """缺失维度半权 + 重归一化：importance=70 (criticality high)，其余 gap=0"""
        a = _make_asset(asset_status="online", os_name=None, criticality="high")
        db_session.add(a)
        db_session.commit()
        svc = AssetRiskService(db_session)
        b = svc.score_asset(a, svc.load_rules(force=True))
        # importance=70 w=0.2；其余三维度 gap：0.3*0.5 + 0.25*0.5 + 0.25*0.5（alerts 在线但无记录→非gap，score0）
        # exposure gap(0.15) health gap(0.125) alerts 非 gap(0.25, score=0) importance(0.2, 70)
        # total = 70*0.2 / (0.15+0.125+0.25+0.2) = 14 / 0.725 ≈ 19
        assert b["total"] == round(14 / 0.725)
        assert b["dimensions"]["exposure"]["data_gap"] is True
        assert b["dimensions"]["alerts"]["data_gap"] is False

    def test_all_gap_returns_none(self, db_session):
        """证据维度全缺 → None（N/A），不显示低分误导"""
        a = _make_asset(asset_status="offline", os_name=None, os_version=None)
        db_session.add(a)
        db_session.commit()
        svc = AssetRiskService(db_session)
        assert svc.score_asset(a, svc.load_rules(force=True)) is None


class TestRules:
    def test_save_rules_weight_validation(self, db_session):
        svc = AssetRiskService(db_session)
        with pytest.raises(ValueError, match="权重"):
            svc.save_rules({"weights": {"exposure": 0.5, "health": 0.5, "alerts": 0.5, "importance": 0.5}})

    def test_save_and_load_merge(self, db_session):
        svc = AssetRiskService(db_session)
        merged = svc.save_rules({"exposure": {"per_port_score": 30}})
        assert merged["exposure"]["per_port_score"] == 30
        assert merged["exposure"]["high_risk_ports"] == DEFAULT_RULES["exposure"]["high_risk_ports"]  # 深合并保留默认
        # 强制刷新后可读回
        again = svc.load_rules(force=True)
        assert again["exposure"]["per_port_score"] == 30


class TestBatchAndHistory:
    def test_score_all_persists_and_history(self, db_session):
        a = _make_asset()
        db_session.add(a)
        db_session.commit()

        svc = AssetRiskService(db_session)
        stats = svc.score_all()
        assert stats["scored"] == 1 and stats["errors"] == 0
        db_session.refresh(a)
        assert a.risk_score is not None
        assert a.score_breakdown is not None
        assert a.risk_scored_at is not None
        histories = db_session.query(AssetRiskHistory).filter_by(asset_id=a.id).all()
        assert len(histories) == 1

        # 二次评分 → 历史 +1
        svc.score_all()
        assert db_session.query(AssetRiskHistory).filter_by(asset_id=a.id).count() == 2

    def test_na_asset_stats(self, db_session):
        a = _make_asset(asset_status="offline", os_name=None, os_version=None)
        db_session.add(a)
        db_session.commit()
        stats = AssetRiskService(db_session).score_all()
        assert stats["na"] == 1 and stats["scored"] == 0
        db_session.refresh(a)
        assert a.risk_score is None  # N/A 而非 0


class TestSummaryDegradation:
    def test_fallback_when_budget_rejected(self, db_session, monkeypatch):
        """§八-C 降级：预算拒绝 → 规则化文案"""
        from app.services.asset_risk import AssetRiskService as S
        a = _make_asset()
        db_session.add(a)
        db_session.commit()
        svc = S(db_session)
        b = svc.score_asset(a, svc.load_rules(force=True))
        monkeypatch.setattr("app.services.asset_risk.ai_budget.allow", lambda: False)
        text, source = svc.generate_summary(a, b, force=True)
        assert source == "rule"
        assert "综合资产风险分" in text

    def test_should_summarize_threshold(self, db_session):
        svc = AssetRiskService(db_session)
        rules = svc.load_rules(force=True)
        a = _make_asset()
        db_session.add(a)
        db_session.commit()
        assert svc._should_summarize(a, 85, None, rules) is True    # 高分触发
        assert svc._should_summarize(a, 30, 15, rules) is False     # 低分平稳（30-15=15 < 20）不触发
        assert svc._should_summarize(a, 55, 20, rules) is True      # 上升 35 ≥ 20 触发


class TestPrefetchConsistency:
    def test_prefetch_same_as_single_query(self, db_session):
        """批量预取路径与单资产查询路径评分结果一致（N+1 优化的正确性回归）"""
        from app.services.asset_risk import AssetRiskService as S

        a1 = _make_asset(asset_ip="192.168.0.101")
        a2 = _make_asset(asset_ip="192.168.0.102", os_name="CentOS", os_version="7", criticality="critical")
        db_session.add_all([a1, a2])
        db_session.flush()
        for a, port in ((a1, 445), (a2, 3389)):
            db_session.add(AssetPort(asset_id=a.id, asset_ip=a.asset_ip, port=port, protocol="tcp", state="open"))
        v = Vulnerability(cve_id="CVE-2026-7777", title="t", severity="high", cvss_score=8.5)
        db_session.add(v)
        db_session.flush()
        db_session.add(AssetVulnerability(asset_id=a2.id, vulnerability_id=v.id, scanner="wazuh", status="open"))
        db_session.add(AlertGroupAnalysis(fingerprint="pf-a1", priority="P1", linked_asset_id=a1.id))
        db_session.commit()

        svc = S(db_session)
        rules = svc.load_rules(force=True)
        now = _now()
        ctx = svc._prefetch([a1.id, a2.id], now, rules)
        for a in (a1, a2):
            via_ctx = svc.score_asset(a, rules, now, ctx=ctx)
            single = svc.score_asset(a, rules, now)
            assert via_ctx is not None and single is not None
            assert via_ctx["total"] == single["total"], f"asset {a.asset_ip} 分数不一致"
            for k in ("exposure", "health", "alerts"):
                assert via_ctx["dimensions"][k]["score"] == single["dimensions"][k]["score"]
                assert via_ctx["dimensions"][k]["data_gap"] == single["dimensions"][k]["data_gap"]


class TestRefreshSummaryOnDemand:
    def test_subthreshold_asset_gets_summary_on_demand(self, db_session, monkeypatch):
        """低于批量门槛（60）的资产，详情页按需刷新也能拿到摘要（UI 承诺）；
        预算拒绝 → 规则文案降级，仍落库。"""
        a = _make_asset(criticality="low")  # 低重要性，确保总分 < 60
        db_session.add(a)
        db_session.commit()
        svc = AssetRiskService(db_session)
        stats = svc.score_all()
        db_session.refresh(a)
        assert a.risk_score is not None and a.risk_score < 60
        assert a.risk_summary is None  # 批量路径按门槛跳过

        monkeypatch.setattr("app.services.asset_risk.ai_budget.allow", lambda: False)
        out = svc.refresh_summary(a.id)
        assert out["risk_summary"]  # 按需生成（规则降级文案）
        assert out["summary_source"] == "rule"
        db_session.refresh(a)
        assert a.risk_summary is not None

    def test_batch_keeps_ondemand_summary(self, db_session, monkeypatch):
        """批量评分不再清空低分资产的按需摘要（保留用户显式生成的内容）"""
        a = _make_asset(criticality="low")
        db_session.add(a)
        db_session.commit()
        svc = AssetRiskService(db_session)
        monkeypatch.setattr("app.services.asset_risk.ai_budget.allow", lambda: False)
        svc.refresh_summary(a.id)
        db_session.refresh(a)
        assert a.risk_summary is not None
        svc.score_all()  # 再次批量（低分 → skipped）
        db_session.refresh(a)
        assert a.risk_summary is not None  # 不被清空

    def test_na_asset_returns_message(self, db_session):
        a = _make_asset(asset_status="offline", os_name=None, os_version=None)
        db_session.add(a)
        db_session.commit()
        svc = AssetRiskService(db_session)
        out = svc.refresh_summary(a.id)
        assert out["risk_score"] is None
        assert "数据不足" in out["message"]

    def test_refresh_nonexistent_asset(self, db_session):
        import uuid
        assert AssetRiskService(db_session).refresh_summary(uuid.uuid4()) is None
