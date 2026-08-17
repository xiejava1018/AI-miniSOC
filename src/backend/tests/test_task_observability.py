"""
task_observability 集成测试（v0.4.2）。

不依赖 pytest-asyncio；异步测试用 asyncio.run() 包裹。
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core import database as _db
from app.core.database import TestingSessionLocal
from app.models.task_observability import (
    SocTaskRegistry,
    SocTaskRun,
    TaskRunStatus,
)
from app.services.task_observability import track_task, store
from app.services.task_observability.dedup import NotificationDeduplicator
from app.services.task_observability.lock import get_task_lock


@pytest.fixture(autouse=True)
def _use_test_db():
    """把 task_observability 子模块的 SessionLocal 重定向到测试库。

    所有子模块都是通过 ``from app.core import database as _db; _db.SessionLocal()``
    拿 session，所以只需要 monkeypatch ``_db.SessionLocal`` 一个地方。
    """
    original = _db.SessionLocal
    _db.SessionLocal = TestingSessionLocal
    try:
        yield
    finally:
        _db.SessionLocal = original


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. 装饰器成功 / 失败

def test_track_task_success_records_run(db_session):
    store.upsert_registry(
        db_session,
        task_key="test_success_task",
        task_name="Test Success",
        task_type="scheduled",
        timeout_s=30,
    )

    @track_task(
        task_key="test_success_task",
        task_name="Test Success",
        task_type="scheduled",
        timeout_s=30,
        register_on_call=False,
    )
    async def body():
        return {"processed": 42}

    result = _run(body())
    assert result == {"processed": 42}

    db = TestingSessionLocal()
    try:
        run = (
            db.query(SocTaskRun)
            .filter_by(task_key="test_success_task")
            .order_by(SocTaskRun.started_at.desc())
            .first()
        )
        assert run is not None
        assert run.status == TaskRunStatus.SUCCESS
        assert run.stats_json == {"processed": 42}
        reg = db.get(SocTaskRegistry, "test_success_task")
        assert reg.consecutive_failures == 0
        assert reg.total_runs == 1
    finally:
        db.close()


def test_track_task_failure_records_run(db_session):
    store.upsert_registry(
        db_session,
        task_key="test_failed_task",
        task_name="Test Fail",
        task_type="scheduled",
        timeout_s=30,
    )

    @track_task(
        task_key="test_failed_task",
        task_name="Test Fail",
        task_type="scheduled",
        timeout_s=30,
        register_on_call=False,
    )
    async def body():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _run(body())

    db = TestingSessionLocal()
    try:
        run = (
            db.query(SocTaskRun)
            .filter_by(task_key="test_failed_task")
            .order_by(SocTaskRun.started_at.desc())
            .first()
        )
        assert run.status == TaskRunStatus.FAILED
        assert "boom" in (run.error_text or "")
        reg = db.get(SocTaskRegistry, "test_failed_task")
        assert reg.consecutive_failures == 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2. POC-2：timeout 后锁不立即释放

def test_timeout_holds_lock_until_sync_completes(db_session, monkeypatch):
    # 放开装饰器 MIN_TIMEOUT_S 限制，允许 timeout_s=1 验证 POC-2 行为
    from app.services.task_observability import decorator as deco_mod
    from app.services.task_observability import store as store_mod
    monkeypatch.setattr(deco_mod, "MIN_TIMEOUT_S", 0)
    # store.upsert_registry 也有 >=30 保护，测试时绕过
    original_upsert = store_mod.upsert_registry
    def _patched_upsert(db, **kw):
        # 直接写 registry，跳过 timeout 检查
        from app.models.task_observability import SocTaskRegistry
        reg = SocTaskRegistry(**kw)
        db.add(reg)
        db.commit()
        return reg
    monkeypatch.setattr(store_mod, "upsert_registry", _patched_upsert)

    task_key = f"test_poc2_{uuid.uuid4().hex[:8]}"
    lock = get_task_lock(task_key)
    if lock.locked():
        lock.release()

    db = TestingSessionLocal()
    _patched_upsert(
        db, task_key=task_key, task_name=task_key,
        task_type="scheduled", timeout_s=1,
    )
    db.close()

    sync_started = asyncio.Event()

    @track_task(
        task_key=task_key,
        task_name=task_key,
        task_type="scheduled",
        timeout_s=1,
        register_on_call=False,
    )
    async def slow_body():
        async def _sync():
            sync_started.set()
            await asyncio.to_thread(lambda: time.sleep(2))
            return "done"
        return await _sync()

    async def main():
        t0 = time.monotonic()
        task = asyncio.create_task(slow_body())
        await sync_started.wait()
        await asyncio.sleep(0.5)
        assert lock.locked()
        await asyncio.sleep(0.7)
        # timeout 已触发但 to_thread 还在跑——锁必须仍持有
        assert lock.locked(), "POC-2 关键：timeout 后锁必须仍持有"
        result = await task
        elapsed = time.monotonic() - t0
        return result, elapsed

    result, elapsed = _run(main())
    assert result == "done"
    assert elapsed >= 1.8, f"expected ~2s, got {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# 3. 启动对账

def test_reconcile_marks_running_as_unknown(db_session):
    store.upsert_registry(
        db_session,
        task_key="test_reconcile",
        task_name="Test Reconcile",
        task_type="scheduled",
        timeout_s=30,
    )
    run = SocTaskRun(
        id=uuid.uuid4(),
        task_key="test_reconcile",
        trigger="scheduled",
        status=TaskRunStatus.RUNNING,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        host="old-host",
    )
    db_session.add(run)
    db_session.commit()

    stats = store.reconcile_on_startup(db_session)
    assert stats["marked_unknown"] >= 1
    db_session.refresh(run)
    assert run.status == TaskRunStatus.UNKNOWN
    assert run.finished_at is not None


# ---------------------------------------------------------------------------
# 4. 看门狗 zombie

def test_watchdog_marks_zombie(db_session):
    store.upsert_registry(
        db_session,
        task_key="test_zombie",
        task_name="Test Zombie",
        task_type="scheduled",
        timeout_s=30,
    )
    run = SocTaskRun(
        id=uuid.uuid4(),
        task_key="test_zombie",
        trigger="scheduled",
        status=TaskRunStatus.RUNNING,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        last_progress_at=None,
        host="old-host",
    )
    db_session.add(run)
    db_session.commit()
    rid = run.id

    from app.services.task_observability.watchdog import _find_zombies
    db = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        zombies = _find_zombies(db, now)
        assert any(z.id == rid for z in zombies)
    finally:
        db.close()


def test_watchdog_does_not_mark_progressing_run(db_session):
    db = TestingSessionLocal()
    try:
        store.upsert_registry(
            db,
            task_key="test_progress",
            task_name="Test Progress",
            task_type="scheduled",
            timeout_s=300,
        )
        run = SocTaskRun(
            id=uuid.uuid4(),
            task_key="test_progress",
            trigger="scheduled",
            status=TaskRunStatus.RUNNING,
            started_at=datetime.now(timezone.utc) - timedelta(seconds=400),
            last_progress_at=datetime.now(timezone.utc) - timedelta(seconds=10),
            host="host",
        )
        db.add(run)
        db.commit()
        rid = run.id

        from app.services.task_observability.watchdog import _find_zombies
        zombies = _find_zombies(db, datetime.now(timezone.utc))
        assert not any(z.id == rid for z in zombies)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 5. 通知去重

def test_dedup_same_fingerprint_within_window():
    dedup = NotificationDeduplicator(window_seconds=60)
    assert dedup.should_send("k", "alert", "error X") is True
    assert dedup.should_send("k", "alert", "error X") is False
    assert dedup.should_send("k", "alert", "error Y") is True
    assert dedup.should_send("k2", "alert", "error X") is True


# ---------------------------------------------------------------------------
# 6. /health 状态

def test_health_returns_200(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("healthy", "degraded")
    assert "watchdog" in body


# ---------------------------------------------------------------------------
# 7. API 鉴权

def test_tasks_api_requires_auth(client):
    r = client.get("/api/v1/tasks/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 401


def test_tasks_api_404_for_unknown_task(authenticated_client):
    r = authenticated_client.post(
        "/api/v1/tasks/nonexistent_task/trigger",
        json={"reason": "test trigger"},
    )
    body = r.json()
    assert body["code"] == 404


# ---------------------------------------------------------------------------
# Fixtures

@pytest.fixture
def authenticated_client(db_session, client):
    from app.models.user import User, UserStatus
    from app.core.security import get_password_hash

    user = User(
        username=f"testadmin_{uuid.uuid4().hex[:6]}",
        email=f"testadmin_{uuid.uuid4().hex[:6]}@test.local",
        password_hash=get_password_hash("Test123!"),
        status=UserStatus.ACTIVE,
        is_superuser=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    r = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "Test123!"},
    )
    body = r.json()
    token = body.get("data", {}).get("access_token")
    if not token:
        pytest.skip(f"login failed: {body}")
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ---------------------------------------------------------------------------
# Phase 2.4: update_progress API 测试


def test_update_progress_outside_task_is_noop():
    """不在 @track_task 上下文里调用 update_progress 应该返回 False（静默）"""
    from app.services.task_observability import update_progress
    assert update_progress(processed=1, total=10) is False


def test_update_progress_writes_percent(monkeypatch):
    """在 @track_task 内调 update_progress 应该写 soc_task_runs.processed/total/percent"""
    from app.services.task_observability import (
        track_task,
        update_progress,
        decorator as deco_mod,
    )
    from app.models.task_observability import SocTaskRun, SocTaskRegistry
    from app.core import database as _db

    monkeypatch.setattr(deco_mod, "MIN_TIMEOUT_S", 0)

    task_key = f"test_progress_{uuid.uuid4().hex[:8]}"

    # 确保测试表存在（不依赖 db_session fixture，避免 create/drop_all 与 to_thread 连接冲突）
    from app.models.base import Base
    from app.core.database import test_engine
    Base.metadata.create_all(bind=test_engine, tables=[
        SocTaskRegistry.__table__, SocTaskRun.__table__,
    ])

    # 直接写 registry（绕过 store.upsert_registry 的 >=30 保护）
    db = TestingSessionLocal()
    db.add(SocTaskRegistry(
        task_key=task_key, task_name=task_key, task_type="scheduled",
        timeout_s=60, enabled=True,
    ))
    db.commit()
    db.close()

    @track_task(task_key=task_key, task_name=task_key, task_type="scheduled", timeout_s=60)
    async def work_with_progress():
        update_progress(processed=0, total=100, stats={"stage": "fetch"})
        update_progress(processed=50, total=100, stats={"stage": "parse"})
        update_progress(processed=100, total=100, stats={"stage": "done"})
        return {"ok": True}

    asyncio.run(work_with_progress())

    # 验证最终 run 状态
    db = TestingSessionLocal()
    run = db.query(SocTaskRun).filter(SocTaskRun.task_key == task_key).first()
    assert run is not None
    assert run.status.value == "success"
    assert run.total == 100
    assert run.processed == 100
    assert run.percent == 100
    assert run.stats_json is not None
    # finish_run 用返回值覆盖 stats；progress 的 stage 只在 running 期间可见
    assert run.stats_json == {"ok": True}
    db.close()

    # cleanup（避免测试残留堆积）
    db = TestingSessionLocal()
    db.query(SocTaskRun).filter(SocTaskRun.task_key == task_key).delete()
    db.query(SocTaskRegistry).filter(SocTaskRegistry.task_key == task_key).delete()
    db.commit()
    db.close()


def test_update_progress_stage_helper(monkeypatch):
    """update_progress_stage 应该把 stage 合并进 stats"""
    from app.services.task_observability import (
        track_task,
        update_progress_stage,
        decorator as deco_mod,
    )
    from app.models.task_observability import SocTaskRun, SocTaskRegistry

    monkeypatch.setattr(deco_mod, "MIN_TIMEOUT_S", 0)

    task_key = f"test_stage_{uuid.uuid4().hex[:8]}"

    # 确保测试表存在
    from app.models.base import Base
    from app.core.database import test_engine
    Base.metadata.create_all(bind=test_engine, tables=[
        SocTaskRegistry.__table__, SocTaskRun.__table__,
    ])

    db = TestingSessionLocal()
    db.add(SocTaskRegistry(
        task_key=task_key, task_name=task_key, task_type="scheduled",
        timeout_s=60, enabled=True,
    ))
    db.commit()
    db.close()

    @track_task(task_key=task_key, task_name=task_key, task_type="scheduled", timeout_s=60)
    async def staged_work():
        update_progress_stage("step1", processed=1, total=3)
        update_progress_stage("step2", processed=2, total=3, extra={"k": "v"})
        update_progress_stage("step3", processed=3, total=3)
        return {"ok": True}

    asyncio.run(staged_work())

    db = TestingSessionLocal()
    run = db.query(SocTaskRun).filter(SocTaskRun.task_key == task_key).first()
    assert run.status.value == "success"
    assert run.processed == 3
    assert run.total == 3
    # 最终 stats 以返回值为准（progress stage 已被覆盖）
    assert run.stats_json == {"ok": True}
    db.close()

    # cleanup
    db = TestingSessionLocal()
    db.query(SocTaskRun).filter(SocTaskRun.task_key == task_key).delete()
    db.query(SocTaskRegistry).filter(SocTaskRegistry.task_key == task_key).delete()
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Phase 2.4 修复回归：RunOut.id 必须为 str（原来 model_validate(ORM) 报 500）
# 纯 schema 验证，不依赖 db_session（避免与 drop_all 产生锁冲突）


def test_run_out_id_serialized_as_str():
    """RunOut.model_validate(ORM) 不应再因 UUID 类型报 500。
    回归测试：2026-08-17 修复前 /api/v1/tasks/{key}/runs 报 500。"""
    from app.api.task_observability import RunOut
    from uuid import UUID
    import datetime

    # 模拟 SQLAlchemy ORM 行：id 是 UUID 对象，不是 str
    class FakeRun:
        id = UUID("a8dbcc7f-13e1-4d14-8e68-5571de4a0de7")
        task_key = "test"
        trigger = "scheduled"
        started_at = datetime.datetime.now()
        finished_at = None
        status = "success"
        duration_ms = 100
        error_text = None
        stats_json = None
        total = 5
        processed = 5
        percent = 100
        last_progress_at = None
        correlation_id = None
        host = "test"
        triggered_by_user = None

    # 关键断言：model_validate 成功，id 序列化为 str
    out = RunOut.model_validate(FakeRun())
    assert isinstance(out.id, str), f"id 必须是 str, got {type(out.id).__name__}"
    assert out.id == str(FakeRun.id)

    # 关键断言：model_dump(mode='json') 也能成功
    dumped = out.model_dump(mode="json")
    assert isinstance(dumped["id"], str)
    assert dumped["id"] == str(FakeRun.id)
