"""P4 WO-2 补丁：真失败路径测试

替换原 test_source_health_coverage.py 里的合成 @track_task 探针，
直接用 WazuhAgentSyncService / AssetSyncHandler / AssetSyncService 真服务对象，
mock 掉最外层（wazuh_client / _handle_one），让异常能逃到新加的 except 分支，
断言 soc_source_health 行被正确写入。

锚点（验收报告 §3 建议 B/C + 真实失败路径测试）：
- WazuhAgentSyncService.sync_agents 失败 → soc_source_health.failure_count +1
- AssetSyncHandler.handle 失败（source-level 异常）→ record_failure
- AssetSyncHandler.handle 成功 → record_success 带 expected_interval_seconds

跨 DB 问题：服务代码里 _db.SessionLocal() 绑的是 env 里的生产 DB
（本地 dev 指向 AI-miniSOC-testdb，与 AI-miniSOC-db_test 不同）。
以下测试用 patch 把 SessionLocal 重定向到 TestingSessionLocal，
让所有 source_health 写入都进 testdb。生产环境不 patch，行为不变。
"""
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.database import TestingSessionLocal
from app.models.base import Base
from app.core.database import test_engine
from app.models.source_health import SourceHealth


@pytest.fixture(scope="module")
def _engine():
    """模块级引擎 + 建表（一次）"""
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture()
def db(_engine):
    """每个测试独立 session + 清理 source_health"""
    session = TestingSessionLocal()
    session.query(SourceHealth).delete()
    session.commit()
    try:
        yield session
    finally:
        session.query(SourceHealth).delete()
        session.commit()
        session.close()


@pytest.fixture(autouse=True)
def _patch_session_local_to_testdb():
    """让服务代码里的 _db.SessionLocal() 写到 testdb。"""
    with patch("app.core.database.SessionLocal", TestingSessionLocal):
        yield


def test_wazuh_sync_agents_failure_records_source_health(db):
    """WazuhAgentSyncService.sync_agents：wazuh_client 不可达 → 记 record_failure

    验收报告 §2 WO-2 "未达成的部分" 关键缺口之一。
    v1.0-v1.2 行为：logger.error + raise，source_health 不动。
    v1.3 行为：独立 session 记 failure_count + last_failure_at + last_failure_message。
    """
    from app.services.wazuh_agent_sync import WazuhAgentSyncService

    with patch(
        "app.services.wazuh_client.wazuh_client.get_agents",
        side_effect=ConnectionError("Wazuh API timeout"),
    ):
        svc = WazuhAgentSyncService(db)
        with pytest.raises(ConnectionError):
            svc.sync_agents()

    # 用独立 session 查询（避免 db 已 commit/rollback 状态干扰）
    verify_db = TestingSessionLocal()
    try:
        row = verify_db.get(SourceHealth, "wazuh:agents")
        assert row is not None, "失败路径应建 wazuh:agents 行"
        assert row.failure_count == 1
        assert row.last_failure_at is not None
        assert "Wazuh API timeout" in (row.last_failure_message or "")
        assert row.source_type == "wazuh"
    finally:
        verify_db.close()


