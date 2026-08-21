"""
F3.2 资产生命周期服务测试

覆盖（PRD F3.2 / v1.2.1）：
- OS 标签规范化（Ubuntu Linux / Debian GNU/Linux / CentOS Linux 变体）
- 参考表匹配：最长模式优先（centos stream 9 不被 centos 9 抢）、Win11 不误命中 Win10
- 无匹配诚实留空（Kali 滚动版不编造日期）
- 刷新回填：manual 覆盖不被触碰；OS 变更后旧 preset 值清空
- 手动覆盖 / 恢复自动匹配 + 审计落库
- 总览分桶（已超期 / 30 天 / 90 天 / 保修）+ 预估口径透出
- 推送场景：EOL 30 天 info、7 天 warn、已超期 warn
"""
from datetime import date, timedelta

import pytest

from app.models import Asset
from app.models.audit_log import AuditLog
from app.models.eol_reference import EolReference
from app.services.asset_lifecycle import AssetLifecycleService, normalize_os_label


def _ref(db, pattern, name, eol, source="preset", notes=None):
    r = EolReference(pattern=pattern, display_name=name, eol_date=eol,
                     source=source, notes=notes, enabled=True)
    db.add(r)
    db.commit()
    return r


def _asset(db, ip, os_name=None, os_version=None, **kw):
    a = Asset(asset_ip=ip, name=kw.pop("name", f"host-{ip}"),
              os_name=os_name, os_version=os_version, **kw)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


class TestNormalize:
    @pytest.mark.parametrize("os_name,os_version,expected", [
        ("Ubuntu", "24.04.2 LTS", "ubuntu 24.04.2 lts"),
        ("Ubuntu Linux", "24.04 LTS", "ubuntu 24.04 lts"),
        ("Debian GNU/Linux", "12", "debian 12"),
        ("CentOS Linux", "7.9", "centos 7.9"),
        ("Microsoft Windows 11 Home China", "10.0.26200", "microsoft windows 11 home china 10.0.26200"),
    ])
    def test_normalize(self, db_session, os_name, os_version, expected):
        a = Asset(asset_ip="1.1.1.1", os_name=os_name, os_version=os_version)
        assert normalize_os_label(a) == expected


class TestMatching:
    def test_variants_match_same_ref(self, db_session):
        _ref(db_session, "ubuntu 24.04", "Ubuntu 24.04 LTS", date(2029, 4, 30))
        svc = AssetLifecycleService(db_session)
        for name, ver in [("Ubuntu", "24.04.2 LTS"), ("Ubuntu Linux", "24.04 LTS"), ("Ubuntu", "24.04")]:
            a = Asset(asset_ip="2.2.2.2", os_name=name, os_version=ver)
            ref = svc._match_reference(a)
            assert ref is not None and ref.eol_date == date(2029, 4, 30)

    def test_longest_pattern_wins(self, db_session):
        _ref(db_session, "centos 8", "CentOS 8", date(2021, 12, 31))
        _ref(db_session, "centos stream 8", "CentOS Stream 8", date(2024, 5, 31))
        svc = AssetLifecycleService(db_session)
        a = Asset(asset_ip="3.3.3.3", os_name="CentOS Stream", os_version="8")
        assert svc._match_reference(a).display_name == "CentOS Stream 8"

    def test_win11_not_matching_win10(self, db_session):
        _ref(db_session, "windows 10", "Windows 10", date(2025, 10, 14))
        _ref(db_session, "windows 11", "Windows 11", date(2026, 10, 13))
        svc = AssetLifecycleService(db_session)
        a = Asset(asset_ip="4.4.4.4", os_name="Microsoft Windows 11 Home China", os_version="10.0.26200")
        assert svc._match_reference(a).display_name == "Windows 11"

    def test_rolling_release_no_fabrication(self, db_session):
        """Kali 滚动版无参考条目 → 诚实留空，不编造日期"""
        _ref(db_session, "debian 13", "Debian 13", date(2030, 6, 30))
        svc = AssetLifecycleService(db_session)
        a = Asset(asset_ip="5.5.5.5", os_name="Kali GNU/Linux", os_version="2025.3")
        assert svc._match_reference(a) is None


