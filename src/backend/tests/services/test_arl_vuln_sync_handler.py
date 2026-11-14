"""OH-ARL.2 · ArlVulnSyncHandler 单测（§5.5/§5.6 冲突 1/2 分流）。

验证（测试库 db_session）：
  - 无 CVE 未命中资产 → soc_scan_findings 旁路（discovery_source='arl-next'）
  - 同 IP 多插件 → 1 行 findings，raw_data.vulns 聚合数组（唯一键不改迁移）
  - 有 CVE + 命中资产 → Vulnerability(type='arl_poc')
    + AssetVulnerability(scanner='arl-next'，scan_task_id 指向
      soc_scan_tasks(task_type='arl_sync') 日期批次行——冲突 2 处置)
  - 有 CVE 未命中资产 → 仍走 findings（漏洞必须挂 asset FK）
  - 幂等：同天重跑不产生新行
"""
from __future__ import annotations

import pytest
from app.models.asset import Asset
from app.models.scanner_models import ScanFinding
from app.models.vulnerability import AssetVulnerability, ScanTask, Vulnerability
from app.services.sync_handlers.arl_vuln_sync_handler import ArlVulnSyncHandler
from sqlalchemy.orm import Session


@pytest.fixture
def handler():
    return ArlVulnSyncHandler()


def _vuln_item(**overrides):
    item = {
        "ip": "192.168.0.42",
        "url": "https://192.168.0.42:5173",
        "plugin_name": "Swagger_Json_Identify",
        "app_name": "Swagger",
        "cve_ids": [],
        "source_table": "asset_vuln",
        "observed_at": "2026-11-14T08:00:00+00:00",
    }
    item.update(overrides)
    return item


class TestFindingsBypass:
    def test_no_cve_unmatched_goes_to_findings(self, db_session: Session, handler):
        stats = handler.handle("arl-next", [_vuln_item()], db_session)
        assert stats["created"] == 1
        f = (
            db_session.query(ScanFinding)
            .filter(ScanFinding.asset_ip == "192.168.0.42")
            .one()
        )
        assert f.discovery_source == "arl-next"
        assert (f.raw_data or {}).get("vulns")[0]["plugin_name"] == "Swagger_Json_Identify"

    def test_same_ip_multiple_plugins_aggregate(self, db_session: Session, handler):
        stats = handler.handle(
            "arl-next",
            [_vuln_item(),
             _vuln_item(plugin_name="Nacos_Auth_Bypass",
                        url="http://192.168.0.42:8848/nacos")],
            db_session,
        )
        # 同天同 IP 唯一键 → 第二条为聚合更新
        assert stats["created"] == 1
        assert stats["updated"] == 1
        assert db_session.query(ScanFinding).count() == 1
        f = (
            db_session.query(ScanFinding)
            .filter(ScanFinding.asset_ip == "192.168.0.42")
            .one()
        )
        assert len(f.raw_data["vulns"]) == 2

    def test_cve_without_asset_goes_to_findings(self, db_session: Session, handler):
        item = _vuln_item(cve_ids=["CVE-2026-1234"])
        stats = handler.handle("arl-next", [item], db_session)
        assert stats["created"] == 1
        assert db_session.query(Vulnerability).count() == 0  # 未命中资产不入漏洞表
        f = db_session.query(ScanFinding).one()
        assert f.raw_data["vulns"][0]["cve_ids"] == ["CVE-2026-1234"]


class TestVulnerabilityPath:
    def test_cve_with_asset_creates_records(self, db_session: Session, handler):
        asset = Asset(name="arl-self", asset_ip="192.168.0.42",
                      network_segment="default")
        db_session.add(asset)
        db_session.commit()
        item = _vuln_item(
            cve_ids=["CVE-2026-1234", "CVE-2026-5678"],
            severity="high",
        )
        stats = handler.handle("arl-next", [item], db_session)
        assert stats["created"] == 2

        vulns = {v.cve_id: v for v in db_session.query(Vulnerability).all()}
        assert set(vulns) == {"CVE-2026-1234", "CVE-2026-5678"}
        for v in vulns.values():
            assert v.type == "arl_poc"
            assert v.severity == "high"

        links = (
            db_session.query(AssetVulnerability)
            .filter(AssetVulnerability.scanner == "arl-next")
            .all()
        )
        assert len(links) == 2
        assert {str(l.asset_id) for l in links} == {str(asset.id)}

    def test_scan_task_batch_record(self, db_session: Session, handler):
        """OH-ARL.4：漏洞路径的批次记录落在 soc_scan_tasks（task_type='arl_sync'）。"""
        db_session.add(Asset(name="arl-self", asset_ip="192.168.0.42",
                             network_segment="default"))
        db_session.commit()
        handler.handle("arl-next", [_vuln_item(cve_ids=["CVE-2026-1234"])],
                       db_session)
        batch = (
            db_session.query(ScanTask)
            .filter(ScanTask.task_type == "arl_sync")
            .one()
        )
        link = db_session.query(AssetVulnerability).one()
        assert link.scan_task_id == batch.id

    def test_idempotent_same_day(self, db_session: Session, handler):
        db_session.add(Asset(name="arl-self", asset_ip="192.168.0.42",
                             network_segment="default"))
        db_session.commit()
        handler.handle("arl-next", [_vuln_item(cve_ids=["CVE-2026-1234"])],
                       db_session)
        stats = handler.handle("arl-next",
                               [_vuln_item(cve_ids=["CVE-2026-1234"])], db_session)
        assert stats["created"] == 0
        assert db_session.query(Vulnerability).count() == 1
        assert db_session.query(AssetVulnerability).count() == 1
        assert db_session.query(ScanTask).filter(
            ScanTask.task_type == "arl_sync").count() == 1


class TestValidate:
    def test_missing_ip_rejected(self, db_session: Session, handler):
        stats = handler.handle("arl-next", [_vuln_item(ip="")], db_session)
        assert stats["failed"] == 1

    def test_empty_item_rejected(self, db_session: Session, handler):
        stats = handler.handle(
            "arl-next", [_vuln_item(plugin_name=None, url=None)], db_session,
        )
        assert stats["failed"] == 1
