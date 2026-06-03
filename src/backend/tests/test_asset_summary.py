"""
资产安全摘要服务 + /summary 端点测试

覆盖范围:
- AssetSummaryService.build_summary 各字段聚合逻辑
- 在线状态映射、未关闭事件过滤、高危端口识别、标签返回
- 异常路径(无效 UUID / 资产不存在)的兜底
- 通过 HTTP 调用 /api/v1/assets/{id}/summary 验证 envelope

> Wazuh 缓存字段(applications/vuln_*/sca_*)Phase 1 占位为 0/None,Phase 2 接入真实表后
> 需要补对应的真实数据测试,本次测试只锁定占位契约。
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_port import AssetPort
from app.models.asset_tag import AssetTag
from app.models.asset_incident import AssetIncident
from app.models.incident import Incident
from app.services.asset_summary import (
    AssetSummaryService,
    HIGH_RISK_PORTS,
    _map_status_to_online,
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
        data_classification="internal",
        owner="alice",
        owner_contact="13800000000",
    )
    defaults.update(overrides)
    asset = Asset(**defaults)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _make_port(db: Session, asset: Asset, port: int, state: str = "open",
               scan_time: datetime = None) -> AssetPort:
    p = AssetPort(
        asset_id=asset.id,
        asset_ip=asset.asset_ip,
        port=port,
        protocol="tcp",
        state=state,
        scan_time=scan_time or datetime.now(timezone.utc),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_incident(db: Session, asset: Asset, status: str,
                   severity: str = "high") -> Incident:
    """创建 incident 并关联到 asset"""
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


def _make_tag(db: Session, asset: Asset, key: str, value: str) -> AssetTag:
    t = AssetTag(asset_id=asset.id, tag_key=key, tag_value=value)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


# ---------- 在线状态映射 ----------

@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    ("online", "online"),
    ("ONLINE", "online"),
    ("active", "online"),
    ("connected", "online"),
    ("offline", "offline"),
    ("disconnected", "offline"),
    ("decommissioned", "offline"),
    ("never_connected", "offline"),
    ("inactive", "offline"),
    (None, "unknown"),
    ("", "unknown"),
    ("weird_status", "unknown"),
])
def test_map_status_to_online(raw, expected):
    """asset_status 字典值 → 统一 online/offline/unknown"""
    assert _map_status_to_online(raw) == expected


# ---------- Service 单元测试 ----------

@pytest.mark.unit
def test_build_summary_happy_path(db_session):
    """完整字段聚合:online + 端口 + 标签 + Wazuh 占位"""
    asset = _make_asset(db_session, asset_ip="10.0.0.10")

    # 4 个开放端口: 22 高危, 80 普通, 3306 高危, 3389 高危
    _make_port(db_session, asset, 22)
    _make_port(db_session, asset, 80)
    _make_port(db_session, asset, 3306)
    _make_port(db_session, asset, 3389)
    # 关闭的端口不计入开放
    _make_port(db_session, asset, 5000, state="closed")

    _make_tag(db_session, asset, "environment", "production")
    _make_tag(db_session, asset, "business_system", "hr-system")

    service = AssetSummaryService(db_session)
    summary = service.build_summary(str(asset.id))

    assert summary["asset_id"] == str(asset.id)
    assert summary["online_status"] == "online"

    # 端口
    assert summary["open_ports"] == 4
    assert summary["high_risk_ports"] == 3  # 22, 3306, 3389
    assert summary["last_port_scan"] is not None

    # 标签
    assert {"key": "environment", "value": "production"} in summary["tags"]
    assert len(summary["tags"]) == 2

    # 合规 + 联系
    assert summary["data_classification"] == "internal"
    assert summary["owner"] == "alice"
    assert summary["owner_contact"] == "13800000000"

    # Wazuh 占位字段(Phase 2 前应该全部为 0/None)
    assert summary["vuln_critical"] == 0
    assert summary["vuln_high"] == 0
    assert summary["vuln_total"] == 0
    assert summary["applications"] == 0
    assert summary["sca_pass_rate"] is None
    assert summary["sca_total"] == 0
    assert summary["sca_failed"] == 0
    assert summary["last_vuln_scan"] is None
    assert summary["last_sca_scan"] is None


@pytest.mark.unit
def test_build_summary_offline_asset(db_session):
    """offline 状态映射"""
    asset = _make_asset(db_session, asset_ip="10.0.0.11", asset_status="offline")
    service = AssetSummaryService(db_session)
    summary = service.build_summary(str(asset.id))
    assert summary["online_status"] == "offline"


@pytest.mark.unit
def test_build_summary_unknown_status(db_session):
    """asset_status 为 None 时映射为 unknown"""
    asset = _make_asset(db_session, asset_ip="10.0.0.12", asset_status=None)
    service = AssetSummaryService(db_session)
    summary = service.build_summary(str(asset.id))
    assert summary["online_status"] == "unknown"


@pytest.mark.unit
def test_open_incidents_excludes_closed(db_session):
    """closed 状态的事件不计入 open_incidents"""
    asset = _make_asset(db_session, asset_ip="10.0.0.13")

    _make_incident(db_session, asset, status="open")
    _make_incident(db_session, asset, status="in_progress")
    _make_incident(db_session, asset, status="resolved")
    _make_incident(db_session, asset, status="closed")  # 应排除

    service = AssetSummaryService(db_session)
    summary = service.build_summary(str(asset.id))

    # open + in_progress + resolved = 3
    assert summary["open_incidents"] == 3


@pytest.mark.unit
def test_summary_returns_empty_for_invalid_uuid(db_session):
    """非法 UUID 字符串走兜底分支,不抛异常"""
    service = AssetSummaryService(db_session)
    summary = service.build_summary("not-a-uuid")

    assert summary["asset_id"] == "not-a-uuid"
    assert summary["online_status"] == "unknown"
    assert summary["open_ports"] == 0
    assert summary["tags"] == []


@pytest.mark.unit
def test_summary_returns_empty_for_nonexistent_asset(db_session):
    """资产不存在时走兜底分支,字段都是 0/None/空"""
    fake_id = str(uuid.uuid4())
    service = AssetSummaryService(db_session)
    summary = service.build_summary(fake_id)

    assert summary["asset_id"] == fake_id
    assert summary["online_status"] == "unknown"
    assert summary["alert_24h"] == 0
    assert summary["alert_critical_24h"] == 0
    assert summary["open_incidents"] == 0
    assert summary["open_ports"] == 0
    assert summary["high_risk_ports"] == 0
    assert summary["tags"] == []


@pytest.mark.unit
def test_alert_stats_fallback_to_zero(db_session):
    """AlertQueryService 抛异常时降级为 (0, 0),不影响整体响应"""
    asset = _make_asset(db_session, asset_ip="10.0.0.14")

    with patch(
        "app.services.asset_summary.AlertQueryService"
    ) as mock_cls:
        mock_cls.return_value.get_alert_statistics.side_effect = Exception("OS down")
        service = AssetSummaryService(db_session)
        summary = service.build_summary(str(asset.id))

    assert summary["alert_24h"] == 0
    assert summary["alert_critical_24h"] == 0


@pytest.mark.unit
def test_alert_stats_critical_threshold(db_session):
    """level >= 12 应计入 critical(覆盖字符串 level 的解析路径)"""
    asset = _make_asset(db_session, asset_ip="10.0.0.15")

    fake_stats = {
        "by_level": [
            {"key": "5", "doc_count": 10},   # 普通
            {"key": "12", "doc_count": 3},   # critical
            {"key": "15", "doc_count": 2},   # critical
            {"key": None, "doc_count": 99},  # 跳过
        ]
    }
    with patch(
        "app.services.asset_summary.AlertQueryService"
    ) as mock_cls:
        mock_cls.return_value.get_alert_statistics.return_value = fake_stats
        service = AssetSummaryService(db_session)
        summary = service.build_summary(str(asset.id))

    assert summary["alert_24h"] == 15  # 10 + 3 + 2
    assert summary["alert_critical_24h"] == 5  # 3 + 2


# ---------- HIGH_RISK_PORTS 常量自检 ----------

@pytest.mark.unit
def test_high_risk_ports_constant_includes_critical_ports():
    """常量库覆盖项目设计文档列出的高危端口"""
    expected = {22, 23, 21, 139, 445, 3306, 3389, 1433, 5432, 27017, 6379, 2375, 9200, 5601}
    assert expected.issubset(set(HIGH_RISK_PORTS.keys()))
    # docker 未授权 API 应是 critical 级
    assert HIGH_RISK_PORTS[2375]["risk"] == "critical"


# ---------- HTTP 端点测试 ----------

@pytest.mark.integration
def test_summary_endpoint_returns_envelope(client, db_session):
    """GET /summary 走 envelope,code=200,data 包含必备字段"""
    asset = _make_asset(db_session, asset_ip="10.0.0.20")

    response = client.get(f"/api/v1/assets/{asset.id}/summary")
    assert response.status_code == 200  # wrapper 层固定 200

    body = response.json()
    assert body["code"] == 200

    data = body["data"]
    # 设计文档 §7.1 锁定的核心字段全部存在
    required_keys = {
        "asset_id", "online_status", "alert_24h", "alert_critical_24h",
        "open_incidents", "vuln_critical", "vuln_high", "vuln_total",
        "open_ports", "high_risk_ports", "applications",
        "sca_pass_rate", "sca_total", "sca_failed",
        "last_port_scan", "last_vuln_scan", "last_sca_scan",
        "data_classification", "owner", "owner_contact", "tags",
    }
    assert required_keys.issubset(set(data.keys()))
    assert data["asset_id"] == str(asset.id)


@pytest.mark.integration
def test_summary_endpoint_404_for_unknown_asset(client):
    """资产不存在 → 404(envelope 包装)"""
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/assets/{fake_id}/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 404


@pytest.mark.integration
def test_summary_endpoint_400_for_invalid_uuid(client):
    """非法 UUID 路径 → 400(envelope 包装)"""
    response = client.get("/api/v1/assets/not-a-uuid/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 400
