"""
测试通知服务的 CRUD + WebSocket 推送
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import select

from app.models import Notification
from app.services.notification_service import NotificationService
from app.services.ws_manager import ws_manager


@pytest.fixture
def fresh_manager():
    """每个测试重置 ws_manager 单例"""
    ws_manager._connections.clear()
    yield ws_manager
    ws_manager._connections.clear()


@pytest.mark.unit
def test_create_notification_persists(db_session, fresh_manager):
    """create() 应入库 + 触发 WS 推送"""
    svc = NotificationService(db_session)
    notif = asyncio.run(
        svc.create(user_id=1, type="test", title="Hello", content="World")
    )

    assert notif.id is not None
    assert notif.user_id == 1
    assert notif.type == "test"
    assert notif.title == "Hello"
    assert notif.is_read is False

    # 重新查询确认入库
    fetched = db_session.execute(
        select(Notification).where(Notification.id == notif.id)
    ).scalar_one()
    assert fetched.title == "Hello"


@pytest.mark.unit
def test_unread_count(db_session, fresh_manager):
    """unread_count 应只统计 is_read=False"""
    svc = NotificationService(db_session)
    asyncio.run(svc.create(user_id=1, type="test", title="A"))
    asyncio.run(svc.create(user_id=1, type="test", title="B"))
    asyncio.run(svc.create(user_id=2, type="test", title="other user"))

    assert svc.unread_count(user_id=1) == 2
    assert svc.unread_count(user_id=2) == 1
    assert svc.unread_count(user_id=999) == 0


@pytest.mark.unit
def test_mark_read_filters_by_user(db_session, fresh_manager):
    """mark_read 应只允许标记本人通知"""
    svc = NotificationService(db_session)
    n1 = asyncio.run(svc.create(user_id=1, type="test", title="A"))
    n2 = asyncio.run(svc.create(user_id=2, type="test", title="B"))

    # 用户 1 标记用户 2 的通知：失败
    assert svc.mark_read(user_id=1, notif_id=n2.id) is False
    # 用户 1 标记自己的：成功
    assert svc.mark_read(user_id=1, notif_id=n1.id) is True
    assert svc.unread_count(user_id=1) == 0


@pytest.mark.unit
def test_mark_all_read(db_session, fresh_manager):
    """mark_all_read 应仅影响本人未读"""
    svc = NotificationService(db_session)
    asyncio.run(svc.create(user_id=1, type="test", title="A"))
    asyncio.run(svc.create(user_id=1, type="test", title="B"))
    asyncio.run(svc.create(user_id=2, type="test", title="other"))

    updated = svc.mark_all_read(user_id=1)
    assert updated == 2
    assert svc.unread_count(user_id=1) == 0
    assert svc.unread_count(user_id=2) == 1


@pytest.mark.unit
def test_list_for_user_pagination(db_session, fresh_manager):
    """分页 + 排序应正常"""
    svc = NotificationService(db_session)
    for i in range(5):
        asyncio.run(svc.create(user_id=1, type="test", title=f"msg-{i}"))

    items, total = svc.list_for_user(user_id=1, page=1, page_size=3)
    assert total == 5
    assert len(items) == 3
    # 默认按 created_at 倒序
    assert items[0].title == "msg-4"

    items2, _ = svc.list_for_user(user_id=1, page=2, page_size=3)
    assert len(items2) == 2
    assert items2[0].title == "msg-1"
