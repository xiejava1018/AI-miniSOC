"""资产统一事件时间线 — 单元测试（P0 联邦查询）。

覆盖：
- TimelineService 编排：合并 / 排序 / 类型过滤 / 游标分页 / 单源失败降级 /
  超时隔离（G1 实证）/ Loki 7 天窗口裁剪（§5.7 诚实性）
- PGAdapter：G3 行为画像 asset_id 可空回退、G4 身份事件纳入、告警簇关联
- schemas：游标编解码
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.core.database import TestingSessionLocal
from app.services.federation.adapters import PGAdapter
from app.services.federation.schemas import (
    AssetAnchor,
    EventRecord,
    EventType,
    SourceKey,
    decode_cursor,
    encode_cursor,
)
from app.services.federation.timeline_service import SourceTimeout, TimelineService


def _ev(event_id, ts, source=SourceKey.PG, etype=EventType.ALERT, asset_id="a1"):
    return EventRecord(
        event_id=event_id,
        ts=ts,
        source=source,
        event_type=etype,
        asset_anchor="10.0.0.1",
        asset_id=asset_id,
        summary=event_id,
    )


def _anchor():
    return AssetAnchor(asset_id="a1", ips=["10.0.0.1"])


def _patch_adapters(pg=None, os_=None, loki=None):
    """把 TimelineService 引用的三个适配器类替换为 MagicMock（.fetch 返回指定列表）。"""
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


# ---------------------------------------------------------------------------
# 编排：合并 / 排序 / 类型过滤 / 分页
# ---------------------------------------------------------------------------


class TestOrchestration:
    def _run(self, pg=None, os_=None, loki=None, **kw):
        mocks, patchers = _patch_adapters(pg, os_, loki)
        try:
            return asyncio.run(
                TimelineService().get_timeline(
                    anchor=_anchor(),
                    start=kw.get("start", datetime(2026, 1, 1, tzinfo=timezone.utc)),
                    end=kw.get("end", datetime(2026, 1, 2, tzinfo=timezone.utc)),
                    types=kw.get("types"),
                    limit=kw.get("limit", 200),
                    cursor=kw.get("cursor"),
                )
            )
        finally:
            for p in patchers:
                p.stop()

    def test_merge_and_sort_desc(self):
        t = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        pg = [_ev("p2", t + timedelta(minutes=2)), _ev("p1", t)]
        os_ = [_ev("o1", t + timedelta(minutes=5), source=SourceKey.OPENSEARCH)]
        loki = [_ev("l1", t + timedelta(minutes=1), source=SourceKey.LOKI, etype=EventType.LOG)]
        res = self._run(pg=pg, os_=os_, loki=loki)
        assert [e.event_id for e in res.events] == ["o1", "p2", "l1", "p1"]  # 降序
        assert res.source_status == {"pg": "ok", "opensearch": "ok", "loki": "ok"}

    def test_type_filter(self):
        t = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        pg = [_ev("p1", t, etype=EventType.ALERT)]
        os_ = [_ev("o1", t, source=SourceKey.OPENSEARCH, etype=EventType.ALERT)]
        loki = [_ev("l1", t, source=SourceKey.LOKI, etype=EventType.LOG)]
        res = self._run(pg=pg, os_=os_, loki=loki, types=[EventType.ALERT])
        assert {e.event_id for e in res.events} == {"p1", "o1"}
        assert all(e.event_type == EventType.ALERT for e in res.events)

    def test_cursor_pagination(self):
        t = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        evs = [_ev(f"e{i}", t + timedelta(minutes=i)) for i in range(5)]  # e4 最新 → 降序 e4,e3,e2,e1,e0
        res1 = self._run(pg=evs, limit=2)
        assert [e.event_id for e in res1.events] == ["e4", "e3"]
        assert res1.next_cursor is not None
        res2 = self._run(pg=evs, limit=2, cursor=res1.next_cursor)
        assert [e.event_id for e in res2.events] == ["e2", "e1"]
        assert res2.next_cursor is not None
        res3 = self._run(pg=evs, limit=2, cursor=res2.next_cursor)
        assert [e.event_id for e in res3.events] == ["e0"]
        assert res3.next_cursor is None
        # 三页无重叠且覆盖全集
        seen = {e.event_id for e in res1.events + res2.events + res3.events}
        assert seen == {f"e{i}" for i in range(5)}

    def test_single_source_error_isolated(self):
        """单源异常应被隔离：该源 status=error，其余源事件仍合并。"""
        t = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        pg = [_ev("p1", t)]
        loki = [_ev("l1", t, source=SourceKey.LOKI, etype=EventType.LOG)]
        mocks, patchers = _patch_adapters(pg=pg, os_=None, loki=loki)
        mocks["OSAdapter"].fetch.side_effect = RuntimeError("OS down")
        try:
            res = asyncio.run(
                TimelineService().get_timeline(
                    anchor=_anchor(),
                    start=t - timedelta(hours=1),
                    end=t + timedelta(hours=1),
                )
            )
        finally:
            for p in patchers:
                p.stop()
        assert res.source_status["opensearch"] == "error"
        assert res.source_status["pg"] == "ok"
        assert res.source_status["loki"] == "ok"
        assert {e.event_id for e in res.events} == {"p1", "l1"}

    def test_all_empty(self):
        res = self._run(pg=[], os_=[], loki=[])
        assert res.events == []
        assert res.source_status == {"pg": "empty", "opensearch": "empty", "loki": "empty"}

    def test_loki_7day_window_clip(self):
        """跨度 > 7 天时 Loki 的 start 应被裁剪到 end-7d，且 coverage_note 非空。"""
        end = datetime(2026, 2, 1, tzinfo=timezone.utc)
        start = end - timedelta(days=30)
        mocks, patchers = _patch_adapters(pg=[], os_=[], loki=[])
        try:
            res = asyncio.run(
                TimelineService().get_timeline(anchor=_anchor(), start=start, end=end)
            )
        finally:
            for p in patchers:
                p.stop()
        assert res.coverage_note != ""
        called_start = mocks["LokiAdapter"].fetch.call_args.args[1]
        assert called_start == end - timedelta(days=7)
        assert res.source_status["loki"] == "empty"

    def test_source_timeout_isolated(self):
        """G1 实证：PG 取数慢于其 3.0s 超时，应被隔离为 timeout，且不影响 OS/Loki 合并。"""
        t = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        os_ = [_ev("o1", t, source=SourceKey.OPENSEARCH)]
        loki = [_ev("l1", t, source=SourceKey.LOKI, etype=EventType.LOG)]

        def _slow_fetch(anchor, start, end):
            time.sleep(3.1)  # 超过 PG 3.0s 超时
            return [_ev("p1", t)]

        mocks, patchers = _patch_adapters(pg=None, os_=os_, loki=loki)
        mocks["PGAdapter"].fetch.side_effect = _slow_fetch
        try:
            t0 = time.monotonic()
            res = asyncio.run(
                TimelineService().get_timeline(
                    anchor=_anchor(),
                    start=t - timedelta(hours=1),
                    end=t + timedelta(hours=1),
                )
            )
            elapsed = time.monotonic() - t0
        finally:
            for p in patchers:
                p.stop()
        assert res.source_status["pg"] == "timeout"
        assert res.source_status["opensearch"] == "ok"
        assert res.source_status["loki"] == "ok"
        assert {e.event_id for e in res.events} == {"o1", "l1"}
        # 不阻塞：总耗时 < PG 睡眠时间（约 3.0s 即超时，而非等满 3.1s）
        assert elapsed < 3.5


# ---------------------------------------------------------------------------
# PGAdapter：G3 / G4 / 告警簇
# ---------------------------------------------------------------------------


class TestPGAdapter:
    def _anchor_for(self, asset):
        return AssetAnchor(asset_id=str(asset.id), ips=[asset.asset_ip])

    def test_g3_nullable_asset_id_fallback(self, db_session):
        """G3：行为画像 asset_id 可空（未纳管设备）且 ip 命中锚 IP 时仍应返回。"""
        from app.models.asset import Asset
        from app.models.behavior_profile import BehaviorProfile

        asset = Asset(
            network_segment="default", network_zone="other", asset_ip="10.0.0.55",
            asset_description="g3-host", asset_status="在线", name="g3-host",
            asset_type="server", criticality="normal",
        )
        db_session.add(asset)
        db_session.commit()
        db_session.refresh(asset)

        day = datetime(2026, 3, 10).date()
        db_session.add(BehaviorProfile(  # ① 已纳管
            asset_id=asset.id, ip=asset.asset_ip, profile_date=day,
            status="ok", total=10, confidence=80,
        ))
        db_session.add(BehaviorProfile(  # ② 未纳管但 ip 命中（G3 回退）
            asset_id=None, ip=asset.asset_ip, profile_date=day,
            status="ok", total=5, confidence=60,
        ))
        db_session.add(BehaviorProfile(  # ③ 干扰项：ip 不命中 → 不应返回
            asset_id=None, ip="9.9.9.9", profile_date=day,
            status="ok", total=1, confidence=10,
        ))
        db_session.commit()

        with patch("app.services.federation.adapters.SessionLocal", TestingSessionLocal):
            events = PGAdapter().fetch(
                self._anchor_for(asset),
                datetime(2026, 3, 9, tzinfo=timezone.utc),
                datetime(2026, 3, 11, tzinfo=timezone.utc),
            )
        bh = [e for e in events if e.event_type == EventType.BEHAVIOR]
        assert len(bh) == 2  # ① + ②，不含 ③
        assert any(e.asset_id is None for e in bh)  # ② G3 回退
        assert any(e.asset_id == str(asset.id) for e in bh)  # ①

    def test_g4_identity_event_included(self, db_session):
        """G4：身份事件（已是 PG 数据）应纳入时间线。"""
        from app.models.asset import Asset
        from app.models.identity import IdentityEvent

        asset = Asset(
            network_segment="default", network_zone="other", asset_ip="10.0.0.66",
            asset_description="g4-host", asset_status="在线", name="g4-host",
            asset_type="server", criticality="normal",
        )
        db_session.add(asset)
        db_session.commit()
        db_session.refresh(asset)

        ts = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
        # 注：IdentityEvent 模型无 asset_id 列，仅按 dst_ip/src_ip 关联资产
        db_session.add(IdentityEvent(
            es_index="wazuh-alerts-4.x-2026.04.01", es_doc_id="doc-g4",
            rule_id="5501", account="alice", src_ip="1.2.3.4",
            dst_ip=asset.asset_ip, success=True, event_type="auth_success",
            ts=ts,
        ))
        db_session.commit()

        with patch("app.services.federation.adapters.SessionLocal", TestingSessionLocal):
            events = PGAdapter().fetch(
                self._anchor_for(asset),
                datetime(2026, 3, 31, tzinfo=timezone.utc),
                datetime(2026, 4, 2, tzinfo=timezone.utc),
            )
        ids = [e for e in events if e.event_type == EventType.IDENTITY]
        assert len(ids) == 1
        assert ids[0].asset_id == str(asset.id)
        assert "alice" in ids[0].summary

    def test_alert_group_linked(self, db_session):
        """告警簇研判（linked_asset_id 关联）应纳入 PG 时间线。"""
        import uuid

        from app.models.asset import Asset
        from app.models.alert_group_analysis import AlertGroupAnalysis

        asset = Asset(
            network_segment="default", network_zone="other", asset_ip="10.0.0.77",
            asset_description="ag-host", asset_status="在线", name="ag-host",
            asset_type="server", criticality="normal",
        )
        db_session.add(asset)
        db_session.commit()
        db_session.refresh(asset)

        created = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        db_session.add(AlertGroupAnalysis(
            id=uuid.uuid4(), fingerprint=f"fp-{uuid.uuid4()}",
            priority="P2", is_noise=False, confidence=0.7, source="heuristic",
            linked_asset_id=asset.id, created_at=created,
        ))
        db_session.commit()

        with patch("app.services.federation.adapters.SessionLocal", TestingSessionLocal):
            events = PGAdapter().fetch(
                self._anchor_for(asset),
                datetime(2026, 4, 30, tzinfo=timezone.utc),
                datetime(2026, 5, 2, tzinfo=timezone.utc),
            )
        alerts = [e for e in events if e.event_type == EventType.ALERT and e.source == SourceKey.PG]
        assert len(alerts) == 1
        assert alerts[0].asset_id == str(asset.id)
        assert alerts[0].summary.startswith("告警簇研判")


# ---------------------------------------------------------------------------
# schemas：游标编解码
# ---------------------------------------------------------------------------


class TestCursorCodec:
    def test_roundtrip(self):
        t = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        cur = encode_cursor(t, "e1")
        assert decode_cursor(cur) == (t, "e1")

    def test_empty_cursor(self):
        assert decode_cursor(None) is None
        assert decode_cursor("") is None
