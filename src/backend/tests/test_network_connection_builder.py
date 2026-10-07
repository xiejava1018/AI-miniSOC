"""OH-6.6 EDR 事件入图（NetworkConnectionBuilder + WazuhClient 扩展）单测。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.graph import GraphEdge
from app.services.graph.builders import NetworkConnectionBuilder


class TestNetworkConnectionBuilder:
    def test_no_telemetry_degrades(self, db_session, monkeypatch):
        """现网现状：无 data.dstip 遥测 → 诚实降级，不建边。"""
        def empty_fetch(self):
            return []
        monkeypatch.setattr(
            NetworkConnectionBuilder, "_fetch_connections", empty_fetch)
        out = NetworkConnectionBuilder(db_session).rebuild_all()
        assert out["degraded"] is True
        assert out["connects_to_built"] == 0
        assert "无含 data.dstip" in out["error"]
        assert db_session.query(GraphEdge).filter_by(
            rel_type="connects_to").count() == 0

    def test_builds_edge_to_ip(self, db_session, monkeypatch):
        """有外联事件：主机 → ip:外联目标（未纳管 IP）。"""
        a = Asset(name="h1", asset_ip="10.2.0.1", wazuh_agent_id="001")
        db_session.add(a)
        db_session.commit()

        def fake_fetch(self):
            return [(("001", "8.8.8.8"), 42)]
        monkeypatch.setattr(
            NetworkConnectionBuilder, "_fetch_connections", fake_fetch)

        out = NetworkConnectionBuilder(db_session).rebuild_all()
        assert out["degraded"] is False
        assert out["connects_to_built"] == 1
        e = db_session.query(GraphEdge).filter_by(
            rel_type="connects_to").one()
        assert e.src_key == f"asset:{a.id}"
        assert e.dst_key == "ip:8.8.8.8"
        assert float(e.confidence) == 0.7
        assert e.evidence["event_count"] == 42
        assert "无进程归因" in e.evidence["attribution"]

    def test_builds_edge_to_managed_asset(self, db_session, monkeypatch):
        """外联目标是纳管资产 → 边指向 asset 节点（resolve_asset_or_ip_node）。"""
        src = Asset(name="src", asset_ip="10.2.0.5", wazuh_agent_id="001")
        dst = Asset(name="dst", asset_ip="10.2.0.9")
        db_session.add_all([src, dst])
        db_session.commit()

        def fake_fetch(self):
            return [(("001", "10.2.0.9"), 5)]
        monkeypatch.setattr(
            NetworkConnectionBuilder, "_fetch_connections", fake_fetch)

        out = NetworkConnectionBuilder(db_session).rebuild_all()
        assert out["connects_to_built"] == 1
        e = db_session.query(GraphEdge).filter_by(
            rel_type="connects_to").one()
        assert e.dst_key == f"asset:{dst.id}"

    def test_unknown_agent_skipped(self, db_session, monkeypatch):
        """事件的 agent 不在资产库 → 跳过不建边。"""
        def fake_fetch(self):
            return [(("999", "8.8.8.8"), 3)]
        monkeypatch.setattr(
            NetworkConnectionBuilder, "_fetch_connections", fake_fetch)
        out = NetworkConnectionBuilder(db_session).rebuild_all()
        assert out["connects_to_built"] == 0
        assert out["degraded"] is False  # 有数据但无映射，不算降级


class TestWazuhClientExtension:
    def test_get_processes_parses_snake_case(self):
        """get_processes 解析 affected_items（实测 Wazuh 4.x 为 snake_case）。"""
        from app.services.wazuh_client import WazuhClient
        wc = WazuhClient.__new__(WazuhClient)
        wc.__dict__["use_mock_data"] = False

        def fake_req(method, path, params=None):
            assert path == "/syscollector/001/processes"
            return {"data": {"affected_items": [{"name": "sshd"}]}}
        wc._request = fake_req
        assert wc.get_processes("001") == [{"name": "sshd"}]

    def test_get_ports(self):
        from app.services.wazuh_client import WazuhClient
        wc = WazuhClient.__new__(WazuhClient)
        wc.__dict__["use_mock_data"] = False

        def fake_req(method, path, params=None):
            assert path == "/syscollector/001/ports"
            return {"data": {"affected_items": [{"local": {"port": 22}}]}}
        wc._request = fake_req
        assert wc.get_ports("001") == [{"local": {"port": 22}}]
