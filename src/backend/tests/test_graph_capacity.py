"""graph capacity check (OH-3.8, Session #12)

覆盖：
  - 阈值评估纯函数（边数 + P95 by query_type）
  - 消息构造（无触发 None / 单维触发 / 多维触发）
  - 配置加载（默认 + 自定义 yaml）
  - 端点 GET /capacity/status（viewer+ 可读）
  - 端点 POST /capacity/run（admin/operator 触发）
  - 端点权限矩阵：viewer 可读 / 无 token 401 / 跨角色正确

约定：测试库 schema 已由 alembic head 推到 c7d8e9f10a2b。
"""
from __future__ import annotations

import pytest

from app.services.graph import capacity_check as cap_mod


# ============ 纯函数：阈值评估 ============

class TestEvaluateThresholds:
    def test_边数_未超阈(self):
        cfg = cap_mod.CapacityConfig.from_dict({})
        ev = cap_mod.evaluate_thresholds(
            {"edges_total": 100, "p95_by_query_type": {}}, cfg
        )
        assert ev["edges"]["triggered"] is False
        assert ev["edges"]["current"] == 100

    def test_边数_达到阈(self):
        cfg = cap_mod.CapacityConfig.from_dict({})
        ev = cap_mod.evaluate_thresholds(
            {"edges_total": 10000, "p95_by_query_type": {}}, cfg
        )
        assert ev["edges"]["triggered"] is True
        assert ev["edges"]["delta_pct"] == 0.0

    def test_边数_远超阈(self):
        cfg = cap_mod.CapacityConfig.from_dict({})
        ev = cap_mod.evaluate_thresholds(
            {"edges_total": 15000, "p95_by_query_type": {}}, cfg
        )
        assert ev["edges"]["triggered"] is True
        assert ev["edges"]["delta_pct"] == 50.0

    def test_p95_未超阈(self):
        cfg = cap_mod.CapacityConfig.from_dict({"p95_threshold_ms": 500.0})
        ev = cap_mod.evaluate_thresholds(
            {"edges_total": 0, "p95_by_query_type": {"neighbors": 100.0}}, cfg
        )
        assert ev["p95_neighbors"]["triggered"] is False

    def test_p95_超阈(self):
        cfg = cap_mod.CapacityConfig.from_dict({"p95_threshold_ms": 500.0})
        ev = cap_mod.evaluate_thresholds(
            {"edges_total": 0, "p95_by_query_type": {"neighbors": 800.0}}, cfg
        )
        assert ev["p95_neighbors"]["triggered"] is True
        assert ev["p95_neighbors"]["current"] == 800.0

    def test_p95_多个_query_type_独立评估(self):
        cfg = cap_mod.CapacityConfig.from_dict({"p95_threshold_ms": 500.0})
        ev = cap_mod.evaluate_thresholds(
            {
                "edges_total": 0,
                "p95_by_query_type": {
                    "neighbors": 800.0,
                    "paths": 100.0,
                    "impact_scope": 1200.0,
                },
            },
            cfg,
        )
        assert ev["p95_neighbors"]["triggered"] is True
        assert ev["p95_paths"]["triggered"] is False
        assert ev["p95_impact_scope"]["triggered"] is True


# ============ 纯函数：消息构造 ============

class TestBuildAlertMessage:
    def test_无触发_返回_None(self):
        cfg = cap_mod.CapacityConfig.from_dict({})
        ev = cap_mod.evaluate_thresholds(
            {"edges_total": 100, "p95_by_query_type": {"neighbors": 100.0}}, cfg
        )
        assert cap_mod.build_alert_message(ev) is None

    def test_边数触发(self):
        cfg = cap_mod.CapacityConfig.from_dict({})
        ev = cap_mod.evaluate_thresholds(
            {"edges_total": 15000, "p95_by_query_type": {"neighbors": 100.0}}, cfg
        )
        msg = cap_mod.build_alert_message(ev)
        assert msg is not None
        assert "边数 15,000" in msg
        assert "10,000" in msg

    def test_p95触发(self):
        cfg = cap_mod.CapacityConfig.from_dict({"p95_threshold_ms": 500.0})
        ev = cap_mod.evaluate_thresholds(
            {"edges_total": 0, "p95_by_query_type": {"neighbors": 800.0}}, cfg
        )
        msg = cap_mod.build_alert_message(ev)
        assert msg is not None
        assert "P95[neighbors]" in msg
        assert "800.0ms" in msg

    def test_多维同时触发(self):
        cfg = cap_mod.CapacityConfig.from_dict({"p95_threshold_ms": 500.0})
        ev = cap_mod.evaluate_thresholds(
            {
                "edges_total": 15000,
                "p95_by_query_type": {"neighbors": 800.0, "paths": 100.0},
            },
            cfg,
        )
        msg = cap_mod.build_alert_message(ev)
        assert msg is not None
        assert "边数" in msg and "P95" in msg
        assert "neighbors" in msg and "paths" not in msg


