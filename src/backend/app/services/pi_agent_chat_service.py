"""
Art Bot 聊天服务（Pi Agent + Agnes AI 版）

通过 AgentProcessManager 调用 Pi Agent，使用 Agnes AI 作为 LLM。
复用了现有的 ChatSession/ChatMessage 数据库表。

数据流：
    history (DB)  →  拼装 user 消息
                 →  AgentProcessManager.get_or_create()
                 →  agent.prompt JSON-RPC 调用
                 →  流式解析 SSE 事件
                 →  抽取 text_delta 增量 yield 出去
                 →  流结束写回 assistant 消息

对比 ClaudeCLI 版本：
    - 优势：无需本地 Claude CLI，支持多模型（Agnes AI）
    - 劣势：暂无内置工具（待 MVP-2 实现）
"""

import asyncio
import json
import logging
import uuid
from typing import AsyncIterator, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import ChatMessage, ChatSession
from app.services.agent_process_manager import AgentProcessManager

logger = logging.getLogger(__name__)


# Art Bot system prompt（用于 SOC 场景）
ART_BOT_SYSTEM_PROMPT = (
    "你是 AI-miniSOC 安全运营中心的 Art Bot，"
    "一名专业的安全运营助手。请用简洁、结构化的中文回答，"
    "涉及命令、规则、代码请用 Markdown 代码块包裹。"
)

# 默认使用配置中心「AI 模型管理」里的模型实例（见 art_bot_model_resolver）
# 这里的 DEFAULT_MODEL 只是「配置缺失 + 旧会话」时的最后兜底。
DEFAULT_MODEL = "openai/glm-4-flash"


class PiAgentChatError(Exception):
    """Pi Agent 调用异常"""


