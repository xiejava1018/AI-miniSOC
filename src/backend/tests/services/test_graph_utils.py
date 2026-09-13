"""资产知识图谱 - utils/coverage 单元测试

覆盖（§8.3 测试计划 ①）：
- 节点归并：同 IP 在不同 builder 只产生一种 node_key
- 外网 IP 判定：内网/外网正确分类
- compute_topology_coverage：去降级公式（精确）
- 边衰减窗口：rel_type → expires_at
- 边 upsert：sources / evidence / last_seen_by_source 合并
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Asset
from app.services.graph.coverage import compute_topology_coverage, D1_D2_TYPES
from app.services.graph.utils import (
    ATTACK_EDGE_TYPES,
    D1_TYPES,
    D2_TYPES,
    EDGE_DECAY_DAYS,
    INFERRED_TYPES,
    ensure_node,
    is_external_ip,
    make_expires_at,
    resolve_asset_or_ip_node,
    upsert_edge,
)


# ---------------------------------------------------------------------------
# is_external_ip
# ---------------------------------------------------------------------------


class TestIsExternalIp:
    def test_public_ipv4(self):
        assert is_external_ip("8.8.8.8") is True
        assert is_external_ip("1.1.1.1") is True
        assert is_external_ip("208.67.222.222") is True

    def test_private_ipv4(self):
        assert is_external_ip("192.168.1.1") is False
        assert is_external_ip("10.0.0.5") is False
        assert is_external_ip("172.16.0.10") is False
        assert is_external_ip("127.0.0.1") is False
        assert is_external_ip("169.254.0.1") is False  # link-local
        assert is_external_ip("100.64.0.1") is False   # CGNAT

    def test_ipv6(self):
        assert is_external_ip("2001:4860:4860::8888") is True
        assert is_external_ip("fe80::1") is False      # link-local
        assert is_external_ip("fc00::1") is False      # ULA

    def test_invalid_ip(self):
        assert is_external_ip("not.an.ip") is False
        assert is_external_ip("") is False
        assert is_external_ip("999.999.999.999") is False


# ---------------------------------------------------------------------------
# resolve_asset_or_ip_node
# ---------------------------------------------------------------------------


class TestResolveAssetOrIpNode:
    def test_unmanaged_ip(self, db_session):
        assert resolve_asset_or_ip_node(db_session, "8.8.8.8") == "ip:8.8.8.8"

    def test_managed_ip(self, db_session):
        a = Asset(asset_ip="192.168.1.100", name="test", network_segment="x",
                  criticality="medium")
        db_session.add(a)
        db_session.flush()
        result = resolve_asset_or_ip_node(db_session, "192.168.1.100")
        assert result == f"asset:{a.id}"

    def test_empty_ip(self, db_session):
        assert resolve_asset_or_ip_node(db_session, "") == "ip:_unknown"


# ---------------------------------------------------------------------------
# compute_topology_coverage（§6.7.3 精确公式）
# ---------------------------------------------------------------------------


class _FakeEdge:
    def __init__(self, rel_type: str, confidence: float = 0.9):
        self.rel_type = rel_type
        self.confidence = confidence


class TestComputeTopologyCoverage:
    def test_empty(self):
        r = compute_topology_coverage([])
        assert r["degraded"] is True
        assert len(r["warnings"]) == 3  # 三个核心边都缺失
        assert r["score"] == 0.0

    def test_full_coverage(self):
        edges = [
            _FakeEdge("has_port", 1.0),
            _FakeEdge("belongs_to_system", 1.0),
            _FakeEdge("owned_by", 1.0),
            _FakeEdge("login_to", 1.0),
            _FakeEdge("has_vuln", 1.0),
        ]
        r = compute_topology_coverage(edges)
        assert r["degraded"] is False
        assert r["warnings"] == []
        assert r["score"] == 1.0
        assert r["bonus_ok"] is True

    def test_missing_owner_only(self):
        edges = [
            _FakeEdge("has_port", 1.0),
            _FakeEdge("belongs_to_system", 1.0),
            _FakeEdge("login_to", 1.0),
            _FakeEdge("has_vuln", 1.0),
        ]
        r = compute_topology_coverage(edges)
        assert r["degraded"] is True
        assert len(r["warnings"]) == 1
        assert r["warnings"][0]["code"] == "MISSING_OWNED_BY"
        # 2 核心 + 1 加分 = 3/4
        assert r["score"] == 0.75

    def test_low_confidence_excluded(self):
        """置信度 < 0.7 的 D1 边不应计为核心覆盖"""
        edges = [
            _FakeEdge("has_port", 0.5),  # 低于 0.7 门槛
            _FakeEdge("belongs_to_system", 1.0),
            _FakeEdge("owned_by", 1.0),
        ]
        r = compute_topology_coverage(edges)
        assert r["degraded"] is True
        assert any(w["code"] == "MISSING_HAS_PORT" for w in r["warnings"])

    def test_d3_not_counted(self):
        """D3 推断边不入覆盖度判定"""
        edges = [
            _FakeEdge("same_segment", 0.9),
            _FakeEdge("shared_tag", 0.9),
        ]
        r = compute_topology_coverage(edges)
        # D3 不在 D1_D2_TYPES 里 → 全部核心缺失
        assert r["degraded"] is True
        assert len(r["warnings"]) == 3

    def test_bonus_missing(self):
        """有 has_port 但没 login_to + has_vuln → bonus 不满足 → degraded"""
        edges = [
            _FakeEdge("has_port", 1.0),
            _FakeEdge("belongs_to_system", 1.0),
            _FakeEdge("owned_by", 1.0),
        ]
        r = compute_topology_coverage(edges)
        assert r["degraded"] is True
        assert r["bonus_ok"] is False
        # 3 核心 + 0 加分 = 3/4
        assert r["score"] == 0.75


# ---------------------------------------------------------------------------
# 边衰减窗口（§6.3.2 规则卡）
# ---------------------------------------------------------------------------


class TestEdgeDecay:
    def test_decay_windows(self):
        assert EDGE_DECAY_DAYS["login_to"] == 30
        assert EDGE_DECAY_DAYS["login_from"] == 30
        assert EDGE_DECAY_DAYS["external_access"] == 7
        assert EDGE_DECAY_DAYS["session_on"] == 90
        assert EDGE_DECAY_DAYS["alerted_on"] == 90

    def test_no_decay_for_d1(self):
        """D1 永久类边没有衰减"""
        for rt in ("has_port", "has_vuln", "port_has_vuln",
                   "belongs_to_system", "owned_by", "runs_on"):
            assert EDGE_DECAY_DAYS.get(rt) is None

    def test_make_expires_at(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        e = make_expires_at("external_access", base)
        assert e == base + timedelta(days=7)
        e = make_expires_at("has_port", base)
        assert e is None  # 永久


# ---------------------------------------------------------------------------
# ensure_node / upsert_edge（幂等性）
# ---------------------------------------------------------------------------


class TestEnsureNode:
    def test_insert_and_update(self, db_session):
        ensure_node(db_session, "asset:test-uuid-1", "asset", "test-host-1",
                   ref_table="soc_assets", ref_id="test-uuid-1",
                   props={"ip": "1.2.3.4"})
        db_session.commit()
        # 第二次调用：label 应更新
        ensure_node(db_session, "asset:test-uuid-1", "asset", "renamed",
                   ref_table="soc_assets", ref_id="test-uuid-1",
                   props={"ip": "1.2.3.5"})
        db_session.commit()
        from app.models import GraphNode
        node = db_session.query(GraphNode).filter_by(
            node_key="asset:test-uuid-1").first()
        assert node.label == "renamed"
        assert node.props["ip"] == "1.2.3.5"


class TestUpsertEdge:
    def test_create_new(self, db_session):
        ensure_node(db_session, "asset:a", "asset", "A")
        ensure_node(db_session, "asset:b", "asset", "B")
        db_session.commit()
        upsert_edge(db_session, "asset:a", "asset:b", "same_segment",
                   confidence=0.5, sources=["wazuh"], evidence={"count": 5})
        db_session.commit()
        from app.models import GraphEdge
        edges = db_session.query(GraphEdge).all()
        assert len(edges) == 1
        assert edges[0].confidence == 0.5
        assert edges[0].evidence["count"] == 5

    def test_merge_sources(self, db_session):
        ensure_node(db_session, "asset:x", "asset", "X")
        ensure_node(db_session, "asset:y", "asset", "Y")
        db_session.commit()
        upsert_edge(db_session, "asset:x", "asset:y", "has_port",
                   sources=["wazuh"], evidence={"count": 1})
        db_session.commit()
        upsert_edge(db_session, "asset:x", "asset:y", "has_port",
                   sources=["manual"], evidence={"count": 5})
        db_session.commit()
        from app.models import GraphEdge
        e = db_session.query(GraphEdge).first()
        assert set(e.sources) == {"wazuh", "manual"}
        # count 取较大者
        assert e.evidence["count"] == 5

    def test_confidence_take_max(self, db_session):
        ensure_node(db_session, "asset:p", "asset", "P")
        ensure_node(db_session, "asset:q", "asset", "Q")
        db_session.commit()
        upsert_edge(db_session, "asset:p", "asset:q", "has_port",
                   confidence=0.5)
        db_session.commit()
        upsert_edge(db_session, "asset:p", "asset:q", "has_port",
                   confidence=0.9)
        db_session.commit()
        from app.models import GraphEdge
        e = db_session.query(GraphEdge).first()
        assert e.confidence == 0.9


# ---------------------------------------------------------------------------
# 常量分档
# ---------------------------------------------------------------------------


class TestTypeCategories:
    def test_d1_d2_disjoint(self):
        assert D1_TYPES & D2_TYPES == set()

    def test_attack_types_is_d1_d2(self):
        assert ATTACK_EDGE_TYPES == (D1_TYPES | D2_TYPES)

    def test_inferred_types_distinct(self):
        assert INFERRED_TYPES & ATTACK_EDGE_TYPES == set()