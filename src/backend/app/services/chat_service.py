"""
Art Bot 聊天服务（Claude Code CLI 版）

通过本地 `claude` CLI 子进程调用 Anthropic Claude 模型。
相比直接调 Anthropic SDK，CLI 模式的优势：
- 无需管理 ANTHROPIC_API_KEY（CLI 用 OAuth/Keychain 自己鉴权）
- 自动获得 Read/Bash/Grep/Glob 等内置工具
- 内置会话持久化（用 --session-id 复用）
- 流式输出原生日志（stream-json）便于解析

数据流：
    history (DB)  →  拼装 user/assistant 消息
                 →  subprocess.Popen(claude -p ... --session-id <uuid>)
                 →  逐行解析 stream-json
                 →  抽取 assistant 文本增量 yield 出去
                 →  流结束写回 assistant 消息

CLI 关键选项：
    -p                            非交互模式
    --output-format stream-json   JSON Lines 流式输出
    --include-partial-messages    增量分块（边生成边吐）
    --session-id <uuid>           复用同一会话的历史
    --no-session-persistence      不写本地 session 文件
    --append-system-prompt        追加 system prompt
    --allowed-tools               工具白名单
    --effort                      思考深度
    --add-dir                     授权工具可访问的目录
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import AsyncIterator, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)


# Claude Code CLI 内置 system prompt（追加用），不写数据库
ART_BOT_SYSTEM_PROMPT = (
    "你是 AI-miniSOC 安全运营中心的 Art Bot，"
    "一名专业的安全运营助手。请用简洁、结构化的中文回答，"
    "涉及命令、规则、代码请用 Markdown 代码块包裹。"
)


class ClaudeCLIError(RuntimeError):
    """CLI 子进程异常（exit code 非 0、超时、被 kill）"""


class ChatService:
    """聊天服务：会话/消息持久化 + Claude Code CLI 流式调用"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._workspace = self._resolve_workspace()

    # ============== 路径解析 ==============

    @staticmethod
    def _resolve_workspace() -> str:
        """解析 Claude CLI 工作目录，懒建。"""
        ws = settings.CLAUDE_CLI_WORKSPACE
        if ws:
            os.makedirs(ws, exist_ok=True)
            return ws
        # 默认放后端的 tmp 下，按进程 pid 隔离
        default = os.path.join(tempfile.gettempdir(), f"claude-cli-{os.getpid()}")
        os.makedirs(default, exist_ok=True)
        return default

    def _resolve_cli_path(self) -> str:
        """解析 claude 可执行路径，找不到直接抛。"""
        cli = settings.CLAUDE_CLI_PATH
        if os.path.isabs(cli) and os.path.exists(cli):
            return cli
        found = shutil.which(cli)
        if not found:
            raise ClaudeCLIError(
                f"未找到 Claude CLI 可执行: {cli}。"
                f"请设置 CLAUDE_CLI_PATH 或把 claude 加入 PATH。"
            )
        return found

    # ============== 会话 CRUD（保持原签名） ==============

    def create_session(
        self,
        user_id: int,
        title: Optional[str] = None,
    ) -> ChatSession:
        """新建会话，model_name 记录为当前 CLI 模型标识。"""
        session = ChatSession(
            id=uuid.uuid4(),  # 我们自己生成 UUID，CLI 用同一个
            user_id=user_id,
            title=title or "新会话",
            model_name=f"claude-cli:{settings.CLAUDE_CLI_MODEL}",
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

    # ============== 消息流（CLI 子进程） ==============

    def build_history(self, session: ChatSession) -> List[dict]:
        """组装供 CLI 复读的 user/assistant 消息（CLI 自己会处理 system）。
        我们不再传 system prompt——CLI 已通过 --append-system-prompt 注入。
        """
        history: List[dict] = []
        for m in session.messages:
            if m.role in ("user", "assistant"):
                history.append({"role": m.role, "content": m.content})
        return history

    def _build_cli_command(
        self, session: ChatSession, user_message: str
    ) -> List[str]:
        """构造 `claude` 子进程命令。"""
        cli = self._resolve_cli_path()
        cmd: List[str] = [
            cli,
            "-p",                              # 非交互
            user_message,                      # 本轮用户消息
            "--output-format", "stream-json",  # JSON Lines 流
            "--session-id", str(session.id),   # 复用历史
            "--model", settings.CLAUDE_CLI_MODEL,
            "--effort", settings.CLAUDE_CLI_EFFORT,
            "--append-system-prompt", ART_BOT_SYSTEM_PROMPT,
            "--verbose",  # stream-json 必须配合 --verbose
            # 不加 --include-partial-messages：会同时推 thinking + 完整文本，导致重复
        ]
        if settings.CLAUDE_CLI_NO_PERSIST:
            cmd.append("--no-session-persistence")
        if settings.CLAUDE_CLI_DANGEROUSLY_SKIP:
            # 仅在隔离/沙箱环境使用
            cmd.append("--dangerously-skip-permissions")
        elif settings.CLAUDE_CLI_ALLOWED_TOOLS:
            cmd.extend(["--allowedTools", settings.CLAUDE_CLI_ALLOWED_TOOLS])
        return cmd

    async def _read_cli_stream(
        self, proc: asyncio.subprocess.Process
    ) -> AsyncIterator[dict]:
        """逐行读取 CLI 的 stream-json 输出，yield dict。
        每个 JSON 行是单个事件，常见 type：
          - system        初始化
          - assistant     助手消息（含完整 content 块）
          - user          回显用户输入
          - result        最终汇总（含 session_id、cost、duration）
          - stream_event  （开了 include_partial_messages 才有）
        """
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break  # EOF
            try:
                event = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                logger.warning("非 JSON 行，已跳过: %r", line[:200])
                continue
            yield event

    def _extract_text_delta(self, event: dict) -> List[str]:
        """从单个 stream-json 事件中抽取 assistant 文本增量。"""
        etype = event.get("type")

        # 新格式：--include-partial-messages 开启后的 stream_event
        if etype == "stream_event":
            inner = event.get("event", {})
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        return [text]

        # 兜底：完整 assistant 消息事件（可能一次性来一大块）
        if etype == "assistant":
            msg = event.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "text":
                    txt = block.get("text", "")
                    if txt:
                        return [txt]
        return []

    async def stream_chat(
        self,
        session_id: UUID,
        user_id: int,
        new_user_message: str,
    ) -> AsyncIterator[str]:
        """流式生成助手回复，逐 chunk 产出纯文本 delta。

        调用方负责在流结束后调用 `finalize_assistant()` 一次性写入 assistant 消息。
        客户端断开时本生成器会自然终止（asyncio.CancelledError）。
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

        cmd = self._build_cli_command(session, new_user_message)
        logger.info("启动 claude CLI: %s", " ".join(cmd[:6]) + " ...")

        env = os.environ.copy()
        # 强制非交互；CLI 已能自己鉴权
        env["CI"] = "1"
        env["CLAUDE_CODE_ENTRYPOINT"] = "ai-minisoc-api"

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._workspace,
                env=env,
            )
        except FileNotFoundError as e:
            raise ClaudeCLIError(f"启动 CLI 失败: {e}") from e

        try:
            async for event in self._read_cli_stream(proc):
                for piece in self._extract_text_delta(event):
                    yield piece
            # 等子进程退出
            await proc.wait()
            if proc.returncode != 0:
                err_tail = b""
                if proc.stderr is not None:
                    err_tail = await proc.stderr.read() or b""
                err_msg = err_tail.decode("utf-8", errors="replace").strip() or f"exit {proc.returncode}"
                logger.error("claude CLI 异常退出: %s", err_msg[-500:])
                raise ClaudeCLIError(f"CLI 异常退出 (code={proc.returncode}): {err_msg[-300:]}")
        except asyncio.CancelledError:
            # 客户端断开，kill 子进程
            logger.info("客户端断开，终止 claude CLI 进程 pid=%s", proc.pid)
            try:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            except ProcessLookupError:
                pass
            raise
        except Exception:
            # 其它异常也要收尸
            if proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
            raise

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