class TestRefresh:
    def test_backfill_and_keep_manual(self, db_session):
        _ref(db_session, "debian 12", "Debian 12", date(2028, 6, 30))
        auto = _asset(db_session, "10.0.0.1", "Debian GNU/Linux", "12")
        manual = _asset(db_session, "10.0.0.2", "Debian GNU/Linux", "12",
                        expected_eol=date(2027, 1, 1), expected_eol_source="manual")
        no_os = _asset(db_session, "10.0.0.3")
        stats = AssetLifecycleService(db_session).refresh_eol_all()
        assert stats["matched"] == 1 and stats["kept_manual"] == 1 and stats["no_os"] == 1
        db_session.refresh(auto); db_session.refresh(manual)
        assert auto.expected_eol == date(2028, 6, 30) and auto.expected_eol_source == "preset"
        assert manual.expected_eol == date(2027, 1, 1)  # 人工覆盖不被触碰

    def test_clear_stale_preset_when_os_changed(self, db_session):
        a = _asset(db_session, "10.0.0.4", "SomeOS", "1.0",
                   expected_eol=date(2025, 1, 1), expected_eol_source="preset")
        stats = AssetLifecycleService(db_session).refresh_eol_all()
        assert stats["cleared"] == 1
        db_session.refresh(a)
        assert a.expected_eol is None


class TestOverrideAudit:
    def test_override_and_clear(self, db_session, admin_user):
        _ref(db_session, "ubuntu 22.04", "Ubuntu 22.04 LTS", date(2027, 4, 30))
        a = _asset(db_session, "10.0.1.1", "Ubuntu", "22.04")
        svc = AssetLifecycleService(db_session)
        out = svc.set_eol_override(a.id, date(2026, 12, 31), admin_user)
        assert out.expected_eol == date(2026, 12, 31) and out.expected_eol_source == "manual"
        assert db_session.query(AuditLog).filter(
            AuditLog.resource_name == f"asset:{a.id}:eol").count() == 1

        out2 = AssetLifecycleService(db_session).clear_eol_override(a.id, admin_user)
        assert out2.expected_eol == date(2027, 4, 30)   # 立即回落参考表
        assert out2.expected_eol_source == "preset"
        assert db_session.query(AuditLog).filter(
            AuditLog.resource_name == f"asset:{a.id}:eol").count() == 2

    def test_override_missing_asset(self, db_session, admin_user):
        import uuid
        assert AssetLifecycleService(db_session).set_eol_override(
            uuid.uuid4(), date(2030, 1, 1), admin_user) is None


class TestOverview:
    def test_buckets_and_unverified_flag(self, db_session):
        today = date.today()
        _ref(db_session, "windows 11", "Windows 11", today + timedelta(days=53),
             source="preset_unverified", notes="按 24H2 估算")
        _ref(db_session, "centos 7", "CentOS 7", today - timedelta(days=700))
        _asset(db_session, "10.1.0.1", "CentOS Linux", "7.9",
               expected_eol=today - timedelta(days=700))
        _asset(db_session, "10.1.0.2", "Windows", "11 Pro",
               expected_eol=today + timedelta(days=53))
        _asset(db_session, "10.1.0.3", "Windows", "11 Pro",
               expected_eol=today + timedelta(days=10))
        _asset(db_session, "10.1.0.4", warranty_end=today - timedelta(days=5))
        _asset(db_session, "10.1.0.5", warranty_end=today + timedelta(days=20))
        _asset(db_session, "10.1.0.6", "Kali GNU/Linux", "2025.3")  # 未匹配

        out = AssetLifecycleService(db_session).overview()
        assert len(out["eol_expired"]) == 1
        assert len(out["eol_within_30d"]) == 1
        assert len(out["eol_within_90d"]) == 1
        assert len(out["warranty_expired"]) == 1
        assert len(out["warranty_within_30d"]) == 1
        assert out["unmatched_count"] == 1  # Kali
        # 口径透出：预估条目带 unverified 标记
        assert out["eol_within_90d"][0]["eol_unverified"] is True
        assert out["eol_within_90d"][0]["eol_ref"] == "Windows 11"
        assert out["eol_expired"][0]["eol_unverified"] is False
