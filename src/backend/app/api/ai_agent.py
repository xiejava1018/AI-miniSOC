"""
AI Agent API — Pi Agent 集成

路由: /api/v1/ai/agent/*

SSE 事件格式（兼容 EventSource）：
    data: {"delta": "...", "session_id": "..."}\n\n
    data: [DONE]\n\n

注意：ResponseWrapperMiddleware 会放过非 `application/json` 响应，
`text/event-stream` 自然不会进入包装逻辑。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.agent_process_manager import AgentProcessManager
from app.api.deps import get_current_user
from app.models import User

logger = logging.getLogger(__name__)

# 全局 Manager 实例 (模块级单例)
_agent_manager: Optional[AgentProcessManager] = None


def get_agent_manager() -> AgentProcessManager:
    """获取或创建全局 AgentProcessManager 单例"""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentProcessManager()
    return _agent_manager


# ======================================================================
# Request/Response Models
# ======================================================================


class AgentPromptRequest(BaseModel):
    """Agent 对话请求"""
    session_id: Optional[str] = None  # 不传则创建新 session
    user_message: str
    model: str = "agnes/agnes-1.5-flash"  # 默认用 Agnes AI
    skills: list[str] = []
    tools: list[str] = []
    system_prompt: Optional[str] = None


class AgentContinueRequest(BaseModel):
    """继续 Agent 对话请求"""
    session_id: str
    user_message: str


# ======================================================================
# SSE 生成器
# ======================================================================


async def _stream_agent_events(
    session_id: str,
    user_message: str,
    trace_id: str,
    model: str,
) -> AsyncIterator[str]:
    """
    AgentProcessManager.stream_events() → SSE 格式

    SSE 格式参考 ai_chat.py:
        data: {"delta": "...", "session_id": "..."}\n\n
        data: [DONE]\n\n
    """
    manager = get_agent_manager()
    full_reply: list[str] = []

    try:
        # 获取或创建进程
        proc = await manager.get_or_create(
            session_id=session_id,
            role="chat",
            config={"model": model, "trace_id": trace_id},
        )

        # 发送 prompt
        await proc.call(
            "agent.prompt",
            {
                "sessionId": session_id,
                "userMessage": user_message,
                "model": model,
                "trace_id": trace_id,
            },
        )

        # 流式监听事件
        async for event in proc.stream_events():
            evt_type = event.get("type", "")
            delta = event.get("delta", "")

            if delta:
                full_reply.append(delta)
                yield f"data: {json.dumps({'delta': delta, 'session_id': session_id}, ensure_ascii=False)}\n\n"

            if evt_type == "tool_execution_start":
                tool_name = event.get("tool", "")
                yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name}, ensure_ascii=False)}\n\n"

            if evt_type == "tool_execution_end":
                tool_name = event.get("tool", "")
                yield f"data: {json.dumps({'type': 'tool_end', 'tool': tool_name}, ensure_ascii=False)}\n\n"

            if evt_type == "agent_end":
                # 完成, 发统计
                yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'total_tokens': len(''.join(full_reply))}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

    except asyncio.TimeoutError:
        logger.warning("Agent stream timeout: session=%s", session_id)
        yield f"data: {json.dumps({'error': 'Agent timeout', 'code': 'timeout', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:  # noqa: BLE001
        logger.exception("Agent stream error: session=%s: %s", session_id, e)
        yield f"data: {json.dumps({'error': str(e), 'code': 'internal_error', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"


# ======================================================================
# 端点
# ======================================================================

router = APIRouter(prefix="/agent", tags=["ai-agent"])


@router.post("/prompt")
async def agent_prompt(
    req: AgentPromptRequest,
    x_trace_id: Optional[str] = Header(None, alias="X-Trace-Id"),
    x_trace_id_auto: Optional[str] = Header(None, alias="trace-id"),
    current_user: User = Depends(get_current_user),
):
    """
    创建/继续 Agent 对话 (SSE 流式)

    Headers:
        X-Trace-Id / trace-id: 可选 trace ID（自动生成）
    """
    trace_id = x_trace_id or x_trace_id_auto or str(uuid.uuid4())
    session_id = req.session_id or str(uuid.uuid4())

    return StreamingResponse(
        _stream_agent_events(
            session_id=session_id,
            user_message=req.user_message,
            trace_id=trace_id,
            model=req.model,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 防 nginx 缓冲
            "X-Session-Id": session_id,
            "X-Trace-Id": trace_id,
        },
    )


@router.get("/sessions")
async def list_agent_sessions(
    current_user: User = Depends(get_current_user),
):
    """列出活跃 Agent session (来自 AgentProcessManager)"""
    manager = get_agent_manager()
    return {"sessions": manager.get_stats()}


@router.post("/sessions/{session_id}/abort")
async def abort_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """中断指定 session"""
    manager = get_agent_manager()
    try:
        proc = manager._processes.get(session_id)
        if proc:
            await proc.kill()
        return {"ok": True, "session_id": session_id}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))
