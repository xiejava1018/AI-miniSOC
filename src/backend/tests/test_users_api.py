# tests/test_users_api.py
import pytest
from fastapi.testclient import TestClient


def test_get_users_unauthorized(client: TestClient):
    """测试未认证访问"""
    response = client.get("/api/v1/users")
    assert response.status_code == 401


def test_get_users_authorized(client: TestClient, auth_token):
    """测试认证用户访问"""
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