class PiAgentChatService:
    """聊天服务：会话/消息持久化 + Pi Agent 流式调用"""

    # 全局 AgentProcessManager 单例
    _agent_manager: Optional[AgentProcessManager] = None

    @classmethod
    def get_agent_manager(cls) -> AgentProcessManager:
        """获取或创建全局 AgentProcessManager 单例"""
        if cls._agent_manager is None:
            cls._agent_manager = AgentProcessManager()
        return cls._agent_manager

    def __init__(self, db: Session) -> None:
        self.db = db

    # ============== 会话 CRUD ==============

    def create_session(
        self,
        user_id: int,
        title: Optional[str] = None,
    ) -> ChatSession:
        """新建会话"""
        # 模型标识在会话创建时按「配置中心 → AI 模型管理」解析；
        # 解析失败不阻断建会话（后续 stream_chat 会再次解析并抛出可读错误）。
        try:
            from app.services.art_bot_model_resolver import resolve_art_bot_model

            model_name = resolve_art_bot_model(db=self.db).model
        except Exception as e:  # noqa: BLE001
            logger.warning("Art Bot 建会话时解析模型失败，用兜底值：%s", e)
            model_name = DEFAULT_MODEL

        session = ChatSession(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title or "新会话",
            model_name=model_name,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(
        self, user_id: int, session_id: UUID
    ) -> Optional[ChatSession]:
        stmt = (
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_sessions(
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[List[ChatSession], int]:
        total = (
            self.db.execute(
                select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)
            ).scalar()
            or 0
        )
        items = (
            self.db.execute(
                select(ChatSession)
                .where(ChatSession.user_id == user_id)
                .order_by(ChatSession.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return list(items), int(total)

    def delete_session(self, user_id: int, session_id: UUID) -> bool:
        session = self.get_session(user_id, session_id)
        if not session:
            return False
        self.db.delete(session)
        self.db.commit()
        return True

    # ============== 消息 CRUD ==============

    def add_message(
        self,
        session_id: UUID,
        role: str,
        content: str,
        tokens_used: int = 0,
        is_truncated: bool = False,
    ) -> ChatMessage:
        msg = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            tokens_used=tokens_used,
            is_truncated=is_truncated,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def build_history(self, session: ChatSession) -> List[dict]:
        """组装历史消息（用于调试/日志）"""
        history: List[dict] = []
        for m in session.messages:
            if m.role in ("user", "assistant"):
                history.append({"role": m.role, "content": m.content})
        return history

    # ============== 消息流（Pi Agent） ==============

    async def stream_chat(
        self,
        session_id: UUID,
        user_id: int,
        new_user_message: str,
    ) -> AsyncIterator[str]:
        """流式生成助手回复，逐 chunk 产出纯文本 delta。

        调用方负责在流结束后调用 `finalize_assistant()` 一次性写入 assistant 消息。
        """
        session = self.get_session(user_id=user_id, session_id=session_id)
        if session is None:
            raise ValueError(f"session not found: {session_id}")

        # 先把 user 消息持久化
        self.add_message(session.id, role="user", content=new_user_message)

        # 标题自动取首条 user 消息
        if session.title == "新会话":
            session.title = new_user_message[:30]
            self.db.commit()

        # 获取 Agent Process Manager
        manager = self.get_agent_manager()

        # 构造 system prompt（含历史上下文）
        system_prompt = self._build_system_prompt(session)

        try:
            # 解析 Art Bot 应使用的模型（配置中心 → AI 模型管理）
            from app.services.art_bot_model_resolver import build_agent_config

            agent_config = build_agent_config(
                db=self.db,
                model_override=session.model_name or None,
                trace_id=str(uuid.uuid4()),
                system_prompt=system_prompt,
            )

            # 获取或创建 Agent 进程
            proc = await manager.get_or_create(
                session_id=str(session.id),
                role="art-bot",
                config=agent_config,
            )

            # 发送 prompt
            await proc.call(
                "agent.prompt",
                {
                    "sessionId": str(session.id),
                    "userMessage": new_user_message,
                    "model": agent_config.get("model") or DEFAULT_MODEL,
                    "trace_id": str(uuid.uuid4()),
                },
            )

            # 流式监听事件
            async for event in proc.stream_events():
                evt_type = event.get("type", "")
                delta = event.get("delta", "")

                # runner 上报的 LLM 错误（2026-11-10 修：原先被丢弃，
                # 导致「AI 额度用尽」静默表现为「聊天没反应」）
                if evt_type in ("error", "agent_error"):
                    err_text = (
                        event.get("error")
                        or event.get("message")
                        or event.get("params", {}).get("error")
                        or "未知错误"
                    )
                    logger.error(
                        "Art Bot runner 上报错误: session=%s err=%s", session_id, err_text
                    )
                    raise PiAgentChatError(f"AI 服务异常: {err_text}")

                if delta:
                    yield delta

                if evt_type == "agent_end":
                    # Agent 结束，退出循环
                    break

        except asyncio.CancelledError:
            logger.info("client disconnected: session=%s", session_id)
            raise
        except PiAgentChatError:
            raise
        except Exception as e:
            logger.exception("Pi Agent error: session=%s: %s", session_id, e)
            raise PiAgentChatError(f"AI 服务暂不可用: {e}") from e

    def _build_system_prompt(self, session: ChatSession) -> str:
        """构建 system prompt（包含角色定义 + 历史消息）"""
        history_context = ""
        messages = session.messages[-6:]  # 最近 6 条消息作为上下文
        for m in messages:
            if m.role == "user":
                history_context += f"\n用户: {m.content}"
            elif m.role == "assistant":
                history_context += f"\n助手: {m.content}"

        return f"""{ART_BOT_SYSTEM_PROMPT}

{history_context}
"""

    async def finalize_assistant(
        self,
        session_id: UUID,
        content: str,
        is_truncated: bool = False,
        tokens_used: int = 0,
    ) -> ChatMessage:
        """流式结束后一次性写 assistant 消息。"""
        return self.add_message(
            session_id=session_id,
            role="assistant",
            content=content,
            tokens_used=tokens_used,
            is_truncated=is_truncated,
        )
