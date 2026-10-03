"""graph perf alerts (OH-3.7, Session #11)

覆盖：
  - 判据纯函数 _classify_severity / _build_message / evaluate_one_round
  - 落库函数 _persist_round / _mark_resolved（用真 DB session 测）
  - 端点 GET /perf/alerts + POST /perf/alerts/run（API 集成）
  - 配置生效：GRAPH_PERF_ALERT_SUSTAINED_ROUNDS / _WINDOW_MIN_SAMPLES

约定：测试库 schema 已由 alembic head=4d5e6f7a8b9c 推到 c7d8e9f10a2b。
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from app.services.graph import slow_query_monitor as mon_mod


# ============ 纯函数 ============

class TestClassifySeverity:
    def test_未触发_返回_None(self):
        assert mon_mod._classify_severity(100.0, 200.0, 500.0) is None
        assert mon_mod._classify_severity(499.9, 999.9, 500.0) is None

    def test_warning(self):
        assert mon_mod._classify_severity(500.0, 800.0, 500.0) == "warning"
        assert mon_mod._classify_severity(999.0, 1499.0, 500.0) == "warning"

    def test_critical_P95_2x(self):
        assert mon_mod._classify_severity(1000.0, 1500.0, 500.0) == "critical"

    def test_critical_max_3x(self):
        assert mon_mod._classify_severity(700.0, 1500.0, 500.0) == "critical"


class TestBuildMessage:
    def test_warning_message(self):
        m = mon_mod._build_message("neighbors", "warning", 600.0, 500.0, 12)
        assert "[警告]" in m
        assert "neighbors" in m
        assert "600ms" in m
        assert "12" in m

    def test_critical_message(self):
        m = mon_mod._build_message("paths", "critical", 1500.0, 500.0, 20)
        assert "[严重]" in m
        assert "立即扩容" in m


class TestEvaluateOneRound:
    def _snap(self, p95_map, samples_map):
        return {
            "window_size": 200,
            "slow_threshold_ms": 500.0,
            "samples": samples_map,
            "p50_ms": {k: 200.0 for k in samples_map},
            "p95_ms": p95_map,
            "max_ms": {k: 600.0 for k in samples_map},
            "avg_ms": {k: 250.0 for k in samples_map},
            "slow_count": {k: 0 for k in samples_map},
        }

    def test_冷启样本不足_不告警(self):
        snap = self._snap(
            {"neighbors": 1500.0, "paths": 100.0, "impact_scope": 100.0, "vuln_chokepoints": 100.0},
            {"neighbors": 5, "paths": 200, "impact_scope": 200, "vuln_chokepoints": 200},
        )
        sustained = {"neighbors": 0, "paths": 0, "impact_scope": 0, "vuln_chokepoints": 0}
        out = mon_mod.evaluate_one_round(snap, 500.0, sustained)
        assert out == []
        # 冷启 neighbors 不应累计 sustained
        assert sustained["neighbors"] == 0

    def test_不足_sustained_rounds_不告警(self, monkeypatch):
        monkeypatch.setattr(mon_mod.settings, "GRAPH_PERF_ALERT_SUSTAINED_ROUNDS", 3)
        monkeypatch.setattr(mon_mod.settings, "GRAPH_PERF_ALERT_WINDOW_MIN_SAMPLES", 30)
        snap = self._snap(
            {"neighbors": 600.0, "paths": 100.0, "impact_scope": 100.0, "vuln_chokepoints": 100.0},
            {"neighbors": 100, "paths": 100, "impact_scope": 100, "vuln_chokepoints": 100},
        )
        sustained = {"neighbors": 0, "paths": 0, "impact_scope": 0, "vuln_chokepoints": 0}
        # 第一轮 + 第二轮：sustained=1,2 都不到 3 → 不出
        mon_mod.evaluate_one_round(snap, 500.0, sustained)
        assert sustained["neighbors"] == 1
        out2 = mon_mod.evaluate_one_round(snap, 500.0, sustained)
        assert sustained["neighbors"] == 2
        assert out2 == []

    def test_达到_sustained_rounds_告警(self, monkeypatch):
        monkeypatch.setattr(mon_mod.settings, "GRAPH_PERF_ALERT_SUSTAINED_ROUNDS", 3)
        monkeypatch.setattr(mon_mod.settings, "GRAPH_PERF_ALERT_WINDOW_MIN_SAMPLES", 30)
        snap = self._snap(
            {"neighbors": 600.0, "paths": 100.0, "impact_scope": 100.0, "vuln_chokepoints": 100.0},
            {"neighbors": 100, "paths": 100, "impact_scope": 100, "vuln_chokepoints": 100},
        )
        sustained = {"neighbors": 2, "paths": 0, "impact_scope": 0, "vuln_chokepoints": 0}
        out = mon_mod.evaluate_one_round(snap, 500.0, sustained)
        assert len(out) == 1
        a = out[0]
        assert a["query_type"] == "neighbors"
        assert a["severity"] == "warning"
        assert a["p95_ms"] == 600.0
        assert a["threshold_ms"] == 500.0
        assert "[警告]" in a["message"]

    def test_critical_severity(self, monkeypatch):
        monkeypatch.setattr(mon_mod.settings, "GRAPH_PERF_ALERT_SUSTAINED_ROUNDS", 1)
        monkeypatch.setattr(mon_mod.settings, "GRAPH_PERF_ALERT_WINDOW_MIN_SAMPLES", 30)
        snap = {
            "window_size": 200,
            "slow_threshold_ms": 500.0,
            "samples": {"neighbors": 100, "paths": 100, "impact_scope": 100, "vuln_chokepoints": 100},
            "p50_ms": {k: 300.0 for k in ["neighbors"]},
            "p95_ms": {"neighbors": 1200.0, "paths": 100.0, "impact_scope": 100.0, "vuln_chokepoints": 100.0},
            "max_ms": {"neighbors": 1500.0, "paths": 600.0, "impact_scope": 600.0, "vuln_chokepoints": 600.0},
            "avg_ms": {k: 400.0 for k in ["neighbors"]},
            "slow_count": {"neighbors": 5, "paths": 0, "impact_scope": 0, "vuln_chokepoints": 0},
        }
        sustained = {"neighbors": 0, "paths": 0, "impact_scope": 0, "vuln_chokepoints": 0}
        out = mon_mod.evaluate_one_round(snap, 500.0, sustained)
        assert len(out) == 1
        assert out[0]["severity"] == "critical"


# ============ 落库（真 DB；测试库已有 c7d8b9c 表） ============

@pytest.fixture
def db_clean(db_session):
    """每次测试前清空 soc_graph_perf_alerts（test_db）。"""
    from sqlalchemy import text
    db_session.execute(text("DELETE FROM soc_graph_perf_alerts"))
    db_session.commit()
    yield db_session


class TestPersistAndResolve:
    def test_persist_round_写入成功(self, db_clean):
        alerts = [
            {
                "alert_type": "p95_threshold_breach",
                "query_type": "neighbors",
                "severity": "warning",
                "triggered_at": datetime.now(timezone.utc),
                "window_size": 100,
                "p50_ms": 200.0,
                "p95_ms": 600.0,
                "max_ms": 800.0,
                "slow_count": 5,
                "threshold_ms": 500.0,
                "message": "test warning",
                "metadata": "{}",
            }
        ]
        written = mon_mod._persist_round(alerts, db=db_clean)
        assert written == 1

    def test_mark_resolved(self, db_clean):
        # 先写一条未解决
        mon_mod._persist_round(
            [
                {
                    "alert_type": "p95_threshold_breach",
                    "query_type": "neighbors",
                    "severity": "warning",
                    "triggered_at": datetime.now(timezone.utc),
                    "window_size": 100,
                    "p50_ms": 200.0,
                    "p95_ms": 600.0,
                    "max_ms": 800.0,
                    "slow_count": 5,
                    "threshold_ms": 500.0,
                    "message": "test",
                    "metadata": "{}",
                }
            ], db=db_clean
        )
        n = mon_mod._mark_resolved(["neighbors"], db=db_clean)
        assert n == 1

        # 再次调用：未解决的应=0
        n2 = mon_mod._mark_resolved(["neighbors"], db=db_clean)
        assert n2 == 0

    def test_persist_round_空列表_不写(self, db_clean):
        assert mon_mod._persist_round([], db=db_clean) == 0


# ============ API 集成 ============

@pytest.fixture
def client(db_session):
    """FastAPI TestClient（与 conftest 一致：override get_db 到 db_session，no-op lifespan）。"""
    from contextlib import asynccontextmanager
    from fastapi.testclient import TestClient
    from main import app
    from app.core.database import get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield
    app.router.lifespan_context = _noop_lifespan

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def admin_token(admin_user):
    """admin_user 在 conftest 中定义；这里只是 token 化。"""
    from app.core.auth import create_access_token
    return create_access_token(
        data={
            "sub": str(admin_user.id),
            "username": admin_user.username,
            "email": admin_user.email,
            "role_id": admin_user.role_id,
        }
    )


@pytest.fixture
def viewer_user(db_session):
    """额外创建 viewer 角色用户（admin_user 默认是 admin）。"""
    from app.models import User, UserStatus, Role as RoleModel
    from app.core.security import get_password_hash

    role = db_session.query(RoleModel).filter_by(code="viewer").first()
    if role is None:
        role = RoleModel(code="viewer", name="Viewer")
        db_session.add(role)
        db_session.flush()

    user = User(
        username=f"viewer_perf_{id(db_session)}",
        password_hash=get_password_hash("viewer123"),
        email=f"viewer_perf_{id(db_session)}@example.com",
        full_name="Viewer Perf",
        role_id=role.id,
        status=UserStatus.ACTIVE,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def viewer_token(viewer_user):
    from app.core.auth import create_access_token
    return create_access_token(
        data={
            "sub": str(viewer_user.id),
            "username": viewer_user.username,
            "email": viewer_user.email,
            "role_id": viewer_user.role_id,
        }
    )


class TestPerfAlertsAPI:
    def test_list_alerts_viewer可读(self, client, viewer_token, db_clean):
        # 先写一条
        mon_mod._persist_round(
            [
                {
                    "alert_type": "p95_threshold_breach",
                    "query_type": "paths",
                    "severity": "critical",
                    "triggered_at": datetime.now(timezone.utc),
                    "window_size": 100,
                    "p50_ms": 300.0,
                    "p95_ms": 1500.0,
                    "max_ms": 2000.0,
                    "slow_count": 10,
                    "threshold_ms": 500.0,
                    "message": "test critical",
                    "metadata": "{}",
                }
            ], db=db_clean
        )
        res = client.get(
            "/api/v1/graph/perf/alerts?only_unresolved=true&limit=10",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["code"] == 200
        assert body["data"]["total"] == 1
        item = body["data"]["items"][0]
        assert item["query_type"] == "paths"
        assert item["severity"] == "critical"
        assert item["resolved"] is False

    def test_run_alerts_admin(self, client, admin_token):
        res = client.post(
            "/api/v1/graph/perf/alerts/run",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["code"] == 200
        assert "emitted" in body["data"]
        assert "resolved" in body["data"]
        assert "sustained_rounds_required" in body["data"]

    def test_run_alerts_无权限_403(self, client, viewer_token):
        res = client.post(
            "/api/v1/graph/perf/alerts/run",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        # envelope 模式：HTTP 恒 200；错误码走 body.code
        assert res.status_code == 200
        body = res.json()
        # viewer 不在 (admin, operator) 内 → require_role 拒绝 → code=403
        # viewer 也属于 READ_ONLY_ROLES，第二层防御会用「只读角色」文案
        assert body["code"] == 403
        assert ("需要角色" in body["msg"]) or ("只读角色" in body["msg"])

    def test_list_alerts_only_resolved_true(self, client, admin_token, db_clean):
        # 写两条：一条 resolved 一条未
        from sqlalchemy import text
        # 用 test_db（已迁好的 schema）。注意 test_db 由 conftest.db_session
        # 走 Base.metadata.create_all 创建，id 列 server_default=gen_random_uuid() 未必
        # 被同步到 test_db 索引，需要手动调用 pgcrypto 扩展并填 gen_random_uuid()。
        from app.core.database import test_engine, TestingSessionLocal
        db = TestingSessionLocal()
        try:
            db.execute(text('CREATE EXTENSION IF NOT EXISTS pgcrypto'))
            db.execute(text(
                """
                INSERT INTO soc_graph_perf_alerts
                (id, alert_type, query_type, severity, triggered_at, window_size,
                 p50_ms, p95_ms, max_ms, slow_count, threshold_ms,
                 message, resolved, "metadata")
                VALUES
                (gen_random_uuid(),'p95_threshold_breach','neighbors','warning',now(),100,200,600,800,5,500,'u',FALSE,'{}'::jsonb),
                (gen_random_uuid(),'p95_threshold_breach','paths','warning',now() - interval '1 hour',100,200,600,800,5,500,'r',TRUE,'{}'::jsonb)
                """
            ))
            db.commit()
        finally:
            db.close()

        res = client.get(
            "/api/v1/graph/perf/alerts?only_unresolved=true&limit=10",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = res.json()
        assert body["data"]["total"] == 1
        assert body["data"]["items"][0]["query_type"] == "neighbors"

        res2 = client.get(
            "/api/v1/graph/perf/alerts?only_unresolved=false&limit=10",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body2 = res2.json()
        assert body2["data"]["total"] == 2