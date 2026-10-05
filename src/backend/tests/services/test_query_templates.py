"""OH-4.9 L2 查询模板执行器单测（4→10 模板）。

覆盖 6 个新模板的：
  - 参数校验（走 validate → execute）
  - 返回结构（assets/total/notes 必含）
  - coverage 数据覆盖率披露纪律
旧 4 模板的执行路径通过 load/execute 一致性冒烟顺带保护。
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_port import AssetPort
from app.models.business_system import AssetBusiness, BusinessSystem
from app.models.vulnerability import AssetVulnerability, Vulnerability
from app.services import query_templates as qt


# ----------------------------------------------------------------- helpers


def _make_asset(
    db: Session,
    name: str,
    ip: str,
    *,
    risk_score=None,
    owner=None,
    business_unit=None,
    expected_eol=None,
) -> Asset:
    a = Asset(
        name=name,
        asset_ip=ip,
        risk_score=risk_score,
        owner=owner,
        business_unit=business_unit,
        expected_eol=expected_eol,
    )
    db.add(a)
    return a


def _make_port(db: Session, asset: Asset, port: int, state: str = "open") -> AssetPort:
    p = AssetPort(asset_id=asset.id, asset_ip=str(asset.asset_ip), port=port,
                  protocol="tcp", state=state)
    db.add(p)
    return p


def _make_system(db: Session, code: str, name: str) -> BusinessSystem:
    s = BusinessSystem(code=code, name=name)
    db.add(s)
    return s


def _make_vuln(db: Session, cve: str, severity: str) -> Vulnerability:
    v = Vulnerability(type="sca", cve_id=cve, title=f"漏洞 {cve}", severity=severity)
    db.add(v)
    return v


# ----------------------------------------------------------------- 模板加载


class TestTemplateCatalog:
    def test_ten_templates_registered(self):
        cfg = qt.load_templates(force=True)
        assert len(cfg["templates"]) == 10
        assert cfg["version"] == 2

    def test_yaml_and_executors_aligned(self):
        cfg = qt.load_templates(force=True)
        assert set(cfg["templates"].keys()) == set(qt._EXECUTORS.keys())

    def test_prompt_catalog_lists_new_templates(self):
        catalog = qt.template_catalog_for_prompt()
        for tid in ("high_risk_assets", "eol_assets", "port_count_by_asset"):
            assert tid in catalog


# ----------------------------------------------------------------- high_risk


class TestHighRiskAssets:
    def test_orders_by_risk_desc(self, db_session: Session):
        _make_asset(db_session, "low", "10.0.0.1", risk_score=20)
        _make_asset(db_session, "high", "10.0.0.2", risk_score=90)
        _make_asset(db_session, "mid", "10.0.0.3", risk_score=50)
        db_session.commit()

        out = qt.execute(db_session, "high_risk_assets", {})
        scores = [a["risk_score"] for a in out["assets"]]
        assert scores == sorted(scores, reverse=True)
        assert scores[0] == 90
        assert out["total"] == 3

    def test_min_score_filter(self, db_session: Session):
        _make_asset(db_session, "a", "10.0.0.1", risk_score=10)
        _make_asset(db_session, "b", "10.0.0.2", risk_score=85)
        db_session.commit()

        out = qt.execute(db_session, "high_risk_assets", {"min_score": "80"})
        assert out["total"] == 1
        assert out["assets"][0]["risk_score"] == 85

    def test_unscored_excluded_and_reported(self, db_session: Session):
        _make_asset(db_session, "scored", "10.0.0.1", risk_score=40)
        _make_asset(db_session, "unscored", "10.0.0.2", risk_score=None)
        db_session.commit()

        out = qt.execute(db_session, "high_risk_assets", {})
        assert out["total"] == 1
        assert out["coverage"]["unscored"] == 1
        assert any("未评分" in n for n in out["notes"])

    def test_invalid_min_score(self, db_session: Session):
        with pytest.raises(qt.TemplateError):
            qt.execute(db_session, "high_risk_assets", {"min_score": 150})


# ------------------------------------------------------- business system


class TestAssetByBusinessSystem:
    def test_members_with_role(self, db_session: Session):
        a1 = _make_asset(db_session, "web1", "10.0.1.1", risk_score=70)
        a2 = _make_asset(db_session, "db1", "10.0.1.2", risk_score=30)
        sys = _make_system(db_session, "soc-platform", "SOC平台")
        db_session.commit()
        db_session.add_all([
            AssetBusiness(asset_id=a1.id, system_id=sys.id, role="web"),
            AssetBusiness(asset_id=a2.id, system_id=sys.id, role="db"),
        ])
        db_session.commit()

        out = qt.execute(db_session, "asset_by_business_system", {"system": "soc-platform"})
        assert out["total"] == 2
        roles = {a["ip"]: a["system_role"] for a in out["assets"]}
        assert roles["10.0.1.1"] == "web"
        assert roles["10.0.1.2"] == "db"

    def test_match_by_name_fuzzy(self, db_session: Session):
        a = _make_asset(db_session, "x", "10.0.1.3")
        sys = _make_system(db_session, "oa-sys", "办公自动化系统")
        db_session.commit()
        db_session.add(AssetBusiness(asset_id=a.id, system_id=sys.id, role="app"))
        db_session.commit()

        out = qt.execute(db_session, "asset_by_business_system", {"system": "办公"})
        assert out["total"] == 1

    def test_system_not_found(self, db_session: Session):
        out = qt.execute(db_session, "asset_by_business_system", {"system": "nope"})
        assert out["total"] == 0
        assert out["assets"] == []


# ------------------------------------------------------------- vuln assets


class TestVulnAssets:
    def test_aggregates_vulns_under_asset(self, db_session: Session):
        a = _make_asset(db_session, "host", "10.0.2.1", risk_score=88)
        v1 = _make_vuln(db_session, "CVE-2024-0001", "critical")
        v2 = _make_vuln(db_session, "CVE-2024-0002", "high")
        db_session.commit()
        db_session.add_all([
            AssetVulnerability(asset_id=a.id, vulnerability_id=v1.id,
                               status="open", scanner="manual"),
            AssetVulnerability(asset_id=a.id, vulnerability_id=v2.id,
                               status="open", scanner="manual"),
        ])
        db_session.commit()

        out = qt.execute(db_session, "vuln_assets", {})
        assert out["total"] == 1
        assert len(out["assets"][0]["vulnerabilities"]) == 2

    def test_severity_filter(self, db_session: Session):
        a = _make_asset(db_session, "host", "10.0.2.2")
        vc = _make_vuln(db_session, "CVE-C", "critical")
        vl = _make_vuln(db_session, "CVE-L", "low")
        db_session.commit()
        db_session.add_all([
            AssetVulnerability(asset_id=a.id, vulnerability_id=vc.id,
                               status="open", scanner="manual"),
            AssetVulnerability(asset_id=a.id, vulnerability_id=vl.id,
                               status="open", scanner="manual"),
        ])
        db_session.commit()

        out = qt.execute(db_session, "vuln_assets", {"severity": "critical"})
        assert out["total"] == 1
        assert out["assets"][0]["vulnerabilities"][0]["severity"] == "critical"

    def test_status_fixed_excluded_by_default(self, db_session: Session):
        a = _make_asset(db_session, "host", "10.0.2.3")
        v = _make_vuln(db_session, "CVE-F", "high")
        db_session.commit()
        db_session.add(AssetVulnerability(asset_id=a.id, vulnerability_id=v.id,
                                          status="fixed", scanner="manual"))
        db_session.commit()

        out = qt.execute(db_session, "vuln_assets", {})
        assert out["total"] == 0

    def test_invalid_severity(self, db_session: Session):
        with pytest.raises(qt.TemplateError):
            qt.execute(db_session, "vuln_assets", {"severity": "ultra"})


# ----------------------------------------------------------------- owner


class TestAssetsByOwner:
    def test_owner_fuzzy(self, db_session: Session):
        _make_asset(db_session, "a", "10.0.3.1", owner="张三")
        _make_asset(db_session, "b", "10.0.3.2", owner="张无忌")
        _make_asset(db_session, "c", "10.0.3.3", owner="李四")
        db_session.commit()

        out = qt.execute(db_session, "assets_by_owner", {"owner": "张"})
        assert out["total"] == 2

    def test_missing_owner_reported(self, db_session: Session):
        _make_asset(db_session, "a", "10.0.3.4", owner="张三")
        _make_asset(db_session, "b", "10.0.3.5", owner=None)
        db_session.commit()

        out = qt.execute(db_session, "assets_by_owner", {"owner": "张三"})
        assert out["coverage"]["missing_owner"] == 1


# ----------------------------------------------------------------- eol


class TestEolAssets:
    def test_expired_and_within(self, db_session: Session):
        today = date.today()
        _make_asset(db_session, "expired", "10.0.4.1", expected_eol=today - timedelta(days=10))
        _make_asset(db_session, "soon", "10.0.4.2", expected_eol=today + timedelta(days=20))
        _make_asset(db_session, "far", "10.0.4.3", expected_eol=today + timedelta(days=300))
        db_session.commit()

        out = qt.execute(db_session, "eol_assets", {"within_days": "90"})
        ips = {a["ip"] for a in out["assets"]}
        assert ips == {"10.0.4.1", "10.0.4.2"}
        states = {a["ip"]: a["eol_state"] for a in out["assets"]}
        assert states["10.0.4.1"] == "expired"

    def test_missing_eol_reported(self, db_session: Session):
        _make_asset(db_session, "no-eol", "10.0.4.4", expected_eol=None)
        db_session.commit()

        out = qt.execute(db_session, "eol_assets", {})
        assert out["total"] == 0
        assert out["coverage"]["missing_eol"] == 1


# --------------------------------------------------------- port count


class TestPortCountByAsset:
    def test_descending_count(self, db_session: Session):
        a1 = _make_asset(db_session, "many", "10.0.5.1")
        a2 = _make_asset(db_session, "one", "10.0.5.2")
        db_session.commit()
        _make_port(db_session, a1, 22)
        _make_port(db_session, a1, 80)
        _make_port(db_session, a1, 443)
        _make_port(db_session, a2, 22)
        db_session.commit()

        out = qt.execute(db_session, "port_count_by_asset", {})
        counts = [a["open_port_count"] for a in out["assets"]]
        assert counts == [3, 1]

    def test_min_ports_filter(self, db_session: Session):
        a1 = _make_asset(db_session, "many", "10.0.5.3")
        a2 = _make_asset(db_session, "one", "10.0.5.4")
        db_session.commit()
        _make_port(db_session, a1, 22)
        _make_port(db_session, a1, 80)
        _make_port(db_session, a2, 22)
        db_session.commit()

        out = qt.execute(db_session, "port_count_by_asset", {"min_ports": 2})
        assert out["total"] == 1
        assert out["assets"][0]["ip"] == "10.0.5.3"

    def test_closed_ports_not_counted(self, db_session: Session):
        a = _make_asset(db_session, "h", "10.0.5.5")
        db_session.commit()
        _make_port(db_session, a, 22, state="closed")
        db_session.commit()

        out = qt.execute(db_session, "port_count_by_asset", {})
        assert out["total"] == 0
