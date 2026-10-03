"""资产事件时间线 API — 契约测试（P0 联邦查询 REST）。

覆盖：
- 非法 asset_id → 400
- 资产不存在 → 404
- 正常路径：envelope code=200 + data 结构完整（events / source_status / coverage_note）
- 单源降级时 envelope 仍 200，source_status 正确标注
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.asset import Asset
from app.services.federation import timeline_service as svc_mod
from app.services.federation.schemas import (
    AssetAnchor,
    EventRecord,
    EventType,
    SourceKey,
)


@pytest.fixture
def authed_client(client, test_user):
    """覆盖 get_current_user 依赖（client fixture 默认不提供 token）。"""
    from app.api.deps import get_current_user

    client.app.dependency_overrides[get_current_user] = lambda: test_user
    yield client
    client.app.dependency_overrides.pop(get_current_user, None)


def _mock_adapters(pg=None, os_=None, loki=None):
    """把 TimelineService 引用的三个适配器类替换为返回指定列表的 MagicMock。

    返回 (mocks, patchers)：mocks 为类名→实例（可改 .fetch.side_effect），patchers 用于 teardown。
    """
    mocks: dict = {}
    patchers = []
    for name, val in (("PGAdapter", pg), ("OSAdapter", os_), ("LokiAdapter", loki)):
        p = patch(f"app.services.federation.timeline_service.{name}")
        mock_cls = p.start()
        inst = MagicMock()
        inst.fetch = MagicMock(return_value=val if val is not None else [])
        mock_cls.return_value = inst
        mocks[name] = inst
        patchers.append(p)
    return mocks, patchers


def _seed_asset(db_session, ip="10.0.0.99"):
    asset = Asset(
        network_segment="default", network_zone="other", asset_ip=ip,
        asset_description="api-host", asset_status="在线", name="api-host",
        asset_type="server", criticality="normal",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


class TestAssetTimelineAPI:
    def test_invalid_asset_id(self, authed_client):
        # 响应包装中间件：HTTP 恒 200，业务码在 body.code（此处应为 400）
        r = authed_client.get("/api/v1/assets/not-a-uuid/timeline")
        assert r.status_code == 200
        assert r.json()["code"] == 400

    def test_asset_not_found(self, authed_client, db_session):
        import uuid

        # 响应包装中间件：HTTP 恒 200，业务码在 body.code（此处应为 404）
        r = authed_client.get(f"/api/v1/assets/{uuid.uuid4()}/timeline")
        assert r.status_code == 200
        assert r.json()["code"] == 404

    def test_success_envelope(self, authed_client, db_session):
        asset = _seed_asset(db_session)
        t = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        evs = [
            EventRecord(
                event_id="p1", ts=t, source=SourceKey.PG, event_type=EventType.ALERT,
                asset_anchor=asset.asset_ip, asset_id=str(asset.id), summary="x",
            )
        ]
        mocks, patchers = _mock_adapters(pg=evs, os_=[], loki=[])
        try:
            r = authed_client.get(f"/api/v1/assets/{asset.id}/timeline")
        finally:
            for p in patchers:
                p.stop()
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 200
        assert body["data"]["asset_id"] == str(asset.id)
        assert len(body["data"]["events"]) == 1
        assert body["data"]["events"][0]["event_id"] == "p1"
        assert body["data"]["source_status"]["pg"] == "ok"

    def test_source_degraded_envelope(self, authed_client, db_session):
        """单源降级时 envelope 仍 200，source_status 标注该源 error。"""
        asset = _seed_asset(db_session, ip="10.0.0.98")
        t = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        pg = [EventRecord(
            event_id="p1", ts=t, source=SourceKey.PG, event_type=EventType.ALERT,
            asset_anchor=asset.asset_ip, asset_id=str(asset.id), summary="x",
        )]
        mocks, patchers = _mock_adapters(pg=pg, os_=None, loki=[])
        mocks["OSAdapter"].fetch.side_effect = RuntimeError("OS down")
        try:
            r = authed_client.get(f"/api/v1/assets/{asset.id}/timeline")
        finally:
            for p in patchers:
                p.stop()
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 200
        # PG 事件仍返回
        assert len(body["data"]["events"]) == 1
        assert body["data"]["source_status"]["opensearch"] == "error"
        assert body["data"]["source_status"]["pg"] == "ok"
