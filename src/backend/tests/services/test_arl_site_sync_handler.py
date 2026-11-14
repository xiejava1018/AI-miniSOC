"""OH-ARL.2/3 · ArlSiteSyncHandler 单测（docs/design/2026-11-14-ARL-Next集成设计方案.md §5.7）。

验证（测试库 db_session，不连网络）：
  - 校验：缺 ip / 非法 ip / 缺 port → failed + 死信
  - IP 命中台账 → soc_asset_sources('arl-next') + 端口多源融合
    （sources JSONB 追加 / last_seen_by_source 各记 / 补充不覆盖语义）
  - 命中但端口行不存在 → 新建端口行 sources=['arl-next']
  - IP 未命中 → soc_scan_findings(discovery_source='arl-next')，零直写 soc_assets
  - 幂等：同天重跑不产生新行（批次按 UTC 日期 uuid5）
  - exposure：公网 IP → public
  - 不调用 record_observation：失联判定不受 ARL 观测影响（§5.8）
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.models.asset import Asset
from app.models.asset_port import AssetPort
from app.models.asset_source import AssetSource
from app.models.scanner_models import ScanFinding, ScannerTask
from app.services.sync_handlers.arl_site_sync_handler import ArlSiteSyncHandler
from sqlalchemy.orm import Session


@pytest.fixture
def handler():
    return ArlSiteSyncHandler()


def _item(**overrides):
    item = {
        "ip": "192.168.0.60",
        "port": 9000,
        "scheme": "http",
        "service": "http",
        "title": "Portainer",
        "url": "http://192.168.0.60:9000",
        "fingers": ["Portainer"],
        "scope_id": "scope-1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    item.update(overrides)
    return item


class TestValidate:
    def test_missing_ip_rejected(self, db_session: Session, handler):
        stats = handler.handle("arl-next", [_item(ip="")], db_session)
        assert stats["failed"] == 1
        assert stats["dead_letter_batch_id"] is not None

    def test_invalid_ip_rejected(self, db_session: Session, handler):
        stats = handler.handle("arl-next", [_item(ip="not-an-ip")], db_session)
        assert stats["failed"] == 1

    def test_missing_port_rejected(self, db_session: Session, handler):
        stats = handler.handle("arl-next", [_item(port=None)], db_session)
        assert stats["failed"] == 1


class TestMatchedAsset:
    def test_upserts_source_and_merges_port(self, db_session: Session, handler):
        asset = Asset(name="fnNAS", asset_ip="192.168.0.60", network_segment="default")
        db_session.add(asset)
        db_session.commit()
        port = AssetPort(
            asset_ip="192.168.0.60", port=9000, protocol="tcp",
            service="http", sources=["scanner"],
            last_seen_by_source={"scanner": "2026-11-13T00:00:00+00:00"},
        )
        db_session.add(port)
        db_session.commit()

        stats = handler.handle("arl-next", [_item()], db_session)
        assert stats["updated"] == 1
        assert stats["created"] == 0

        src = (
            db_session.query(AssetSource)
            .filter(AssetSource.asset_id == asset.id,
                    AssetSource.source == "arl-next")
            .one()
        )
        assert src.source_status == "observed"
        assert src.source_id == "scope-1"
        assert (src.source_metadata or {}).get("title") == "Portainer"

        db_session.refresh(port)
        assert "arl-next" in port.sources
        assert "scanner" in port.sources  # 多源并存不覆盖（§5.8）
        assert "arl-next" in port.last_seen_by_source
        assert port.service == "http"  # 既有值不被覆盖

    def test_creates_missing_port_row(self, db_session: Session, handler):
        db_session.add(Asset(name="fnNAS", asset_ip="192.168.0.60",
                             network_segment="default"))
        db_session.commit()
        stats = handler.handle("arl-next", [_item()], db_session)
        assert stats["updated"] == 1
        port = (
            db_session.query(AssetPort)
            .filter(AssetPort.asset_ip == "192.168.0.60", AssetPort.port == 9000)
            .one()
        )
        assert port.sources == ["arl-next"]

    def test_no_observation_recorded(self, db_session: Session, handler,
                                     monkeypatch):
        """§5.8：ARL 观测不进存在性判定——record_observation 不得被调用。"""
        from app.services import asset_presence

        called = []
        monkeypatch.setattr(
            asset_presence, "record_observation",
            lambda *a, **k: called.append(a),
        )
        db_session.add(Asset(name="fnNAS", asset_ip="192.168.0.60",
                             network_segment="default"))
        db_session.commit()
        handler.handle("arl-next", [_item()], db_session)
        assert called == []


class TestUnmatchedIp:
    def test_goes_to_findings_not_ledger(self, db_session: Session, handler):
        from app.models.asset import Asset as A
        before = db_session.query(A).count()
        stats = handler.handle("arl-next", [_item(ip="192.168.0.99")], db_session)
        assert stats["created"] == 1
        assert db_session.query(A).count() == before  # 零直写台账

        f = (
            db_session.query(ScanFinding)
            .filter(ScanFinding.asset_ip == "192.168.0.99")
            .one()
        )
        assert f.discovery_source == "arl-next"
        assert f.finding_status == "new"
        assert f.exposure == "internal"
        assert (f.raw_data or {}).get("title") == "Portainer"
        # 批次行（OH-ARL.4）
        assert db_session.query(ScannerTask).filter(
            ScannerTask.task_uuid == f.scan_task_uuid,
            ScannerTask.mode == "arl_sync",
        ).count() == 1

    def test_public_ip_exposure(self, db_session: Session, handler):
        handler.handle("arl-next", [_item(ip="118.253.185.206", port=443,
                                          scheme="https", service="https")],
                       db_session)
        f = (
            db_session.query(ScanFinding)
            .filter(ScanFinding.asset_ip == "118.253.185.206")
            .one()
        )
        assert f.exposure == "public"


class TestIdempotent:
    def test_same_day_rerun_no_new_rows(self, db_session: Session, handler):
        db_session.add(Asset(name="fnNAS", asset_ip="192.168.0.60",
                             network_segment="default"))
        db_session.commit()
        handler.handle("arl-next", [_item(ip="192.168.0.60"),
                                    _item(ip="192.168.0.99")], db_session)
        first_assets = db_session.query(AssetSource).count()
        first_findings = db_session.query(ScanFinding).count()

        stats = handler.handle("arl-next", [_item(ip="192.168.0.60"),
                                            _item(ip="192.168.0.99")], db_session)
        # 同天重跑：命中→updated，未命中→finding 行 upsert（updated）
        assert stats["created"] == 0
        assert stats["updated"] == 2
        assert db_session.query(AssetSource).count() == first_assets
        assert db_session.query(ScanFinding).count() == first_findings
