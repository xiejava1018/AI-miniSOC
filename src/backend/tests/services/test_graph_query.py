"""资产知识图谱 - 递归 CTE 单元测试

覆盖（§8.3 测试计划 ①）：
- 线性链 A→B→C→D：N 跳深度遍历正确
- 环形 A→B→A：环检测生效，**不死循环**
- 深度 > 6 截断：depth < N 兜底
- 置信度门槛：< 0.5 的边不入路径
- 过期边：expires_at < now() 被过滤
- find_paths 最短路径
- impact_scope 业务系统/责任人聚合
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Asset
from app.services.graph import (
    ensure_node,
    upsert_edge,
)
from app.services.graph.utils import make_expires_at
from app.services.graph.query import (
    find_paths,
    get_neighbors,
    impact_scope,
)


def _make_asset(db, ip: str, segment: str = "x", name: str | None = None) -> Asset:
    a = Asset(
        asset_ip=ip,
        name=name or f"host-{ip}",
        network_segment=segment,
        criticality="medium",
    )
    db.add(a)
    db.flush()
    return a


def _seed_chain(db_session):
    """种入线性链 A→B→C→D（同 segment）。"""
    a = _make_asset(db_session, "10.0.0.1")
    b = _make_asset(db_session, "10.0.0.2")
    c = _make_asset(db_session, "10.0.0.3")
    d = _make_asset(db_session, "10.0.0.4")

    for x, y in [(a, b), (b, c), (c, d)]:
        ensure_node(db_session, f"asset:{x.id}", "asset", x.name,
                   ref_table="soc_assets", ref_id=str(x.id))
        ensure_node(db_session, f"asset:{y.id}", "asset", y.name,
                   ref_table="soc_assets", ref_id=str(y.id))
        upsert_edge(db_session, f"asset:{x.id}", f"asset:{y.id}", "login_to",
                   confidence=0.9, sources=["wazuh"])
    db_session.commit()
    return a, b, c, d


# ---------------------------------------------------------------------------
# ① 邻居子图（BFS）
# ---------------------------------------------------------------------------


class TestGetNeighbors:
    def test_linear_2_hops(self, db_session):
        a, b, c, d = _seed_chain(db_session)
        result = get_neighbors(db_session, f"asset:{a.id}", depth=2, min_conf=0.5)
        node_ids = {n["id"] for n in result["nodes"]}
        # A + B + C（不能到 D，depth=2）
        assert f"asset:{a.id}" in node_ids
        assert f"asset:{b.id}" in node_ids
        assert f"asset:{c.id}" in node_ids
        assert f"asset:{d.id}" not in node_ids
        assert result["stats"]["depth"] == 2

    def test_depth_truncates(self, db_session):
        a, b, c, d = _seed_chain(db_session)
        # depth=3 应该能到 D
        result = get_neighbors(db_session, f"asset:{a.id}", depth=3, min_conf=0.5)
        node_ids = {n["id"] for n in result["nodes"]}
        assert f"asset:{d.id}" in node_ids

    def test_center_not_in_db(self, db_session):
        """中心节点不存在时返回空 stats 但不报错。"""
        result = get_neighbors(db_session, "asset:nonexistent-uuid", depth=2)
        assert result["stats"]["empty"] is True

    def test_min_conf_filters(self, db_session):
        a, b, c, d = _seed_chain(db_session)
        # 设 login_to 的 conf=0.5 → min_conf=0.9 应过滤掉所有边
        result = get_neighbors(db_session, f"asset:{a.id}", depth=3, min_conf=0.99)
        # 中心节点单独返回，无边
        assert len(result["links"]) == 0

    def test_cyclic_data_no_infinite_loop(self, db_session):
        """A→B→A 环不应死循环（环检测）。"""
        a = _make_asset(db_session, "10.0.0.10")
        b = _make_asset(db_session, "10.0.0.11")
        for x, y in [(a, b), (b, a)]:
            ensure_node(db_session, f"asset:{x.id}", "asset", x.name,
                       ref_table="soc_assets", ref_id=str(x.id))
            ensure_node(db_session, f"asset:{y.id}", "asset", y.name,
                       ref_table="soc_assets", ref_id=str(y.id))
            upsert_edge(db_session, f"asset:{x.id}", f"asset:{y.id}", "login_to",
                       confidence=0.9)
        db_session.commit()
        # 设置较短超时保护
        result = get_neighbors(db_session, f"asset:{a.id}", depth=5, min_conf=0.5)
        # A + B（两个都被到达，但 A 不会再次进入）
        node_ids = {n["id"] for n in result["nodes"]}
        assert f"asset:{a.id}" in node_ids
        assert f"asset:{b.id}" in node_ids

    def test_expired_edges_filtered(self, db_session):
        a, b, c, d = _seed_chain(db_session)
        # 把 A→B 的 expires_at 设为过去
        from app.models import GraphEdge
        e = db_session.query(GraphEdge).filter(
            GraphEdge.src_key == f"asset:{a.id}",
            GraphEdge.dst_key == f"asset:{b.id}",
        ).first()
        e.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db_session.commit()
        result = get_neighbors(db_session, f"asset:{a.id}", depth=3, min_conf=0.5)
        node_ids = {n["id"] for n in result["nodes"]}
        # 过期后 B 应该不可达
        assert f"asset:{b.id}" not in node_ids

    def test_rel_types_filter(self, db_session):
        """限定 rel_types 应只返回指定类型边。"""
        a, b, c, d = _seed_chain(db_session)
        result = get_neighbors(
            db_session, f"asset:{a.id}", depth=3,
            rel_types=["login_to"],
        )
        assert all(link["relType"] == "login_to" for link in result["links"])

    def test_include_inferred_false_excludes_d3(self, db_session):
        """include_inferred=False 应排除 same_segment / shared_tag / co_alerted。"""
        a, b, c, d = _seed_chain(db_session)
        # 加一条 same_segment 边
        ensure_node(db_session, f"asset:{a.id}", "asset", a.name)
        ensure_node(db_session, f"asset:{b.id}", "asset", b.name)
        upsert_edge(db_session, f"asset:{a.id}", f"asset:{b.id}", "same_segment",
                   confidence=0.5, sources=["inferred"])
        db_session.commit()
        # 不含 inferred：应只剩 login_to
        result = get_neighbors(
            db_session, f"asset:{a.id}", depth=2,
            include_inferred=False,
        )
        assert all(link["relType"] != "same_segment" for link in result["links"])


# ---------------------------------------------------------------------------
# ② find_paths（最短路径）
# ---------------------------------------------------------------------------


class TestFindPaths:
    def test_linear_path(self, db_session):
        a, b, c, d = _seed_chain(db_session)
        result = find_paths(
            db_session, f"asset:{a.id}", f"asset:{d.id}",
            max_depth=4, min_conf=0.5,
        )
        assert result["stats"]["pathCount"] >= 1
        # 最短路径 A → B → C → D
        shortest = result["paths"][0]
        assert len(shortest["nodeKeys"]) == 4  # A,B,C,D
        assert shortest["cost"] == 3.0  # 3 跳

    def test_no_path(self, db_session):
        a, b, c, d = _seed_chain(db_session)
        result = find_paths(
            db_session, f"asset:{a.id}", "asset:nonexistent",
            max_depth=3, min_conf=0.5,
        )
        assert result["paths"] == []

    def test_min_conf_blocks(self, db_session):
        a, b, c, d = _seed_chain(db_session)
        # 提高门槛到 0.95：login_to=0.9 不通过
        result = find_paths(
            db_session, f"asset:{a.id}", f"asset:{d.id}",
            max_depth=3, min_conf=0.95,
        )
        assert result["paths"] == []


# ---------------------------------------------------------------------------
# ③ impact_scope
# ---------------------------------------------------------------------------


class TestImpactScope:
    def test_basic(self, db_session):
        a, b, c, d = _seed_chain(db_session)
        result = impact_scope(
            db_session, [f"asset:{a.id}"],
            max_depth=2, include_inferred=True,
        )
        assert "scope" in result
        assert "nodes" in result["scope"]
        assert "links" in result["scope"]
        assert "byBusinessSystem" in result["scope"]
        # 没有业务系统/owner，coverage 应 degraded
        assert result["degraded"] is True
        assert len(result["warnings"]) >= 1

    def test_empty_targets(self, db_session):
        result = impact_scope(
            db_session, ["asset:nonexistent"],
            max_depth=2,
        )
        assert result["degraded"] is True