"""
Art Bot 聊天 API

支持两种后端：
- Pi Agent + Agnes AI（默认）
- Claude Code CLI（备选，通过环境变量切换）

API 端点：
- POST /ai/chat             新建会话 + 发起首轮对话（SSE 流式）
- POST /ai/chat/{session_id}  继续对话（SSE 流式）
- GET  /ai/chat/sessions    会话列表（分页）
- GET  /ai/chat/sessions/{id}/messages  消息历史
- DELETE /ai/chat/sessions/{id}  删除会话

SSE 事件格式：
    data: {"delta": "...", "session_id": "..."}\n\n
    data: {"delta": "...", "session_id": "..."}\n\n
    data: [DONE]\n\n

注意：ResponseWrapperMiddleware 会放过非 `application/json` 响应，
`text/event-stream` 自然不会进入包装逻辑。
"""

import asyncio
import json
import logging
import os
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import User
from app.schemas.chat import (
    ChatContinueRequest,
    ChatCreateRequest,
    ChatMessageOut,
    ChatSessionDetailOut,
    ChatSessionListResponse,
    ChatSessionOut,
)
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["art-bot"])

# 决定使用哪种后端：pi_agent（默认）或 claude_cli
CHAT_BACKEND = os.getenv("CHAT_BACKEND", "pi_agent").lower()
logger.info(f"[Art Bot] Using chat backend: {CHAT_BACKEND}")

if CHAT_BACKEND == "pi_agent":
    from app.services.pi_agent_chat_service import PiAgentChatService as ChatService, PiAgentChatError as ChatError
    logger.info("[Art Bot] Pi Agent + Agnes AI backend enabled")
elif CHAT_BACKEND == "claude_cli":
    from app.services.chat_service import ChatService, ClaudeCLIError as ChatError
    logger.info("[Art Bot] Claude CLI backend enabled")
else:
    raise ValueError(f"Invalid CHAT_BACKEND: {CHAT_BACKEND}. Must be 'pi_agent' or 'claude_cli'")


def _session_to_out(s) -> ChatSessionOut:
    return ChatSessionOut.model_validate(s)


def _message_to_out(m) -> ChatMessageOut:
    return ChatMessageOut.model_validate(m)


async def _sse_generator(
    service: ChatService,
    session_id: uuid.UUID,
    user_id: int,
    user_message: str,
) -> AsyncIterator[str]:
    """通用 SSE 生成器：

    1. 调 service.stream_chat 拿增量文本
    2. 累加成完整回复
    3. 收尾：一次写 assistant 消息 + 发通知
    4. 客户端断开时优雅退出（CancelledError 透传，由 FastAPI 清理）
    """
    full_reply: list[str] = []
    try:
        async for piece in service.stream_chat(
            session_id=session_id,
            user_id=user_id,
            new_user_message=user_message,
        ):
            full_reply.append(piece)
            payload = json.dumps(
                {"delta": piece, "session_id": str(session_id)},
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"
    except asyncio.CancelledError:
        # 客户端断开，标记残缺并退出
        logger.info("client disconnected, mid-stream; session=%s", session_id)
        if full_reply:
            await service.finalize_assistant(
                session_id=session_id,
                content="".join(full_reply),
                is_truncated=True,
            )
        raise
    except ChatError as e:
        # AI 服务异常
        logger.error("chat backend error session=%s: %s", session_id, e)
        err = json.dumps(
            {
                "error": f"AI 服务暂不可用: {e}",
                "code": "chat_error",
                "session_id": str(session_id),
            },
            ensure_ascii=False,
        )
        yield f"data: {err}\n\n"
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("stream error session=%s: %s", session_id, e)
        err = json.dumps({"error": str(e), "session_id": str(session_id)}, ensure_ascii=False)
        yield f"data: {err}\n\n"
        if full_reply:
            await service.finalize_assistant(
                session_id=session_id,
                content="".join(full_reply),
                is_truncated=True,
            )
        return

    # 正常收尾：写 assistant 消息 + 触发完成通知
    if full_reply:
        await service.finalize_assistant(
            session_id=session_id,
            content="".join(full_reply),
        )
        try:
            notif = NotificationService(service.db)
            await notif.create(
                user_id=user_id,
                type="ai_done",
                title="Art Bot 已生成回答",
                content=f"已生成 {len(''.join(full_reply))} 字，点击查看会话",
                link=f"/art-bot?session={session_id}",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("failed to push ai_done notification: %s", e)

    yield "data: [DONE]\n\n"


@router.post("")
async def create_and_chat(
    request: ChatCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建会话并发起首轮流式对话"""
    service = ChatService(db)
    session = service.create_session(user_id=current_user.id)
    return StreamingResponse(
        _sse_generator(service, session.id, current_user.id, request.message.content),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 防 nginx 缓冲
            "X-Session-Id": str(session.id),
            "X-Chat-Backend": CHAT_BACKEND,
        },
    )


@router.post("/{session_id}")
async def continue_chat(
    session_id: uuid.UUID,
    request: ChatContinueRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """在已有 session 上继续对话（流式）"""
    service = ChatService(db)
    session = service.get_session(user_id=current_user.id, session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")

    return StreamingResponse(
        _sse_generator(service, session.id, current_user.id, request.message.content),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": str(session.id),
            "X-Chat-Backend": CHAT_BACKEND,
        },
    )


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_sessions(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ChatService(db)
    items, total = service.list_sessions(user_id=current_user.id, page=page, page_size=page_size)
    return ChatSessionListResponse(
        total=total,
        items=[_session_to_out(s) for s in items],
        page=page,
        page_size=page_size,
    )


@router.get("/sessions/{session_id}", response_model=ChatSessionDetailOut)
async def get_session_detail(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ChatService(db)
    session = service.get_session(user_id=current_user.id, session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return ChatSessionDetailOut(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        model_name=session.model_name,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[_message_to_out(m) for m in session.messages],
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ChatService(db)
    ok = service.delete_session(user_id=current_user.id, session_id=session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return {"deleted": True, "id": str(session_id)}
