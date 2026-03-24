"""
资产模型测试
"""

import pytest
from datetime import datetime, timezone
from app.models.asset import Asset


def test_asset_with_wazuh_fields(db_session):
    """测试资产的Wazuh相关字段"""
    asset = Asset(
        network_segment="default",
        asset_ip="192.168.1.100",
        data_source="wazuh",
        last_synced_at=datetime.now(timezone.utc),
        os_name="Ubuntu",
        os_version="22.04",
        hardware_info={"cpu": "4 cores", "memory": "8GB"}
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    assert asset.data_source == "wazuh"
    assert asset.last_synced_at is not None
    assert asset.os_name == "Ubuntu"
    assert asset.os_version == "22.04"
    assert asset.hardware_info["cpu"] == "4 cores"


def test_asset_default_data_source(db_session):
    """测试资产默认数据源为manual"""
    asset = Asset(
        network_segment="default",
        asset_ip="192.168.1.101"
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    assert asset.data_source == "manual"
