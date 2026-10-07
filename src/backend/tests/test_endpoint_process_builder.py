"""OH-3.9 端点行为图（EndpointProcessBuilder）单测。

mock WazuhClient._request，不真实调 Wazuh。
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.graph import GraphEdge, GraphNode
from app.services.graph.builders import EndpointProcessBuilder


def _asset(db, name, ip, agent):
    a = Asset(name=name, asset_ip=ip, wazuh_agent_id=agent)
    db.add(a)
    db.flush()
    return a


def _procs(names):
    return [{"name": n, "pid": str(i), "euser": "root"}
            for i, n in enumerate(names)]


class _FakeWazuhClient:
    """替身类：构造无参；_request 按 agent 返回固定进程清单；'bad' 抛错。"""

    pages = {
        "001": _procs(["sshd", "nginx", "sshd"]),  # 重复名聚合
    }

    def get_processes(self, agent_id: str, limit: int = 500):
        if agent_id == "bad":
            raise RuntimeError("400 Bad Request")
        return self.pages.get(agent_id, _procs([]))


class TestEndpointProcessBuilder:
    def test_creates_edges_built(self, db_session, monkeypatch):
        a1 = _asset(db_session, "host1", "10.1.1.1", "001")
        a2 = _asset(db_session, "host2", "10.1.1.2", "bad")
        db_session.commit()

        import importlib
        wc_mod = importlib.import_module("app.services.wazuh_client")
        fake_cls = type("FakeWazuh", (_FakeWazuhClient,), {})
        monkeypatch.setattr(wc_mod, "WazuhClient", fake_cls)

        out = EndpointProcessBuilder(db_session).rebuild_all()

        assert out["agents_scanned"] == 2
        assert out["degraded"] is True  # bad agent 拉取失败
        # host1：sshd 聚合去重 + nginx → 2 个进程 2 条边
        assert out["processes_built"] == 2
        assert out["creates_built"] == 2

        edges = db_session.query(GraphEdge).filter(
            GraphEdge.rel_type == "creates").all()
        assert len(edges) == 2
        pkeys = {e.dst_key for e in edges}
        assert pkeys == {f"process:001:sshd", "process:001:nginx"}
        # 边置信度 / 来源
        for e in edges:
            assert float(e.confidence) == 0.9
            assert "wazuh" in (e.sources or [])

        # 进程节点存在且类型正确
        nodes = db_session.query(GraphNode).filter(
            GraphNode.node_type == "process").all()
        assert {n.node_key for n in nodes} == pkeys

    def test_aggregation_pid_count(self, db_session, monkeypatch):
        a1 = _asset(db_session, "h", "10.1.1.9", "001")
        db_session.commit()
        import importlib
        wc_mod = importlib.import_module("app.services.wazuh_client")
        fake_cls = type("FakeWazuh", (_FakeWazuhClient,), {})
        monkeypatch.setattr(wc_mod, "WazuhClient", fake_cls)
        EndpointProcessBuilder(db_session).rebuild_all()

        n = db_session.query(GraphNode).filter(
            GraphNode.node_key == "process:001:sshd").one()
        assert n.props["pid_count"] == 2  # 两个 sshd 进程聚合
        assert n.props["eusers"] == ["root"]

    def test_truncation_cap(self, db_session, monkeypatch):
        a1 = _asset(db_session, "h2", "10.1.1.10", "001")
        db_session.commit()
        import importlib
        wc_mod = importlib.import_module("app.services.wazuh_client")
        fake_cls = type("FakeWazuh", (_FakeWazuhClient,), {})
        fake_cls.pages = {"001": _procs([f"p{i}" for i in range(50)])}
        monkeypatch.setattr(wc_mod, "WazuhClient", fake_cls)
        out = EndpointProcessBuilder(
            db_session, max_processes_per_agent=10).rebuild_all()
        assert out["truncated_agents"] == 1
        assert out["processes_built"] == 10

    def test_no_assets(self, db_session):
        out = EndpointProcessBuilder(db_session).rebuild_all()
        assert out["agents_scanned"] == 0
        assert "无 wazuh_agent_id" in out["error"]
