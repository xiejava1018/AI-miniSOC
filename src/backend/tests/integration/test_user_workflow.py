"""
用户生命周期集成测试

测试用户从创建到删除的完整生命周期

P3-T2：HTTP 状态码恒 200，业务成功/失败通过 body.code 区分。
原断言 assert response.status_code == 201/200/404 应改为 body["code"] 断言。
"""
import pytest
from fastapi.testclient import TestClient


def _assert_envelope(resp, expected_code: int) -> dict:
    """统一响应包装下，HTTP 200 + body.code=expected_code 表示业务成功。"""
    assert resp.status_code == 200, f"HTTP 期望 200，实际 {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["code"] == expected_code, (
        f"业务码期望 {expected_code}，实际 {body.get('code')}: {body.get('msg')}"
    )
    return body


def test_user_lifecycle(client: TestClient, admin_token: str):
    """测试用户完整生命周期（P3-T2：envelope 业务码断言）"""

    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. 创建用户
    user_data = {
        "username": "lifecycle_test",
        "password": "Test123456",
        "email": "lifecycle@example.com",
        "full_name": "生命周期测试",
        "role_id": 2,
    }

    resp = client.post("/api/v1/users", json=user_data, headers=headers)
    user = _assert_envelope(resp, 201)
    user_id = user["data"]["id"]

    # 2. 查询用户
    resp = client.get(f"/api/v1/users/{user_id}", headers=headers)
    body = _assert_envelope(resp, 200)
    assert body["data"]["username"] == "lifecycle_test"

    # 3. 更新用户
    update_data = {"full_name": "已更新"}
    resp = client.put(f"/api/v1/users/{user_id}", json=update_data, headers=headers)
    body = _assert_envelope(resp, 200)
    assert body["data"]["full_name"] == "已更新"

    # 4. 锁定用户
    lock_data = {"is_locked": True, "lock_reason": "测试锁定"}
    resp = client.post(f"/api/v1/users/{user_id}/lock", json=lock_data, headers=headers)
    body = _assert_envelope(resp, 200)
    assert body["data"]["is_locked"] is True

    # 5. 解锁用户
    lock_data = {"is_locked": False}
    resp = client.post(f"/api/v1/users/{user_id}/lock", json=lock_data, headers=headers)
    body = _assert_envelope(resp, 200)
    assert body["data"]["is_locked"] is False

    # 6. 删除用户
    resp = client.delete(f"/api/v1/users/{user_id}", headers=headers)
    _assert_envelope(resp, 200)

    # 7. 验证已删除（业务码应为 404）
    resp = client.get(f"/api/v1/users/{user_id}", headers=headers)
    _assert_envelope(resp, 404)
