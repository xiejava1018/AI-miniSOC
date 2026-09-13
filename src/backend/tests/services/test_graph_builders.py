"""资产知识图谱 - Builder 集成测试

覆盖（§8.3 测试计划 ②）：
- fixtures：10 资产 + 30 identity_events + 50 ports + 20 vulnerabilities
- 跑 5 个 builder，验证边数量、置信度分布、evidence 字段非空
- 验证 (src_key, dst_key, rel_type) 唯一性（无重复三元组）
- 验证 resolve_asset_or_ip_node：同一 IP 只产生一个 node_key（无分叉）
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import (
    Asset,
    AssetPort,
    AssetTag,
    AssetVulnerability,
    IdentityBinding,
    IdentityEvent,
    Vulnerability,
)
from app.services.graph.builders import (
    AssetPortVulnBuilder,
    IdentityGraphBuilder,
    TopologyBuilder,
    ManualRelationBuilder,
    run_all_builders,
)


def _make_asset(db, ip: str, segment: str = "x", criticality: str = "medium",
                owner_id: int | None = None) -> Asset:
    a = Asset(
        asset_ip=ip,
        name=f"host-{ip}",
        network_segment=segment,
        criticality=criticality,
        owner_id=owner_id,
    )
    db.add(a)
    db.flush()
    return a


# ---------------------------------------------------------------------------
# AssetPortVulnBuilder
# ---------------------------------------------------------------------------


class TestAssetPortVulnBuilder:
    def test_has_port_edges(self, db_session):
        a = _make_asset(db_session, "192.168.1.10")
        for port in (22, 80, 443):
            db_session.add(AssetPort(
                asset_id=a.id, asset_ip=a.asset_ip,
                port=port, protocol="tcp", state="open",
            ))
        db_session.commit()
        builder = AssetPortVulnBuilder(db_session)
        builder.rebuild_all()
        db_session.commit()
        from app.models import GraphEdge
        edges = db_session.query(GraphEdge).filter_by(
            rel_type="has_port"
        ).all()
        assert len(edges) == 3
        for e in edges:
            assert e.confidence == 1.0
            assert e.evidence  # 非空
            assert "table" in e.evidence

    def test_has_vuln_and_port_has_vuln(self, db_session):
        a = _make_asset(db_session, "192.168.1.20")
        # 1 端口
        p = AssetPort(
            asset_id=a.id, asset_ip=a.asset_ip,
            port=22, protocol="tcp", state="open",
            vulnerabilities=["CVE-2023-44487"],
        )
        db_session.add(p)
        # 1 漏洞
        v = Vulnerability(
            cve_id="CVE-2023-44487", title="Test CVE",
            severity="high", cvss_score=7.5,
        )
        db_session.add(v)
        db_session.flush()
        db_session.add(AssetVulnerability(
            asset_id=a.id, vulnerability_id=v.id,
            scanner="wazuh", status="open",
        ))
        db_session.commit()

        builder = AssetPortVulnBuilder(db_session)
        builder.rebuild_all()
        db_session.commit()
        from app.models import GraphEdge
        has_vuln = db_session.query(GraphEdge).filter_by(rel_type="has_vuln").all()
        port_has_vuln = db_session.query(GraphEdge).filter_by(rel_type="port_has_vuln").all()
        assert len(has_vuln) >= 1
        assert any(e.confidence == 1.0 for e in has_vuln)
        # port_has_vuln 通过 vulnerabilities JSONB 匹配 CVE-2023-44487
        assert len(port_has_vuln) >= 1
        assert any(e.confidence == 0.9 for e in port_has_vuln)


# ---------------------------------------------------------------------------
# IdentityGraphBuilder
# ---------------------------------------------------------------------------


class TestIdentityGraphBuilder:
    def test_login_to_edges_from_events(self, db_session):
        a = _make_asset(db_session, "192.168.1.30")
        # 30 个事件：成功登录某账号
        for i in range(30):
            db_session.add(IdentityEvent(
                es_index="wazuh-2026.01", es_doc_id=f"doc-{i}",
                account="alice@corp", src_ip="192.168.1.5",
                dst_ip="192.168.1.30", success=(i % 3 != 0),
                ts=datetime.now(timezone.utc) - timedelta(hours=i),
                event_type="auth_success",
            ))
        db_session.commit()
        builder = IdentityGraphBuilder(db_session, window_days=30)
        stats = builder.rebuild_all()
        db_session.commit()
        from app.models import GraphEdge
        login_to = db_session.query(GraphEdge).filter_by(rel_type="login_to").all()
        assert len(login_to) >= 1
        assert stats["login_to_built"] >= 1
        # 验证 evidence 包含 success/fail/sample_ids
        e = login_to[0]
        assert e.evidence["count"] == 30
        assert e.evidence["success"] > 0
        assert e.evidence["fail"] > 0
        assert "sample_ids" in e.evidence

    def test_external_access_only_external_ips(self, db_session):
        a = _make_asset(db_session, "192.168.1.40")
        # 10 个内网 src_ip → 不应产生 external_access 边
        for i in range(10):
            db_session.add(IdentityEvent(
                es_index="wazuh-2026.01", es_doc_id=f"ev-{i}",
                account="bob@corp", src_ip="10.0.0.5",  # 内网
                dst_ip="192.168.1.40", success=True,
                ts=datetime.now(timezone.utc) - timedelta(hours=i),
            ))
        # 5 个外网 src_ip → 应产生 external_access 边
        for i in range(5):
            db_session.add(IdentityEvent(
                es_index="wazuh-2026.01", es_doc_id=f"ext-{i}",
                account="bob@corp", src_ip="8.8.8.8",  # 外网
                dst_ip="192.168.1.40", success=True,
                ts=datetime.now(timezone.utc) - timedelta(hours=i),
            ))
        db_session.commit()
        builder = IdentityGraphBuilder(db_session, window_days=30)
        stats = builder.rebuild_all()
        db_session.commit()
        from app.models import GraphEdge
        ext = db_session.query(GraphEdge).filter_by(rel_type="external_access").all()
        from_internal = db_session.query(GraphEdge).filter_by(rel_type="login_from").all()
        assert stats["external_access_built"] == 1  # 同一 src+dst 聚合为 1
        assert len(ext) >= 1
        assert ext[0].evidence["count"] == 5
        assert len(from_internal) >= 1  # login_from 也有

    def test_session_on_from_bindings(self, db_session):
        a = _make_asset(db_session, "192.168.1.50")
        db_session.add(IdentityBinding(
            account="carol@corp", ip="192.168.1.50",
            asset_id=a.id, logins=100,
        ))
        db_session.commit()
        builder = IdentityGraphBuilder(db_session, window_days=30)
        builder.rebuild_all()
        db_session.commit()
        from app.models import GraphEdge
        e = db_session.query(GraphEdge).filter_by(rel_type="session_on").first()
        assert e is not None
        assert e.evidence["logins"] == 100
        assert e.expires_at is not None  # 有衰减


# ---------------------------------------------------------------------------
# TopologyBuilder
# ---------------------------------------------------------------------------


class TestTopologyBuilder:
    def test_same_segment_undirected(self, db_session):
        for ip in ("192.168.1.60", "192.168.1.61", "192.168.1.62"):
            _make_asset(db_session, ip, segment="3F")
        db_session.commit()
        builder = TopologyBuilder(db_session)
        stats = builder.rebuild_all()
        db_session.commit()
        from app.models import GraphEdge
        edges = db_session.query(GraphEdge).filter_by(rel_type="same_segment").all()
        # 3 资产两两相连 → 3 条边
        assert stats["same_segment_built"] == 3
        assert all(e.direction == "undirected" for e in edges)
        assert all(e.confidence == 0.5 for e in edges)

    def test_shared_tag_edges(self, db_session):
        a = _make_asset(db_session, "192.168.1.70")
        b = _make_asset(db_session, "192.168.1.71")
        c = _make_asset(db_session, "192.168.1.72")
        for x in (a, b, c):
            db_session.add(AssetTag(asset_id=x.id, tag_key="env", tag_value="prod"))
        db_session.commit()
        builder = TopologyBuilder(db_session)
        stats = builder.rebuild_all()
        db_session.commit()
        from app.models import GraphEdge
        edges = db_session.query(GraphEdge).filter_by(rel_type="shared_tag").all()
        assert stats["shared_tag_built"] >= 1
        assert all(e.confidence == 0.4 for e in edges)


# ---------------------------------------------------------------------------
# 跨 builder 不分叉验证
# ---------------------------------------------------------------------------


class TestNoNodeFork:
    """resolve_asset_or_ip_node 必须保证同一 IP 只产生一种 node_key。"""
    def test_same_ip_one_node(self, db_session):
        a = _make_asset(db_session, "192.168.1.100")
        b = _make_asset(db_session, "192.168.1.101")
        # A → B（A→B login 事件）
        db_session.add(IdentityEvent(
            es_index="wazuh-2026.01", es_doc_id="x-1",
            account="eve@corp", src_ip="192.168.1.200", dst_ip="192.168.1.100",
            success=True, ts=datetime.now(timezone.utc),
        ))
        # B 登录到 A
        db_session.add(IdentityEvent(
            es_index="wazuh-2026.01", es_doc_id="x-2",
            account="eve@corp", src_ip="192.168.1.101", dst_ip="192.168.1.100",
            success=True, ts=datetime.now(timezone.utc),
        ))
        db_session.commit()
        IdentityGraphBuilder(db_session, window_days=30).rebuild_all()
        TopologyBuilder(db_session).rebuild_all()
        db_session.commit()
        from app.services.graph.utils import resolve_asset_or_ip_node
        # 同一 IP 192.168.1.100 必须映射到 asset:xxx，且只有这一个 node_key
        key = resolve_asset_or_ip_node(db_session, "192.168.1.100")
        assert key == f"asset:{a.id}"
        from app.models import GraphNode
        # 没有 ip:192.168.1.100 这个节点
        ip_node = db_session.query(GraphNode).filter_by(
            node_key="ip:192.168.1.100").first()
        assert ip_node is None
        # 有 asset:xxx 节点
        asset_node = db_session.query(GraphNode).filter_by(node_key=key).first()
        assert asset_node is not None


# ---------------------------------------------------------------------------
# 唯一性约束
# ---------------------------------------------------------------------------


class TestUniqueConstraint:
    def test_unique_src_dst_rel(self, db_session):
        """(src, dst, rel_type) 唯一：重复 upsert 不产生重复边。"""
        from app.services.graph import ensure_node, upsert_edge
        ensure_node(db_session, "asset:u-1", "asset", "U1")
        ensure_node(db_session, "asset:u-2", "asset", "U2")
        db_session.commit()
        for _ in range(3):
            upsert_edge(db_session, "asset:u-1", "asset:u-2", "has_port",
                       confidence=0.9, sources=["wazuh"])
        db_session.commit()
        from app.models import GraphEdge
        edges = db_session.query(GraphEdge).filter_by(
            src_key="asset:u-1", dst_key="asset:u-2", rel_type="has_port"
        ).all()
        assert len(edges) == 1  # 唯一约束生效


# ---------------------------------------------------------------------------
# run_all_builders 烟测
# ---------------------------------------------------------------------------


def test_run_all_builders_smoke(db_session):
    """run_all_builders 5 个 builder 全跑通，不抛异常。"""
    a = _make_asset(db_session, "192.168.1.110")
    _make_asset(db_session, "192.168.1.111", segment="3F")
    db_session.add(AssetPort(asset_id=a.id, asset_ip=a.asset_ip,
                             port=22, protocol="tcp", state="open"))
    db_session.commit()
    stats = run_all_builders(db_session)
    db_session.commit()
    assert "asset_port_vuln" in stats
    assert "identity" in stats
    assert "topology" in stats
    assert "alert_group" in stats
    assert "manual" in stats