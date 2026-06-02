# tests/test_users_api.py
import pytest
from fastapi.testclient import TestClient


def test_get_users_unauthorized(client: TestClient):
    """测试未认证访问"""
    response = client.get("/api/v1/users")
    # 项目用中间件把 401 包成 HTTP 200 + body.code=401
    body = response.json()
    assert body["code"] in (401, 403)
    assert response.status_code == 200  # wrapper 层固定 200


def test_get_users_authorized(client: TestClient, auth_token):
    """测试认证用户访问"""
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    # envelope: {"code": 200, "data": {...}, "msg": "..."}
    data = body["data"]
    assert "items" in data
    assert "total" in data
