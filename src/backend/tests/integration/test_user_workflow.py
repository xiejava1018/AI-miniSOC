"""
用户生命周期集成测试

测试用户从创建到删除的完整生命周期
"""
import pytest
from fastapi.testclient import TestClient


def test_user_lifecycle(client: TestClient, admin_token: str):
    """测试用户完整生命周期"""

    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. 创建用户
    user_data = {
        "username": "lifecycle_test",
        "password": "Test123456",
        "email": "lifecycle@example.com",
        "full_name": "生命周期测试",
        "role_id": 2
    }

    response = client.post("/api/v1/users", json=user_data, headers=headers)
    assert response.status_code == 201
    user = response.json()
    user_id = user["id"]

    # 2. 查询用户
    response = client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["username"] == "lifecycle_test"

    # 3. 更新用户
    update_data = {"full_name": "已更新"}
    response = client.put(f"/api/v1/users/{user_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["full_name"] == "已更新"

    # 4. 锁定用户
    lock_data = {"is_locked": True, "lock_reason": "测试锁定"}
    response = client.post(f"/api/v1/users/{user_id}/lock", json=lock_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["is_locked"] is True

    # 5. 解锁用户
    lock_data = {"is_locked": False}
    response = client.post(f"/api/v1/users/{user_id}/lock", json=lock_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["is_locked"] is False

    # 6. 删除用户
    response = client.delete(f"/api/v1/users/{user_id}", headers=headers)
    assert response.status_code == 200

    # 7. 验证已删除
    response = client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert response.status_code == 404
