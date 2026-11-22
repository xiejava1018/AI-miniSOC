"""暴露面分析 /exposure/rules 分页契约测试。

回归背景：该端点此前不支持分页（只按 limit 截断，total=len(items)），
导致资产管理-暴露面分析页「全量 NAT 端口映射规则」tab 分页失效
（切换每页条数 / 翻页始终返回同一份数据、20条/页出滚动条）。

覆盖：
- 未传分页参数时兼容旧行为（page_size 缺省 → limit=200，单页返回全部）
- page/page_size 生效：第1页返回前 N 条、第2页返回后续数据、无重复
- total 为过滤后的全量条数（而非当前页条数）
- 越界页返回空列表且 total 不变
- internal_ip 过滤 + 分页组合正确
"""
import pytest

from app.models.nat_mapping import NatMapping


@pytest.fixture
def authed_client(client, test_user):
    """覆盖 get_current_user 依赖（client fixture 默认不提供 token）。"""
    from app.api.deps import get_current_user

    client.app.dependency_overrides[get_current_user] = lambda: test_user
    yield client
    client.app.dependency_overrides.pop(get_current_user, None)


def _seed(db_session, n, ip="10.0.0.1"):
    rows = [
        NatMapping(
            source="tplink-router",
            wan_ip="175.11.169.102",
            wan_port=10000 + i,
            protocol="tcp",
            internal_ip=ip,
            internal_port=8000 + i,
            rule_name=f"rule-{i}",
            enabled=True,
        )
        for i in range(n)
    ]
    db_session.add_all(rows)
    # 一条禁用规则：默认 enabled_only=True 时不应计入
    db_session.add(
        NatMapping(
            source="tplink-router",
            wan_ip="175.11.169.102",
            wan_port=19999,
            protocol="tcp",
            internal_ip=ip,
            internal_port=9999,
            rule_name="disabled",
            enabled=False,
        )
    )
    db_session.commit()
    return rows


def test_no_pagination_params_keeps_legacy_single_page(authed_client, db_session):
    _seed(db_session, 5)
    r = authed_client.get("/api/v1/exposure/rules")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["total"] == 5
    assert d["page"] == 1
    assert d["page_size"] == 200
    assert len(d["items"]) == 5


def test_page_size_change_returns_correct_slice(authed_client, db_session):
    _seed(db_session, 25)
    r = authed_client.get("/api/v1/exposure/rules", params={"page": 1, "page_size": 10})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["total"] == 25  # 全量条数，而非当前页条数
    assert d["page"] == 1 and d["page_size"] == 10
    assert len(d["items"]) == 10
    ports_p1 = [x["wan_port"] for x in d["items"]]

    r2 = authed_client.get("/api/v1/exposure/rules", params={"page": 2, "page_size": 10})
    d2 = r2.json()["data"]
    assert len(d2["items"]) == 10
    ports_p2 = [x["wan_port"] for x in d2["items"]]
    # 翻页加载的是"对应页"的数据：与第1页无交集
    assert not set(ports_p1) & set(ports_p2)
    assert d2["total"] == 25

    r3 = authed_client.get("/api/v1/exposure/rules", params={"page": 3, "page_size": 10})
    d3 = r3.json()["data"]
    assert len(d3["items"]) == 5
    assert d3["total"] == 25


def test_size_20_default_returns_20_not_overflow(authed_client, db_session):
    """前端默认 20 条/页：只返回 20 条，total 为全量（滚动条来源消除）。"""
    _seed(db_session, 35)
    r = authed_client.get("/api/v1/exposure/rules", params={"page": 1, "page_size": 20})
    d = r.json()["data"]
    assert len(d["items"]) == 20
    assert d["total"] == 35


def test_out_of_range_page_empty_but_total_kept(authed_client, db_session):
    _seed(db_session, 5)
    r = authed_client.get("/api/v1/exposure/rules", params={"page": 9, "page_size": 10})
    d = r.json()["data"]
    assert d["items"] == []
    assert d["total"] == 5


def test_filter_and_pagination_combined(authed_client, db_session):
    _seed(db_session, 12, ip="10.0.0.1")
    _seed(db_session, 3, ip="10.0.0.2")
    r = authed_client.get(
        "/api/v1/exposure/rules",
        params={"internal_ip": "10.0.0.2", "page": 1, "page_size": 2},
    )
    d = r.json()["data"]
    assert d["total"] == 3
    assert len(d["items"]) == 2
    assert {x["internal_ip"] for x in d["items"]} == {"10.0.0.2"}
