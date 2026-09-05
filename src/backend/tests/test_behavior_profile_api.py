"""行为画像 API 路由级测试（F2.2 教训：service 测过 ≠ 路由通）。

envelope 口径：HTTP 恒 200，业务错误在 body.code。
"""

import datetime as dt

import pytest

from app.models.behavior_profile import BehaviorProfile


def _mk_snapshot(ip="192.168.77.7", date=None, status="ok", total=100,
                 traffic="human", confidence=80):
    return BehaviorProfile(
        asset_id=None, ip=ip, profile_date=date or dt.date.today() - dt.timedelta(days=1),
        status=status, total=total,
        by_hour=[0] * 24, wd_hour=[[0] * 24 for _ in range(7)],
        by_block={"深夜": 10}, cat_share={"AI 工具": 30.0},
        layer_visit={"ACT": 70, "SYS": 30},
        tags=[{"name": "夜猫子", "alias": "野猫子"}],
        traffic_type=traffic, confidence=confidence,
    )


@pytest.fixture()
def _seed(db_session):
    db_session.add(_mk_snapshot())
    db_session.add(_mk_snapshot(status="gap", total=0, confidence=0,
                                date=dt.date.today() - dt.timedelta(days=2)))
    db_session.commit()


H = {"Authorization": "Bearer dummy"}


@pytest.fixture()
def real_admin_token(db_session):
    """conftest.admin_user 绑的是 test_role（is_admin=False），需自建 code='admin' 角色。"""
    from app.core.auth import create_access_token
    from app.core.security import get_password_hash
    from app.models.role import Role
    from app.models.user import User, UserStatus

    role = Role(name="行为画像管理员", code="admin")
    db_session.add(role)
    db_session.flush()
    user = User(
        username="bp_admin", password_hash=get_password_hash("x"),
        email="bp@example.com", full_name="BP Admin",
        role_id=role.id, status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return create_access_token(data={"sub": str(user.id), "username": user.username})


def test_profile_requires_auth(client, _seed):
    r = client.get("/api/v1/behavior-profile/192.168.77.7")
    body = r.json()
    assert r.status_code == 200 and body["code"] in (401,)


def test_profile_admin_ok(client, db_session, real_admin_token, _seed):
    r = client.get("/api/v1/behavior-profile/192.168.77.7?days=7",
                   headers={"Authorization": f"Bearer {real_admin_token}"})
    body = r.json()
    assert body["code"] == 200, body
    data = body["data"]
    assert data["ip"] == "192.168.77.7"
    assert data["total"] == 100          # gap 日不计入 total
    assert data["gap_days"] == 1
    assert data["traffic_type"] == "human"
    assert data["tags"][0]["alias"] == "野猫子"
    assert len(data["daily"]) == 2       # 含 gap 占位行


def test_profile_404_when_empty(client, real_admin_token):
    r = client.get("/api/v1/behavior-profile/10.255.255.1",
                   headers={"Authorization": f"Bearer {real_admin_token}"})
    assert r.json()["code"] == 404


def test_profile_rejects_non_admin(client, admin_token, _seed):
    """X1：非 admin/auditor 角色应被拒（body.code=403）"""
    r = client.get("/api/v1/behavior-profile/192.168.77.7",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.json()["code"] == 403


def test_domains_endpoint(client, real_admin_token, _seed):
    r = client.get("/api/v1/behavior-profile/192.168.77.7/domains",
                   headers={"Authorization": f"Bearer {real_admin_token}"})
    assert r.json()["code"] == 200


def test_trend_endpoint(client, real_admin_token, _seed):
    r = client.get("/api/v1/behavior-profile/192.168.77.7/trend?days=30",
                   headers={"Authorization": f"Bearer {real_admin_token}"})
    body = r.json()
    assert body["code"] == 200
    assert len(body["data"]["items"]) == 2
    assert any(i["status"] == "gap" for i in body["data"]["items"])


def test_list_endpoint(client, real_admin_token, _seed):
    r = client.get("/api/v1/behavior-profile/list",
                   headers={"Authorization": f"Bearer {real_admin_token}"})
    body = r.json()
    assert body["code"] == 200
    assert body["data"]["total"] >= 1   # gap 行不进列表
    item = body["data"]["items"][0]
    assert item["ip"] == "192.168.77.7"
    assert "night_share" in item


def test_list_traffic_type_filter(client, real_admin_token, _seed):
    r = client.get("/api/v1/behavior-profile/list?traffic_type=machine",
                   headers={"Authorization": f"Bearer {real_admin_token}"})
    body = r.json()
    assert body["code"] == 200
    assert body["data"]["total"] == 0   # 只有 human 主体


def test_refresh_requires_permission(client, real_admin_token, _seed):
    """refresh 走 require_button_permission；admin bypass 但菜单不存在时行为=放行 admin"""
    r = client.post("/api/v1/behavior-profile/192.168.77.7/refresh",
                    headers={"Authorization": f"Bearer {real_admin_token}"})
    # 无 Loki 环境下可能 503（envelope code 503），但绝不能 404/405 路由不通
    assert r.json()["code"] in (200, 503)
