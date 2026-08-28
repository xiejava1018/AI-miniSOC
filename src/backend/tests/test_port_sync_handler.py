"""
PortSyncHandler 单元测试（P3/F-S2）

测试库：app.core.database.test_engine（独立 PG 库 AI-miniSOC-db_test）
不连网络，纯 ORM upsert 逻辑 + 死信路径 + 反查 asset_id 关联。
对照设计：docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md §6.2.2
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_port import AssetPort
from app.services.sync_handlers.port_sync_handler import PortSyncHandler
from app.services.sync_handlers.base import BaseSyncHandler
# P4 WO-2：source_health 集成镜像 AssetSyncHandler
from app.services.sync_handlers.asset_sync_handler import (
    _SOURCE_HEALTH_KEYS, _SOURCE_HEALTH_INTERVALS,
)


@pytest.fixture
def handler():
    return PortSyncHandler()


def _make_port_item(**overrides):
    """构造一条合法 port item；用 override 字段改任何值。"""
    item = {
        "asset_ip": "203.0.113.10",
        "port": 22,
        "protocol": "tcp",
        "state": "open",
        "service": "ssh",
        "version": "OpenSSH 8.4p1",
        "service_banner": "SSH-2.0-OpenSSH_8.4p1",
        "scan_time": "2026-08-26T03:00:00Z",
    }
    item.update(overrides)
    return item


# =============================================================================
# 1. 校验：合法 item 通过
# =============================================================================
def test_validate_one_accepts_valid_item(handler):
    item = _make_port_item()
    handler._validate_one(item)   # 不抛即通过
    # 副作用：protocol 标准化成小写
    assert item["protocol"] == "tcp"


def test_validate_one_lowercases_protocol(handler):
    item = _make_port_item(protocol="TCP")
    handler._validate_one(item)
    assert item["protocol"] == "tcp"


# =============================================================================
# 2. 校验：非法 item 抛 ValueError → 入死信
# =============================================================================
@pytest.mark.parametrize("bad_item", [
    {"asset_ip": None, "port": 80, "protocol": "tcp"},     # missing asset_ip
    {"asset_ip": "1.2.3.4", "port": 99999, "protocol": "tcp"},  # port 超范围
    {"asset_ip": "1.2.3.4", "port": 0, "protocol": "tcp"},       # port = 0
    {"asset_ip": "1.2.3.4", "port": 80, "protocol": "icmp"},     # 未知协议
    {"asset_ip": "1.2.3.4"},                                     # 多个字段缺失
], ids=["missing-ip", "port-99999", "port-0", "unknown-proto", "missing-port"])
def test_validate_one_raises(bad_item):
    """字段缺失 / 端口越界 / 未知协议 都应抛 ValueError → 父类入死信。"""
    handler = PortSyncHandler()
    with pytest.raises(ValueError):
        handler._validate_one(bad_item)


# =============================================================================
# 3. 单条 upsert：新建
# =============================================================================
def test_handle_one_creates_new_port(db_session: Session, handler):
    item = _make_port_item(asset_ip="203.0.113.10", port=22)
    result = handler._handle_one("scanner-port", item, db_session)
    db_session.commit()   # fixture 默认不 commit，手动 flush

    assert result == {"created": 1}

    # 验证落库
    port = db_session.query(AssetPort).filter(
        AssetPort.asset_ip == "203.0.113.10",
        AssetPort.port == 22,
        AssetPort.protocol == "tcp",
    ).one()
    assert port.service == "ssh"
    assert port.version == "OpenSSH 8.4p1"
    assert port.service_banner == "SSH-2.0-OpenSSH_8.4p1"
    assert port.state == "open"
    assert port.vulnerability is None  # 本期留空


# =============================================================================
# 4. 单条 upsert：命中已有 → 更新（service 指纹 + last_seen）
# =============================================================================
def test_handle_one_updates_existing_port(db_session: Session, handler):
    # 先建一条
    handler._handle_one("scanner-port", _make_port_item(
        asset_ip="203.0.113.10", port=22, service="ssh", version="OpenSSH 8.4p1"
    ), db_session)
    db_session.commit()

    # 隔一段时间后再次推送（service 指纹细化 + banner 不变）
    new_time = datetime(2026, 8, 27, 4, 0, 0, tzinfo=timezone.utc)
    result = handler._handle_one("scanner-port", _make_port_item(
        asset_ip="203.0.113.10", port=22,
        version="OpenSSH 8.4p1 Debian 5+deb11u1",   # 更精细
        scan_time=new_time.isoformat(),
    ), db_session)
    db_session.commit()

    assert result == {"updated": 1}
    port = db_session.query(AssetPort).filter(
        AssetPort.asset_ip == "203.0.113.10", AssetPort.port == 22,
    ).one()
    assert port.service == "ssh"           # 不变（缺省时保持原值）
    assert "Debian 5+deb11u1" in port.version   # 更新
    assert port.last_seen == new_time       # last_seen 刷新


# =============================================================================
# 5. 反查 soc_assets：命中 IP 自动挂上 asset_id
# =============================================================================
def test_handle_one_attaches_asset_id_when_ip_matches(db_session: Session, handler):
    # 准备：先在台账建一条 IP=203.0.113.10 的资产
    asset = Asset(
        network_segment="public",
        network_zone="dmz",
        asset_ip="203.0.113.10",
        name="public-server-01",
        asset_status="online",
        asset_type="server",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    assert asset.id is not None

    # 推一条端口数据
    result = handler._handle_one("scanner-port", _make_port_item(
        asset_ip="203.0.113.10", port=80,
    ), db_session)
    db_session.commit()
    assert result == {"created": 1}

    port = db_session.query(AssetPort).filter(
        AssetPort.asset_ip == "203.0.113.10", AssetPort.port == 80,
    ).one()
    assert port.asset_id == asset.id   # 自动挂上


# =============================================================================
# 6. 反查失败：IP 不在台账 → asset_id=NULL（公网 IP 允许）
# =============================================================================
def test_handle_one_no_asset_match_leaves_asset_id_null(db_session: Session, handler):
    result = handler._handle_one("scanner-port", _make_port_item(
        asset_ip="203.0.113.99", port=443,  # 台账无此 IP
    ), db_session)
    db_session.commit()
    assert result == {"created": 1}

    port = db_session.query(AssetPort).filter(
        AssetPort.asset_ip == "203.0.113.99",
    ).one()
    assert port.asset_id is None   # 允许 NULL


# =============================================================================
# 7. vulnerability 留空：v0/v1 已有值不覆盖（保留运维标注）
# =============================================================================
def test_handle_one_does_not_clobber_existing_vulnerability(db_session: Session, handler):
    # 先建一条带 vulnerability 的（模拟运维手动标注）
    item = _make_port_item(asset_ip="203.0.113.10", port=22)
    handler._handle_one("scanner-port", item, db_session)
    db_session.commit()

    port = db_session.query(AssetPort).filter(
        AssetPort.asset_ip == "203.0.113.10", AssetPort.port == 22,
    ).one()
    port.vulnerability = "CVE-2023-38408 (manual annotation)"
    db_session.commit()

    # scanner 再次推（不应覆盖 vulnerability）
    handler._handle_one("scanner-port", _make_port_item(
        asset_ip="203.0.113.10", port=22, version="OpenSSH 9.0",  # 只升版
    ), db_session)
    db_session.commit()

    port = db_session.query(AssetPort).filter(
        AssetPort.asset_ip == "203.0.113.10", AssetPort.port == 22,
    ).one()
    assert port.vulnerability == "CVE-2023-38408 (manual annotation)"   # 保留
    assert "9.0" in port.version   # 但 version 升了


# =============================================================================
# 8. 整 batch handle()：混合 created/updated/skipped/failed
# =============================================================================
def test_handle_batch_mixed_results(db_session: Session, handler):
    items = [
        _make_port_item(asset_ip="1.1.1.1", port=22),    # created
        _make_port_item(asset_ip="1.1.1.1", port=80),    # created
        _make_port_item(asset_ip="2.2.2.2", port=None),   # failed（缺 port）
    ]
    stats = handler.handle("scanner-port", items, db_session)

    assert stats["total"] == 3
    assert stats["created"] == 2
    assert stats["updated"] == 0
    assert stats["failed"] == 1
    assert stats["dead_letter_batch_id"] is not None

    # 验证 DB：两条入库
    rows = db_session.query(AssetPort).filter(
        AssetPort.asset_ip.in_(["1.1.1.1"]),
    ).all()
    assert len(rows) == 2


# =============================================================================
# 9. source_health 集成：handle() 成功后自动上报 scanner:ports
# =============================================================================
def test_handle_records_source_health_success(db_session: Session, handler):
    """P4 WO-2 镜像：handle() 成功后 SourceHealthRecorder.record_success 被调。

    用 mock 验证：避免依赖 source_health 模块具体实现。
    """
    from unittest.mock import patch, MagicMock

    items = [_make_port_item()]
    with patch("app.services.source_health.SourceHealthRecorder") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        handler.handle("scanner-port", items, db_session)

        # record_success 被调用，key=scanner:ports
        assert mock_instance.record_success.called
        call_kwargs = mock_instance.record_success.call_args.kwargs
        assert call_kwargs["source_type"] == "scanner-port"
        # 验证 key 派生
        assert "scanner:ports" in _SOURCE_HEALTH_KEYS["scanner-port"]


# =============================================================================
# 10. 入口健康键：scanner:ports 在 KEY 表里
# =============================================================================
def test_health_keys_contain_scanner_ports():
    """回归保护：scanner 通道健康键不会被某次重构误删。"""
    assert "scanner-port" in _SOURCE_HEALTH_KEYS
    assert _SOURCE_HEALTH_KEYS["scanner-port"] == "scanner:ports"
    assert _SOURCE_HEALTH_KEYS["scanner"] == "scanner:discovery"   # Phase 2 用
    assert _SOURCE_HEALTH_INTERVALS["scanner-port"] == 90000  # 按调度节奏（每天 03:00/04:00）而非心跳 300s


# =============================================================================
# 11. Pydantic 校验：DataSyncRequest 接受 data_type="port"
# =============================================================================
def test_data_sync_schema_accepts_port():
    from app.schemas.data_sync import DataSyncRequest
    req = DataSyncRequest(
        source="scanner-port",
        data_type="port",
        items=[_make_port_item()],
    )
    assert req.data_type == "port"
    assert len(req.items) == 1


# 注：Phase 2 写 scanner-collector 时再加 `from collector_framework.base import DataType`
#     的测试，但 collector_framework 不在后端 venv site-packages，需要在 Phase 2
#     的测试 conftest 里加 PYTHONPATH（避免污染后端单测的纯净度）。