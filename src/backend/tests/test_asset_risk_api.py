"""
P3 MVP API 冒烟测试（F1.1 风险 + F4.1 反馈 + F2.1 L1 查询降级路径）

鉴权模式对齐 test_role_menus_api.py：建 code='admin' 角色 + 用户 + token。
L1 查询不真调 GLM：monkeypatch ai_budget 拒绝 → 验证诚实降级（§八-C）。
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.user import User, UserStatus
from app.models.role import Role
from app.models import Asset
from main import app


@pytest.fixture
def client(db_session):
    """裸 TestClient（不进 with，不触发 lifespan）——避免与运行中的 dev 后端
    抢 MCP 8100 端口导致挂起；依赖注入覆盖与 conftest.client 等价。"""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _setup_admin(db_session, username="risk_admin"):
    role = Role(name="管理员", code="admin", description="test")
    db_session.add(role)
    db_session.flush()
    user = User(
        username=username,
        password_hash=get_password_hash("admin123"),
        email=f"{username}@example.com",
        full_name="Risk Admin",
        role_id=role.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return user, {"Authorization": f"Bearer {token}"}


def _make_asset(db_session, ip="192.168.0.77", **kw):
    defaults = dict(
        network_segment="3F", asset_ip=ip, asset_status="online",
        asset_type="server", criticality="high", os_name="Ubuntu", os_version="22.04",
        name=f"server-{ip}",
    )
    defaults.update(kw)
    a = Asset(**defaults)
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


# ---------------------------------------------------------------------------
# F1.1 风险评分 API
# ---------------------------------------------------------------------------

class TestRiskAPI:
    def test_batch_score_then_get_risk(self, client, db_session):
        _, headers = _setup_admin(db_session)
        asset = _make_asset(db_session)

        r = client.post("/api/v1/assets/risk/batch-score", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 200, body
        assert body["data"]["stats"]["scored"] >= 1

        r = client.get(f"/api/v1/assets/{asset.id}/risk", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["risk_score"] is not None
        assert "dimensions" in (data["score_breakdown"] or {})

    def test_risk_history(self, client, db_session):
        _, headers = _setup_admin(db_session)
        asset = _make_asset(db_session)
        client.post("/api/v1/assets/risk/batch-score", headers=headers)
        r = client.get(f"/api/v1/assets/{asset.id}/risk/history", headers=headers)
        assert r.status_code == 200
        assert len(r.json()["data"]["history"]) >= 1

    def test_overview(self, client, db_session):
        _, headers = _setup_admin(db_session)
        _make_asset(db_session)
        client.post("/api/v1/assets/risk/batch-score", headers=headers)
        r = client.get("/api/v1/assets/risk/overview", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert set(data["distribution"].keys()) == {"low", "medium", "high", "critical", "na"}
        assert "budget" in data

    def test_rules_get_put_and_validation(self, client, db_session):
        _, headers = _setup_admin(db_session)
        r = client.get("/api/v1/assets/risk/rules", headers=headers)
        assert r.status_code == 200
        assert "weights" in r.json()["data"]["rules"]

        # 非法权重 → 400
        r = client.put("/api/v1/assets/risk/rules", headers=headers,
                       json={"override": {"weights": {"exposure": 0.9, "health": 0.25, "alerts": 0.25, "importance": 0.2}}})
        assert r.json()["code"] == 400

        # 合法调整 → 200，且审计已落
        r = client.put("/api/v1/assets/risk/rules", headers=headers,
                       json={"override": {"exposure": {"per_port_score": 30}}})
        assert r.json()["code"] == 200
        from app.models.audit_log import AuditLog
        assert db_session.query(AuditLog).filter_by(resource_name="risk_rules").count() == 1

    def test_risk_requires_auth(self, client):
        r = client.get("/api/v1/assets/risk/overview")
        # 约定：HTTP 恒 200，业务码在 body.code（CLAUDE.md 注意事项 11）
        assert r.json()["code"] == 401


# ---------------------------------------------------------------------------
# F4.1 反馈 API
# ---------------------------------------------------------------------------

class TestFeedbackAPI:
    def test_submit_and_summary(self, client, db_session):
        _, headers = _setup_admin(db_session, username="fb_admin")
        r = client.post("/api/v1/ai/feedback", headers=headers, json={
            "target_type": "risk_summary", "target_id": "any-asset-id", "rating": "up",
        })
        assert r.json()["code"] == 200
        r = client.post("/api/v1/ai/feedback", headers=headers, json={
            "target_type": "risk_summary", "target_id": "any-asset-id", "rating": "down",
            "comment": "端口数不对",
        })
        assert r.json()["code"] == 200

        r = client.get("/api/v1/ai/feedback/summary", headers=headers)
        data = r.json()["data"]
        row = [s for s in data["summary"] if s["target_type"] == "risk_summary"][0]
        assert row["total"] == 2 and row["up"] == 1 and row["down"] == 1

    def test_invalid_rating_rejected(self, client, db_session):
        _, headers = _setup_admin(db_session, username="fb_admin2")
        r = client.post("/api/v1/ai/feedback", headers=headers, json={
            "target_type": "query", "target_id": "x", "rating": "meh",
        })
        # pydantic 校验失败同样被包装为 envelope（HTTP 200 + code=422）
        assert r.json()["code"] == 422


# ---------------------------------------------------------------------------
# F2.1 L1 查询 API（降级路径，不真调 GLM）
# ---------------------------------------------------------------------------

class TestAskAPI:
    def test_budget_exhausted_degrades_honestly(self, client, db_session, monkeypatch):
        """预算拒绝 → 明确提示 + 引导筛选器（§八-C），不猜参数"""
        _, headers = _setup_admin(db_session, username="ask_admin")
        monkeypatch.setattr("app.services.asset_query.ai_budget.allow", lambda: False)
        r = client.post("/api/v1/assets/ask", headers=headers,
                        json={"question": "有哪些 Windows 服务器？"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["intent"] == "unavailable"
        assert "筛选器" in data["message"]

    def test_empty_question(self, client, db_session):
        _, headers = _setup_admin(db_session, username="ask_admin2")
        r = client.post("/api/v1/assets/ask", headers=headers, json={"question": "  "})
        assert r.json()["data"]["intent"] == "error"

    def test_history_requires_auth(self, client):
        r = client.get("/api/v1/assets/ask/history")
        assert r.json()["code"] == 401