def test_wazuh_sync_agents_success_records_source_health(db):
    """WazuhAgentSyncService.sync_agents：成功 → wazuh:agents 记 success + interval

    间隔 300s 由 AssetSyncHandler.handle 的 _SOURCE_HEALTH_INTERVALS[wazuh] 提供。
    没 interval 时 _source_status() 会跳过 degraded 判定（验收报告 #2）。
    """
    from app.services.wazuh_agent_sync import WazuhAgentSyncService

    fake_agents = [
        {
            "id": "001",
            "name": "agent-001",
            "ip": "192.168.0.30",
            "status": "active",
            "os": {"name": "Ubuntu", "version": "22.04"},
        }
    ]
    success_stats = {
        "total": 1, "created": 1, "updated": 0, "skipped": 0,
        "failed": 0, "dead_letter_batch_id": None,
    }
    with patch(
        "app.services.wazuh_client.wazuh_client.get_agents",
        return_value=fake_agents,
    ), patch(
        # mock BaseSyncHandler.handle 返成功 stats——避免真实 DB 写 asset/sync_task
        "app.services.sync_handlers.base.BaseSyncHandler.handle",
        return_value=success_stats,
    ):
        svc = WazuhAgentSyncService(db)
        result = svc.sync_agents()
        assert result == success_stats

    verify_db = TestingSessionLocal()
    try:
        row = verify_db.get(SourceHealth, "wazuh:agents")
        assert row is not None
        assert row.success_count >= 1
        assert row.last_success_at is not None
        assert row.expected_interval_seconds == 300, "必须传 interval 才能让 degraded 判定生效"
    finally:
        verify_db.close()


def test_asset_sync_handler_failure_records_source_health(db):
    """AssetSyncHandler.handle：源级异常 → tplink:collector 记 failure

    验收报告 §2 WO-2 "未达成的部分" 另一关键缺口。
    v1.0-v1.2 行为：只 record_success，handle 抛错时 source_health 不动。
    v1.3 行为：try/except 包裹整个 body，失败时独立 session 记 record_failure。
    """
    from app.services.sync_handlers.asset_sync_handler import AssetSyncHandler

    with patch(
        "app.services.sync_handlers.base.BaseSyncHandler.handle",
        side_effect=RuntimeError("DB connection lost"),
    ):
        h = AssetSyncHandler()
        with pytest.raises(RuntimeError):
            h.handle("tplink", [{"asset_ip": "192.168.0.1"}], db)

    verify_db = TestingSessionLocal()
    try:
        row = verify_db.get(SourceHealth, "tplink:collector")
        assert row is not None
        assert row.failure_count == 1
        assert "DB connection lost" in (row.last_failure_message or "")
    finally:
        verify_db.close()


def test_asset_sync_handler_success_includes_expected_interval(db):
    """AssetSyncHandler.handle：成功 → record_success 带 expected_interval_seconds

    没 interval 时 _source_status() 守卫 `if interval and sh.last_success_at:` 跳过 degraded。
    验收报告 #2 要求所有 source 都设置 interval。
    """
    from app.services.sync_handlers.asset_sync_handler import AssetSyncHandler

    success_stats = {
        "total": 1, "created": 1, "updated": 0, "skipped": 0,
        "failed": 0, "dead_letter_batch_id": None,
    }
    h = AssetSyncHandler()
    item = {"asset_ip": "192.168.0.99", "network_segment": "default"}

    with patch(
        # mock base.handle 返成功 stats
        "app.services.sync_handlers.base.BaseSyncHandler.handle",
        return_value=success_stats,
    ):
        h.handle("tplink", [item], db)

    verify_db = TestingSessionLocal()
    try:
        row = verify_db.get(SourceHealth, "tplink:collector")
        assert row is not None
        assert row.success_count == 1
        assert row.expected_interval_seconds == 300
    finally:
        verify_db.close()


def test_wazuh_webhook_failure_records_source_health(db):
    """AssetSyncService.sync_single_agent_webhook：wazuh_client 不可达 → failure

    验收报告 §2 WO-2 提到的 webhooks.py:65 入口场景。
    """
    from app.services.asset_sync import AssetSyncService

    with patch(
        "app.services.wazuh_client.wazuh_client.get_agent_info",
        side_effect=ConnectionError("Wazuh unreachable"),
    ):
        svc = AssetSyncService(db)
        with pytest.raises(ConnectionError):
            svc.sync_single_agent_webhook("001")

    verify_db = TestingSessionLocal()
    try:
        row = verify_db.get(SourceHealth, "wazuh:agents")
        assert row is not None
        assert row.failure_count == 1
        assert "Wazuh unreachable" in (row.last_failure_message or "")
    finally:
        verify_db.close()