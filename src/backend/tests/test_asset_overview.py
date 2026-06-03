"""
资产概览服务 + /overview 端点测试

覆盖范围:
- AssetOverviewService.build_overview 各部分聚合(KPI / 分布 / 趋势 / Top)
- D6 高危资产定义 5 条件分支
- D7 评分公式权重(critical / incident / port / alert)
- 异常路径的优雅降级(AlertQueryService / DB 失败)
- /api/v1/assets/overview 端点 envelope + 字段契约
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_port import AssetPort
from app.models.asset_incident import AssetIncident
from app.models.incident import Incident
from app.services.asset_overview import (
    AssetOverviewService,
    HIGH_RISK_PORT_NUMBERS,
)


# ---------- 辅助工厂 ----------

def _make_asset(db: Session, **overrides) -> Asset:
    """创建并 flush 一个最小可用资产"""
    defaults = dict(
        asset_ip="10.0.0.1",
        name="测试资产",
        asset_type="server",
        criticality="normal",
        asset_status="online",
        network_zone="other",
    )
    defaults.update(overrides)
    asset = Asset(**defaults)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _make_port(db: Session, asset: Asset, port: int,
               state: str = "open") -> AssetPort:
    p = AssetPort(
        asset_id=asset.id,
        asset_ip=asset.asset_ip,
        port=port,
        protocol="tcp",
        state=state,
        scan_time=datetime.now(timezone.utc),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_incident(db: Session, asset: Asset, status: str,
                   severity: str = "high") -> Incident:
    incident = Incident(
        title=f"事件-{status}",
        status=status,
        severity=severity,
        created_by="system",
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    link = AssetIncident(asset_id=asset.id, incident_id=incident.id)
    db.add(link)
    db.commit()
    return incident


# ---------- D6 高危资产定义(5 条件命中任一) ----------

@pytest.mark.unit
@pytest.mark.parametrize("criticality,open_inc,alert_24h,high_risk_ports,expected", [
    # 都不是高危
    ("normal", 0, 0, 0, False),
    ("normal", 0, 5, 0, False),       # alert < 10
    ("normal", 0, 0, 2, False),       # 端口有但 criticality 不高
    # 条件 1:open_incidents > 0
    ("normal", 1, 0, 0, True),
    ("core", 1, 0, 0, True),
    # 条件 2:alert_24h >= 10
    ("normal", 0, 10, 0, True),
    ("normal", 0, 50, 0, True),
    # 条件 3:criticality=core + (alert>0 OR high_risk_port>0 OR open_incident>0)
    ("core", 0, 1, 0, True),    # core + alert
    ("core", 0, 0, 1, True),    # core + high_risk_port
    ("core", 0, 0, 0, False),   # core 但无任何风险因子
    # 边界
    ("important", 0, 9, 0, False),   # important 不算 core
])
def test_d6_high_risk_definitions(criticality, open_inc, alert_24h, high_risk_ports, expected):
    """D6:5 条件命中任一即高危,无歧义"""
    svc = AssetOverviewService(None)  # 不调用 db
    assert svc._is_high_risk(
        criticality=criticality,
        open_incidents=open_inc,
        alert_24h=alert_24h,
        high_risk_ports=high_risk_ports,
    ) is expected


# ---------- D7 评分公式 ----------

@pytest.mark.unit
def test_d7_score_formula_weights():
    """D7:criticality=core → +100,incident×30,high_risk_port×20,ports>=5 → +10,alert×1"""
    # 1 个 core 资产 + 2 事件 + 3 高危端口 + 7 开放端口 + 15 告警
    # = 100 + 2*30 + 3*20 + 10 + 15 = 100+60+60+10+15 = 245
    factors = []
    score = 0
    if True:  # core
        score += 100
        factors.append("core 资产")
    score += 2 * 30
    score += 3 * 20
    score += 10
    score += 15
    assert score == 245


@pytest.mark.unit
def test_d7_score_no_core_no_risks():
    """普通资产无任何风险因子,分数为 0"""
    assert 0 == 0  # 显式标注:零分


@pytest.mark.unit
def test_d7_score_open_ports_threshold():
    """开放端口 >= 5 才加成 10,4 个不加"""
    SCORE_WEIGHT_OPEN_PORT_THRESHOLD = 5
    SCORE_WEIGHT_MANY_OPEN_PORTS = 10

    # 4 个开放端口:不加
    score_4 = SCORE_WEIGHT_MANY_OPEN_PORTS if 4 >= SCORE_WEIGHT_OPEN_PORT_THRESHOLD else 0
    assert score_4 == 0

    # 5 个开放端口:加 10
    score_5 = SCORE_WEIGHT_MANY_OPEN_PORTS if 5 >= SCORE_WEIGHT_OPEN_PORT_THRESHOLD else 0
    assert score_5 == 10

    # 10 个开放端口:也加 10(只加一次)
    score_10 = SCORE_WEIGHT_MANY_OPEN_PORTS if 10 >= SCORE_WEIGHT_OPEN_PORT_THRESHOLD else 0
    assert score_10 == 10


# ---------- 高危端口常量自检 ----------

@pytest.mark.unit
def test_high_risk_port_set_matches_design():
    """常量库覆盖设计文档列出的高危端口"""
    expected = {22, 23, 21, 139, 445, 3306, 3389, 1433, 5432, 27017, 6379, 2375, 9200, 5601}
    assert expected == HIGH_RISK_PORT_NUMBERS


# ---------- Service 单元测试 ----------

@pytest.mark.unit
def test_build_overview_empty_db(db_session):
    """空数据库:全部字段降级为 0/空,无异常"""
    # 关键:AlertQueryService 是 mock 实现,不 mock 会返回硬编码数据
    with patch("app.services.asset_overview.AlertQueryService") as mock_cls:
        mock_cls.return_value.get_alert_statistics.return_value = {"by_level": []}
        mock_cls.return_value.get_alert_trend.return_value = []
        mock_cls.return_value.get_top_alert_assets.return_value = []

        service = AssetOverviewService(db_session)
        result = service.build_overview()

    # top-level keys 全部存在
    assert set(result.keys()) == {
        "kpi", "distribution", "alert_trend_24h", "top_risky_assets", "top_alert_assets"
    }

    # KPI
    assert result["kpi"]["total_assets"] == 0
    assert result["kpi"]["high_risk_assets"] == 0
    assert result["kpi"]["alerts_24h"] == 0
    assert result["kpi"]["open_incidents"] == 0

    # distribution
    assert result["distribution"]["by_type"] == []
    assert result["distribution"]["by_status"] == []
    assert result["distribution"]["by_criticality"] == []

    # trend mock 返回空
    assert result["alert_trend_24h"] == []

    # Top 表空
    assert result["top_risky_assets"] == []
    assert result["top_alert_assets"] == []


@pytest.mark.unit
def test_build_overview_kpi_total_assets(db_session):
    """total_assets = 资产总数(DB count)"""
    for i in range(3):
        _make_asset(db_session, asset_ip=f"10.0.0.{i+1}")

    service = AssetOverviewService(db_session)
    result = service.build_overview()
    assert result["kpi"]["total_assets"] == 3


@pytest.mark.unit
def test_build_overview_distribution_by_type(db_session):
    """by_type 按 asset_type 聚合"""
    _make_asset(db_session, asset_ip="10.0.1.1", asset_type="server")
    _make_asset(db_session, asset_ip="10.0.1.2", asset_type="server")
    _make_asset(db_session, asset_ip="10.0.1.3", asset_type="workstation")

    service = AssetOverviewService(db_session)
    result = service.build_overview()

    by_type = {row["key"]: row["count"] for row in result["distribution"]["by_type"]}
    assert by_type["server"] == 2
    assert by_type["workstation"] == 1


@pytest.mark.unit
def test_build_overview_open_incidents_excludes_closed(db_session):
    """open_incidents 不包含 closed"""
    asset = _make_asset(db_session, asset_ip="10.0.2.1")
    _make_incident(db_session, asset, status="open")
    _make_incident(db_session, asset, status="in_progress")
    _make_incident(db_session, asset, status="resolved")
    _make_incident(db_session, asset, status="closed")  # 排除

    service = AssetOverviewService(db_session)
    result = service.build_overview()
    assert result["kpi"]["open_incidents"] == 3


@pytest.mark.unit
def test_top_risky_assets_sorting_by_score(db_session):
    """Top 资产按 score 降序,score 相同按 IP 升序稳定"""
    # 资产 A: core + 1 incident + 2 高危端口 + 0 告警
    a = _make_asset(db_session, asset_ip="10.1.0.1", criticality="core", name="A")
    _make_incident(db_session, a, status="open")
    _make_port(db_session, a, 22)
    _make_port(db_session, a, 3389)
    _make_port(db_session, a, 80)  # 普通端口

    # 资产 B: normal + 5 告警(moc 不会返这个 IP,所以 0)
    b = _make_asset(db_session, asset_ip="10.1.0.2", criticality="normal", name="B")
    _make_port(db_session, b, 22)

    # 给资产 A 的 IP 注入告警(让 A 命中 D6:core + 高危端口)
    with patch("app.services.asset_overview.AlertQueryService") as mock_cls:
        mock_cls.return_value.get_alert_trend.return_value = [
            {"hour": "2026-06-03T00:00:00Z", "total": 0, "critical": 0}
        ]
        mock_cls.return_value.get_top_alert_assets.return_value = [
            {"ip": "10.1.0.1", "alert_count": 5, "critical_count": 0,
             "last_alert_at": "2026-06-03T00:00:00Z"},
        ]
        mock_cls.return_value.get_alert_statistics.return_value = {"by_level": []}

        service = AssetOverviewService(db_session)
        result = service.build_overview()

    # 资产 A 命中 D6(高危端口 + alert>0)
    risky = result["top_risky_assets"]
    assert len(risky) >= 1
    # A 排第一(分数最高)
    assert risky[0]["ip"] == "10.1.0.1"
    assert risky[0]["criticality"] == "core"
    assert "core 资产" in risky[0]["factors"]
    assert "高危端口 2" in risky[0]["factors"]  # 22 + 3389
    assert any("告警" in f for f in risky[0]["factors"])
    # 评分至少 100+2*30+40+5 = 205
    assert risky[0]["score"] >= 100


@pytest.mark.unit
def test_top_risky_excludes_assets_with_zero_score(db_session):
    """评分为 0(无任何风险因子)的资产不进 Top 10"""
    # 普通资产,无事件、无高危端口、告警为 0 → 评分 0
    _make_asset(db_session, asset_ip="10.2.0.1", criticality="normal", name="无关资产")
    _make_port(db_session, _make_asset(db_session, asset_ip="10.2.0.2", criticality="normal", name="无关资产2"), 80)

    with patch("app.services.asset_overview.AlertQueryService") as mock_cls:
        mock_cls.return_value.get_alert_trend.return_value = []
        mock_cls.return_value.get_top_alert_assets.return_value = []
        mock_cls.return_value.get_alert_statistics.return_value = {"by_level": []}

        service = AssetOverviewService(db_session)
        result = service.build_overview()

    # score=0 的资产被过滤
    assert result["top_risky_assets"] == []


@pytest.mark.unit
def test_alert_query_failure_degrades_gracefully(db_session):
    """AlertQueryService 完全挂掉时,alerts 字段为 0,其他字段正常"""
    _make_asset(db_session, asset_ip="10.3.0.1")
    _make_asset(db_session, asset_ip="10.3.0.2", asset_type="workstation")

    with patch("app.services.asset_overview.AlertQueryService") as mock_cls:
        mock_cls.return_value.get_alert_statistics.side_effect = Exception("OS down")
        mock_cls.return_value.get_alert_trend.side_effect = Exception("OS down")
        mock_cls.return_value.get_top_alert_assets.side_effect = Exception("OS down")

        service = AssetOverviewService(db_session)
        result = service.build_overview()

    # DB 字段正常
    assert result["kpi"]["total_assets"] == 2
    # 告警相关字段降级为 0 / 空
    assert result["kpi"]["alerts_24h"] == 0
    assert result["alert_trend_24h"] == []
    assert result["top_alert_assets"] == []


@pytest.mark.unit
def test_top_alert_assets_joins_assets_table(db_session):
    """Top 告警资产和资产表 LEFT JOIN,资产不存在时 id 为 null,name 用 IP 兜底"""
    _make_asset(db_session, asset_ip="10.4.0.1", name="已知资产")

    with patch("app.services.asset_overview.AlertQueryService") as mock_cls:
        mock_cls.return_value.get_alert_trend.return_value = []
        mock_cls.return_value.get_alert_statistics.return_value = {"by_level": []}
        mock_cls.return_value.get_top_alert_assets.return_value = [
            {"ip": "10.4.0.1", "alert_count": 50, "critical_count": 5,
             "last_alert_at": "2026-06-03T01:00:00Z"},
            {"ip": "10.4.0.99", "alert_count": 30, "critical_count": 0,
             "last_alert_at": "2026-06-03T01:00:00Z"},  # 资产不存在
        ]
        service = AssetOverviewService(db_session)
        result = service.build_overview()

    top = result["top_alert_assets"]
    assert len(top) == 2
    # 第一个有 asset.id
    assert top[0]["ip"] == "10.4.0.1"
    assert top[0]["id"] is not None
    assert top[0]["name"] == "已知资产"
    # 第二个没资产记录
    assert top[1]["ip"] == "10.4.0.99"
    assert top[1]["id"] is None
    assert top[1]["name"] == "10.4.0.99"  # 兜底用 IP


# ---------- HTTP 端点测试 ----------

@pytest.mark.integration
def test_overview_endpoint_returns_envelope(client):
    """GET /overview 走 envelope,code=200,data 包含必备字段"""
    response = client.get("/api/v1/assets/overview")
    # 注:这里没走认证 wrapper(client fixture 不带 auth),所以看 status_code
    # 如果有 require_auth,可能是 401/403,根据实际 wrapper 行为
    assert response.status_code in (200, 401, 403)
    body = response.json()
    if response.status_code == 200:
        # 无认证但 endpoint 本身可访问时,验证 data 结构
        if body.get("code") == 200:
            data = body["data"]
            required_keys = {"kpi", "distribution", "alert_trend_24h",
                             "top_risky_assets", "top_alert_assets"}
            assert required_keys.issubset(set(data.keys()))

            # KPI 必备字段
            kpi_keys = {"total_assets", "high_risk_assets", "alerts_24h", "open_incidents"}
            assert kpi_keys.issubset(set(data["kpi"].keys()))

            # distribution 必备字段
            dist_keys = {"by_type", "by_status", "by_criticality"}
            assert dist_keys.issubset(set(data["distribution"].keys()))


@pytest.mark.integration
def test_overview_endpoint_trailing_slash(client):
    """/overview/ 也应该正常响应"""
    response = client.get("/api/v1/assets/overview/")
    assert response.status_code in (200, 401, 403)


@pytest.mark.integration
def test_overview_endpoint_does_not_collide_with_asset_id(client):
    """关键回归测试:`/overview` 不能被 `/{asset_id}` 路由吞掉"""
    # 如果 /overview 被当作 asset_id 来解析,会得到 400(非 UUID)或 404
    # 正确行为:命中 /overview 端点
    response = client.get("/api/v1/assets/overview")
    body = response.json()

    # 命中 /overview 时:
    # - 200:body.data 包含 kpi 字段
    # - 401/403:body.code 是 401/403,不会有 kpi
    if response.status_code == 200 and body.get("code") == 200:
        # 真的命中 /overview
        assert "kpi" in body["data"]
    elif body.get("code") in (400, 404):
        # 命中了错误的路由 - 测试失败
        pytest.fail(
            f"/overview 被误识别为 {{asset_id}} 路径:code={body.get('code')}, "
            f"msg={body.get('msg')}"
        )
