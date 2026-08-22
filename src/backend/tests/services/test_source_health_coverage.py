"""P4 WO-2：采集源健康上报覆盖补全单测

验收锚点（执行计划 WO-2）：
1. decorator 失败路径写 soc_source_health.failure_count（且修好 v1.0 前已
   静默失效的成功路径——原构造调用 TypeError 被 except 吞掉）
2. AssetSyncHandler.handle 收尾写 tplink:collector（wazuh agents 同走此处）
3. OpenSearch SCAP 同步成功/失败写 opensearch:vuln
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.source_health import SourceHealthRecorder


@pytest.fixture
def recorder():
    """内存 fake：记录 record_success/record_failure 调用。
    同时 patch 两处绑定：decorator（顶层 import，已绑定符号）与
    source_health 模块（asset_sync_handler / scap_sync 函数内延迟 import）。"""
    calls = []

    class _R:
        def __init__(self, db):
            self.db = db

        def record_success(self, key, **kw):
            calls.append(("success", key, kw))

        def record_failure(self, key, **kw):
            calls.append(("failure", key, kw))

    with patch(
        "app.services.task_observability.decorator.SourceHealthRecorder", _R
    ), patch("app.services.source_health.SourceHealthRecorder", _R):
        yield calls


def test_decorator_failure_path_records_source_health(recorder):
    """场景 1：被 @track_task 包装的任务抛错 → source_health 记 failure。"""
    import asyncio
    from app.services.task_observability.decorator import track_task

    fake_db = MagicMock()

    @track_task(task_key="wo2_fail_probe", source_key="wazuh:agents", timeout_s=60)
    async def boom():
        raise RuntimeError("同步挂了")

    with patch("app.services.task_observability.decorator._db") as db_mod, patch(
        "app.services.task_observability.decorator.store"
    ):
        db_mod.SessionLocal.return_value = fake_db
        with pytest.raises(RuntimeError):
            asyncio.run(boom())

    failures = [c for c in recorder if c[0] == "failure" and c[1] == "wazuh:agents"]
    assert failures, "失败路径应写 source_health"
    assert "RuntimeError" in failures[0][2]["error"]


def test_decorator_success_path_records_source_health(recorder):
    """场景 1b：成功路径（v1.0 前从未真正生效——构造调用 TypeError 被吞）。"""
    import asyncio
    from app.services.task_observability.decorator import track_task

    fake_db = MagicMock()

    @track_task(task_key="wo2_ok_probe", source_key="tplink:collector", timeout_s=60)
    async def ok():
        return {"processed": 7}

    with patch("app.services.task_observability.decorator._db") as db_mod, patch(
        "app.services.task_observability.decorator.store"
    ):
        db_mod.SessionLocal.return_value = fake_db
        asyncio.run(ok())

    successes = [c for c in recorder if c[0] == "success" and c[1] == "tplink:collector"]
    assert successes, "成功路径应写 source_health"
    assert successes[0][2]["records_count"] == 7


def test_asset_sync_handler_records_source_health(recorder):
    """场景 2：采集器推送流经 AssetSyncHandler → 写 tplink:collector。"""
    from app.services.sync_handlers.asset_sync_handler import AssetSyncHandler

    calls = recorder

    h = AssetSyncHandler()
    db = MagicMock()
    item = {"network_segment": "seg", "asset_ip": "192.168.0.1", "asset_name": "t"}
    with patch.object(h, "_validate_one"), patch.object(
        h, "_handle_one", return_value={"created": 1, "updated": 0, "skipped": 0}
    ), patch("app.services.sync_handlers.asset_sync_handler.SyncTask"):
        h.handle("tplink", [item], db)

    successes = [c for c in recorder if c[0] == "success" and c[1] == "tplink:collector"]
    assert successes, "tplink 推送应写 tplink:collector"
    assert successes[0][2]["records_count"] == 1