# ============ 配置加载 ============

class TestLoadConfig:
    def test_load_config_默认值(self, monkeypatch):
        monkeypatch.setattr(cap_mod, "CONFIG_PATH", __import__("pathlib").Path("/nonexistent.yaml"))
        cfg = cap_mod.load_config()
        assert cfg.enabled is True
        assert cfg.edges_threshold == 10000
        assert cfg.p95_threshold_ms == 500.0
        assert "admin" in cfg.notify_role_codes

    def test_load_config_自定义yaml(self, tmp_path):
        import yaml as _yaml
        p = tmp_path / "cap.yaml"
        p.write_text(_yaml.safe_dump({
            "enabled": True,
            "edges_threshold": 5000,
            "p95_threshold_ms": 300.0,
            "interval_seconds": 60,
            "notify_role_codes": ["admin", "operator"],
            "notification_type": "custom_cap",
        }, allow_unicode=True))
        monkey = pytest.MonkeyPatch()
        monkey.setattr(cap_mod, "CONFIG_PATH", p)
        try:
            cfg = cap_mod.load_config()
            assert cfg.edges_threshold == 5000
            assert cfg.p95_threshold_ms == 300.0
            assert cfg.interval_seconds == 60
            assert cfg.notify_role_codes == ["admin", "operator"]
            assert cfg.notification_type == "custom_cap"
        finally:
            monkey.undo()

    def test_load_config_间隔下限30s(self, monkeypatch):
        cfg = cap_mod.CapacityConfig.from_dict({"interval_seconds": 5})
        assert cfg.interval_seconds == 30


# ============ API 集成 ============

@pytest.fixture
def cap_admin_token(admin_user):
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
def cap_viewer_user(db_session):
    """独立的 viewer 角色用户（不依赖 sample_role=test_role，避免权限不匹配）。"""
    from app.models import User, UserStatus, Role as _Role
    from app.core.security import get_password_hash

    role = db_session.query(_Role).filter_by(code="viewer").first()
    if role is None:
        role = _Role(code="viewer", name="Viewer")
        db_session.add(role)
        db_session.flush()

    user = User(
        username=f"viewer_cap_{id(db_session)}",
        password_hash=get_password_hash("viewer123"),
        email=f"viewer_cap_{id(db_session)}@example.com",
        full_name="Viewer Cap",
        role_id=role.id,
        status=UserStatus.ACTIVE,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def cap_viewer_token(cap_viewer_user):
    from app.core.auth import create_access_token
    return create_access_token(
        data={
            "sub": str(cap_viewer_user.id),
            "username": cap_viewer_user.username,
            "email": cap_viewer_user.email,
            "role_id": cap_viewer_user.role_id,
        }
    )


class TestCapacityAPI:
    def test_get_status_viewer_可读(self, client, cap_viewer_token):
        """viewer 应能 GET /graph/capacity/status（与 perf 看板同级权限）。"""
        res = client.get(
            "/api/v1/graph/capacity/status",
            headers={"Authorization": f"Bearer {cap_viewer_token}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["code"] == 200
        assert "probe" in body["data"]
        assert "thresholds" in body["data"]
        assert body["data"]["thresholds"]["edges_threshold"] == 10000

    def test_get_status_无token_走envelope(self, client):
        # CLAUDE.md §1.1：HTTP 状态码恒 200，错误码在 body.code
        res = client.get("/api/v1/graph/capacity/status")
        assert res.status_code == 200
        assert res.json()["code"] in (401, 403)

    def test_run_admin(self, client, cap_admin_token):
        res = client.post(
            "/api/v1/graph/capacity/run",
            headers={"Authorization": f"Bearer {cap_admin_token}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["code"] == 200

    def test_run_viewer_无权限_403(self, client, cap_viewer_token):
        """viewer 不能触发 run（POST 是 admin/operator 限定）。"""
        res = client.post(
            "/api/v1/graph/capacity/run",
            headers={"Authorization": f"Bearer {cap_viewer_token}"},
        )
        assert res.status_code == 200
        # viewer 被 READ_ONLY_ROLES 拒，返回的 body.code 应非 200
        assert res.json()["code"] != 200
