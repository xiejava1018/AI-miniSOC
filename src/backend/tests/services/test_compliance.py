"""
F3.3 合规基线判定引擎测试

核心断言围绕 PRD 的双层架构红线：
- 判定层完全确定性、零 LLM：同样输入必得同样结论
- 三态语义严格分离：unknown ≠ pass，且 unknown 不能被算进达标率分子/分母
- 规则 scope 未命中 → skipped，既不算达标也不算不达标
- checker 异常 → unknown（绝不静默放行，避免「异常即合规」的审计漏洞）
- 规则库校验：check.type 白名单外的规则直接拒绝加载（防 YAML 里塞任意表达式）
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Asset, AssetPort, ComplianceFinding
from app.services import compliance as comp_mod
from app.services.compliance import (
    Ctx,
    ComplianceService,
    _CHECKERS,
    _dependency_missing,
    _in_scope,
    load_ruleset,
)


def _asset(db, ip, **kw):
    a = Asset(asset_ip=ip, name=kw.pop("name", f"h-{ip}"),
              asset_status=kw.pop("asset_status", "online"), **kw)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _port(db, asset, port, service=None, state="open"):
    p = AssetPort(asset_id=asset.id, asset_ip=asset.asset_ip, port=port,
                  protocol="tcp", state=state, service=service)
    db.add(p)
    db.commit()
    return p


def _write_ruleset(tmp_path, monkeypatch, rules, version="9.9.9"):
    """写一个临时规则库并让 load_ruleset 指向它（隔离真实 YAML）"""
    import yaml as _yaml
    f = tmp_path / "rules.yaml"
    f.write_text(_yaml.safe_dump({"ruleset_version": version, "rules": rules},
                                 allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(comp_mod, "_RULES_PATH", f)
    comp_mod._ruleset_cache["value"] = None
    comp_mod._ruleset_cache["mtime"] = None
    out = load_ruleset(force=True)
    return out


def _rule(**kw):
    base = {"id": "T-001", "version": 1, "title": "测试规则",
            "category": "network", "severity": "high"}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# 规则库加载与校验
# ---------------------------------------------------------------------------

class TestRuleset:
    def test_real_ruleset_loads_and_is_wellformed(self):
        """真实规则库能加载，且每条规则字段完备、check.type 合法"""
        rs = load_ruleset(force=True)
        rules = rs["rules"]
        assert 10 <= len(rules) <= 20, "PRD 要求 10-15 条高价值规则，不做全量 CIS"
        assert rs["ruleset_version"], "规则库必须有版本号（审计自证）"
        for r in rules:
            assert r["check"]["type"] in _CHECKERS, f"{r['id']} 使用了未注册的判定类型"
            for f in ("id", "version", "title", "category", "severity", "baseline"):
                assert r.get(f), f"{r.get('id')} 缺字段 {f}"

    def test_rule_ids_unique(self):
        rules = load_ruleset(force=True)["rules"]
        ids = [r["id"] for r in rules]
        assert len(ids) == len(set(ids)), "规则 ID 必须唯一（findings 靠 rule_id 溯源）"

    def test_unknown_check_type_rejected_and_reported(self, tmp_path, monkeypatch):
        """白名单外的 check.type 不得进入判定，且必须显式上报（不能静默消失）"""
        bad = _write_ruleset(tmp_path, monkeypatch, [
            _rule(id="X-BAD", check={"type": "os.system", "cmd": "rm -rf /"}),
            _rule(id="X-OK", check={"type": "fields_not_empty", "fields": ["owner"]}),
        ])
        assert [r["id"] for r in bad["rules"]] == ["X-OK"], "非法判定类型必须被排除"
        assert any(i["id"] == "X-BAD" and "白名单" in i["reason"]
                   for i in bad["invalid_rules"]), "非法规则必须出现在 invalid_rules"

    def test_duplicate_ids_rejected_and_reported(self, tmp_path, monkeypatch):
        dup = _write_ruleset(tmp_path, monkeypatch, [
            _rule(id="X-1", check={"type": "fields_not_empty", "fields": ["owner"]}),
            _rule(id="X-1", check={"type": "fields_not_empty", "fields": ["name"]}),
        ])
        assert len(dup["rules"]) == 1, "重复 id 只保留首条"
        assert any(i["reason"] == "id 重复" for i in dup["invalid_rules"])

    def test_valid_ruleset_reports_no_invalid(self):
        """真实规则库不应有加载失败项"""
        assert load_ruleset(force=True).get("invalid_rules") == []


# ---------------------------------------------------------------------------
# 三态语义：pass / fail / unknown
# ---------------------------------------------------------------------------

class TestThreeState:
    def test_ports_never_scanned_is_unknown_not_pass(self, db_session):
        """从未扫描端口 → unknown。绝不能因为「没看到高危端口」就判达标"""
        a = _asset(db_session, "10.0.0.1", exposure_level="public")
        st, reason, _ = _CHECKERS["ports_absent"](
            Ctx(a, None), {"ports": [22, 3389]})
        assert st == "unknown"
        assert "无端口扫描数据" in reason

    def test_scanned_with_no_open_ports_can_pass(self, db_session):
        """扫过且无开放端口 → pass（空列表 [] 与 None 语义必须区分）"""
        a = _asset(db_session, "10.0.0.2", exposure_level="public")
        st, _, _ = _CHECKERS["ports_absent"](Ctx(a, []), {"ports": [22, 3389]})
        assert st == "pass"

    def test_dangerous_port_open_is_fail_with_evidence(self, db_session):
        a = _asset(db_session, "10.0.0.3", exposure_level="public")
        _port(db_session, a, 3389, service="ms-wbt-server")
        ports = ComplianceService(db_session)._ports_for([a.id]).get(a.id)
        st, reason, ev = _CHECKERS["ports_absent"](Ctx(a, ports), {"ports": [22, 3389]})
        assert st == "fail"
        assert "3389" in reason
        assert 3389 in ev["hit"], "证据必须落具体端口，供审计复核"

    def test_missing_field_is_unknown_when_declared_as_dependency(self, db_session):
        """声明了 requires 的字段缺失 → unknown（数据缺口），而非 fail（违规）"""
        a = _asset(db_session, "10.0.0.4", risk_score=None)
        assert _dependency_missing(Ctx(a, None), ["risk_score"]) is not None
        a2 = _asset(db_session, "10.0.0.5", risk_score=30)
        assert _dependency_missing(Ctx(a2, []), ["risk_score"]) is None

    def test_empty_required_field_is_fail_not_unknown(self, db_session):
        """未声明为依赖的必填项为空 → fail（管理缺失就是不达标）"""
        a = _asset(db_session, "10.0.0.6", owner=None)
        st, reason, _ = _CHECKERS["fields_not_empty"](Ctx(a, []), {"fields": ["owner"]})
        assert st == "fail"
        assert "owner" in reason

    def test_checker_exception_degrades_to_unknown(self, db_session, monkeypatch):
        """判定器抛异常必须落 unknown —— 异常绝不能被当作达标"""
        a = _asset(db_session, "10.0.0.7", owner="ops")

        def boom(ctx, cfg):
            raise RuntimeError("模拟判定器内部错误")

        monkeypatch.setitem(_CHECKERS, "fields_not_empty", boom)
        svc = ComplianceService(db_session)
        r = _rule(check={"type": "fields_not_empty", "fields": ["owner"]})
        out = svc._eval_one(Ctx(a, []), r)
        assert out["status"] == "unknown"


# ---------------------------------------------------------------------------
# scope 与 skipped
# ---------------------------------------------------------------------------

class TestScope:
    def test_scope_mismatch_is_skipped(self, db_session):
        a = _asset(db_session, "10.0.1.1", exposure_level="internal")
        assert _in_scope(a, {"exposure_level": ["public", "dmz"]}) is False
        assert _in_scope(a, {"exposure_level": ["internal"]}) is True

    def test_no_scope_means_all_assets(self, db_session):
        a = _asset(db_session, "10.0.1.2")
        assert _in_scope(a, None) is True

    def test_skipped_excluded_from_rates(self, db_session):
        """不适用项不得进入达标率/覆盖率的任何一端"""
        svc = ComplianceService(db_session)
        # pass=8 fail=2 unknown=10，skipped 无论多少都不参与
        assert svc._rate(8, 2) == 80
        assert svc._rate(10, 10) == 50
        assert svc._rate(0, 0) is None, "无可判定项时应返回 None 而非 0%（0% 会被误读为全不达标）"


# ---------------------------------------------------------------------------
# 各判定器语义
# ---------------------------------------------------------------------------

class TestCheckers:
    def test_date_not_passed(self, db_session):
        past = _asset(db_session, "10.0.2.1", expected_eol=date.today() - timedelta(days=10))
        future = _asset(db_session, "10.0.2.2", expected_eol=date.today() + timedelta(days=10))
        none = _asset(db_session, "10.0.2.3", expected_eol=None)
        cfg = {"field": "expected_eol"}
        assert _CHECKERS["date_not_passed"](Ctx(past, []), cfg)[0] == "fail"
        assert _CHECKERS["date_not_passed"](Ctx(future, []), cfg)[0] == "pass"
        assert _CHECKERS["date_not_passed"](Ctx(none, []), cfg)[0] == "unknown"

    def test_date_days_remaining_min(self, db_session):
        soon = _asset(db_session, "10.0.2.4", expected_eol=date.today() + timedelta(days=30))
        far = _asset(db_session, "10.0.2.5", expected_eol=date.today() + timedelta(days=400))
        cfg = {"field": "expected_eol", "min_days": 90}
        assert _CHECKERS["date_days_remaining_min"](Ctx(soon, []), cfg)[0] == "fail"
        assert _CHECKERS["date_days_remaining_min"](Ctx(far, []), cfg)[0] == "pass"

    def test_high_risk_port_count_max(self, db_session):
        a = _asset(db_session, "10.0.2.6")
        for p in (22, 3389, 445, 3306):
            _port(db_session, a, p)
        ports = ComplianceService(db_session)._ports_for([a.id]).get(a.id)
        watch = {"ports": [22, 445, 3306, 3389, 5432, 6379], "max": 3}
        st, reason, ev = _CHECKERS["high_risk_port_count_max"](Ctx(a, ports), watch)
        assert st == "fail"
        assert ev["count"] == 4, "证据需给出实际高危端口数"
        assert _CHECKERS["high_risk_port_count_max"](
            Ctx(a, ports), {**watch, "max": 10})[0] == "pass"

    def test_field_not_in(self, db_session):
        pub = _asset(db_session, "10.0.2.7", exposure_level="public")
        inner = _asset(db_session, "10.0.2.8", exposure_level="internal")
        cfg = {"field": "exposure_level", "forbidden": ["public", "dmz"]}
        assert _CHECKERS["field_not_in"](Ctx(pub, []), cfg)[0] == "fail"
        assert _CHECKERS["field_not_in"](Ctx(inner, []), cfg)[0] == "pass"

    def test_field_in_catches_dict_violation(self, db_session):
        """字典外取值必须被抓出：DEV 实测采集器写入 'normal' 使按重要度分流的规则静默失效"""
        bad = _asset(db_session, "10.0.2.9", criticality="normal")
        good = _asset(db_session, "10.0.2.10", criticality="medium")
        cfg = {"field": "criticality", "allowed": ["critical", "high", "medium", "low"]}
        st, reason, ev = _CHECKERS["field_in"](Ctx(bad, []), cfg)
        assert st == "fail"
        assert "normal" in reason
        assert _CHECKERS["field_in"](Ctx(good, []), cfg)[0] == "pass"

    def test_timestamp_within_days(self, db_session):
        fresh = _asset(db_session, "10.0.2.11",
                       last_synced_at=datetime.now(timezone.utc) - timedelta(days=1))
        stale = _asset(db_session, "10.0.2.12",
                       last_synced_at=datetime.now(timezone.utc) - timedelta(days=30))
        cfg = {"field": "last_synced_at", "days": 7}
        assert _CHECKERS["timestamp_within_days"](Ctx(fresh, []), cfg)[0] == "pass"
        assert _CHECKERS["timestamp_within_days"](Ctx(stale, []), cfg)[0] == "fail"

    def test_number_max(self, db_session):
        hi = _asset(db_session, "10.0.2.13", risk_score=88)
        lo = _asset(db_session, "10.0.2.14", risk_score=40)
        cfg = {"field": "risk_score", "max": 79}
        assert _CHECKERS["number_max"](Ctx(hi, []), cfg)[0] == "fail"
        assert _CHECKERS["number_max"](Ctx(lo, []), cfg)[0] == "pass"


# ---------------------------------------------------------------------------
# 巡检落库
# ---------------------------------------------------------------------------

class TestRunCheck:
    def test_run_persists_only_problems(self, db_session):
        """只落 fail/unknown 明细；pass 只进 stats 计数（控表体积）"""
        _asset(db_session, "10.0.3.1", owner=None, asset_status="online")
        svc = ComplianceService(db_session)
        run = svc.run_check(triggered_by="pytest")

        assert run.ruleset_version == load_ruleset()["ruleset_version"]
        assert run.pass_count + run.fail_count + run.unknown_count > 0
        rows = db_session.query(ComplianceFinding).filter(
            ComplianceFinding.run_id == run.id).all()
        assert rows, "应落问题明细"
        assert all(r.status in ("fail", "unknown") for r in rows), "pass 不入明细表"
        assert len(rows) == run.fail_count + run.unknown_count

    def test_offline_assets_out_of_scope(self, db_session):
        """已下线资产不参与判定，否则会长期拉低达标率造成噪声"""
        _asset(db_session, "10.0.3.2", asset_status="online")
        _asset(db_session, "10.0.3.3", asset_status="offline")
        _asset(db_session, "10.0.3.4", asset_status="retired")
        run = ComplianceService(db_session).run_check(triggered_by="pytest")
        assert run.assets_total == 3
        assert run.assets_in_scope == 1

    def test_rates_exclude_unknown_from_numerator_and_denominator(self, db_session):
        """达标率分母只含 pass+fail；覆盖率暴露 unknown 占比"""
        _asset(db_session, "10.0.3.5", owner="ops", owner_contact="x@y.com")
        run = ComplianceService(db_session).run_check(triggered_by="pytest")
        s = run.stats
        judged = run.pass_count + run.fail_count
        if judged:
            assert run.compliance_rate == round(run.pass_count / judged * 100)
        denom = judged + run.unknown_count
        if denom:
            assert run.coverage_rate == round(judged / denom * 100)
        assert "per_rule" in s and "fail_by_severity" in s

    def test_findings_sorted_fail_before_unknown(self, db_session):
        a = _asset(db_session, "10.0.3.6", owner=None, exposure_level="public")
        svc = ComplianceService(db_session)
        run = svc.run_check(triggered_by="pytest")
        data = svc.findings(run.id, page=1, page_size=100)
        statuses = [f.status for f in data["records"]]
        if "fail" in statuses and "unknown" in statuses:
            assert statuses.index("fail") < statuses.index("unknown"), "不达标必须排在无法判定之前"

    def test_findings_filter_by_status_and_rule(self, db_session):
        _asset(db_session, "10.0.3.7", owner=None)
        svc = ComplianceService(db_session)
        run = svc.run_check(triggered_by="pytest")
        only_fail = svc.findings(run.id, status="fail", page=1, page_size=100)
        assert all(f.status == "fail" for f in only_fail["records"])
        one_rule = svc.findings(run.id, rule_id="SOC-MGT-001", page=1, page_size=100)
        assert all(f.rule_id == "SOC-MGT-001" for f in one_rule["records"])

    def test_determinism_same_input_same_verdict(self, db_session):
        """确定性回归：连跑两次结论必须完全一致（判定层无 LLM、无随机）"""
        _asset(db_session, "10.0.3.8", owner=None, criticality="normal")
        svc = ComplianceService(db_session)
        r1 = svc.run_check(triggered_by="pytest-1")
        r2 = svc.run_check(triggered_by="pytest-2")
        assert (r1.pass_count, r1.fail_count, r1.unknown_count) == \
               (r2.pass_count, r2.fail_count, r2.unknown_count)
        assert r1.stats["per_rule"] == r2.stats["per_rule"]

    def test_latest_run_returns_newest(self, db_session):
        _asset(db_session, "10.0.3.9")
        svc = ComplianceService(db_session)
        svc.run_check(triggered_by="old")
        newest = svc.run_check(triggered_by="new")
        assert svc.latest_run().id == newest.id

    def test_evaluate_asset_includes_pass_items(self, db_session):
        """单资产视图需要看到全部规则（含达标项），便于逐条核对"""
        a = _asset(db_session, "10.0.3.10", owner="ops")
        out = ComplianceService(db_session).evaluate_asset(a)
        assert out["asset_id"] == str(a.id)
        assert len(out["items"]) == len(load_ruleset()["rules"])
        assert any(i["status"] == "pass" for i in out["items"])
        assert set(out["counts"]) == {"pass", "fail", "unknown", "skipped"}
