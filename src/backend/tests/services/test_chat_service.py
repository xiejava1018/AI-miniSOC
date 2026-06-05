"""
测试聊天服务的会话/消息持久化与 Claude Code CLI 流式调用

CLI 子进程通过 monkeypatch 替换为 fake，不真实启动 claude。
"""

import asyncio
import json
import sys
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from sqlalchemy import select

from app.models import ChatSession, ChatMessage
from app.services.chat_service import ChatService, ClaudeCLIError


def _run_async(coro):
    """在同步测试里跑协程，避开 pytest 的事件循环冲突。
    用独立 event_loop 而不是 asyncio.run()。
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============== Stream-JSON 测试样本 ==============

# include_partial_messages 开启时典型的 stream-json 行
STREAM_EVENT_TEXT_DELTA = {
    "type": "stream_event",
    "event": {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": "你好"},
    },
}

STREAM_EVENT_ANOTHER = {
    "type": "stream_event",
    "event": {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": "，我是 Art Bot"},
    },
}

STREAM_EVENT_RESULT = {
    "type": "result",
    "session_id": "fake-session",
    "duration_ms": 1234,
}

# 不应该产出文本的事件
STREAM_EVENT_TOOL_USE = {
    "type": "stream_event",
    "event": {
        "type": "content_block_start",
        "index": 1,
        "content_block": {"type": "tool_use", "id": "tool_1", "name": "Read"},
    },
}


# ============== Fixtures ==============

class FakeProcess:
    """替代 asyncio.subprocess.Process 的假对象。"""

    def __init__(
        self,
        stdout_lines: list[bytes] | None = None,
        stderr: bytes = b"",
        returncode: int = 0,
        pid: int = 99999,
    ):
        self.stdout = _FakeStream(stdout_lines or [])
        self.stderr = _FakeStream([stderr] if stderr else [])
        self.returncode: int | None = None
        self._returncode = returncode
        self.pid = pid

    async def wait(self) -> int:
        self.returncode = self._returncode
        return self.returncode

    def terminate(self) -> None:
        # 测试里不真正发信号
        if self.returncode is None:
            self.returncode = -15

    def kill(self) -> None:
        if self.returncode is None:
            self.returncode = -9


class _FakeStream:
    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)
        self._empty = len(self._chunks) == 0

    async def readline(self) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    async def read(self) -> bytes:
        if self._empty:
            return b""
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


@pytest.fixture
def fake_proc_factory():
    """返回一个工厂：接收 stdout JSON 行 list，生成 FakeProcess。"""
    def _make(stdout_dicts: list[dict], stderr: bytes = b"", returncode: int = 0):
        lines = [json.dumps(d).encode("utf-8") + b"\n" for d in stdout_dicts]
        return FakeProcess(stdout_lines=lines, stderr=stderr, returncode=returncode)
    return _make


@pytest.fixture
def patch_create_subprocess(monkeypatch, fake_proc_factory):
    """把 asyncio.create_subprocess_exec 替换为记录命令并返回 fake proc。"""
    captured: dict = {}

    async def fake_exec(*args, **kwargs):
        captured["cmd"] = list(args)
        captured["kwargs"] = kwargs
        # 调用方会传 stdout_lines，我们用 sentinel 让测试显式注入
        captured["proc"] = fake_proc_factory(
            captured.get("stdout_lines", [STREAM_EVENT_RESULT])
        )
        return captured["proc"]

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return captured


@pytest.fixture
def mock_glm_client():
    """占位：保留旧 fixture 防止外部导入失败，本服务已不依赖 GLM。"""
    yield MagicMock()


@pytest.fixture
def chat_test_user(db_session, test_user):
    return test_user


# ============== CRUD ==============

@pytest.mark.unit
def test_create_session_persists(db_session, chat_test_user):
    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id, title="测试会话")
    import uuid as _uuid
    assert session.id is not None
    # 我们自己用 uuid.uuid4() 生成主键，必须能转回 UUID
    assert isinstance(session.id, _uuid.UUID)
    assert session.user_id == 1
    assert session.title == "测试会话"
    # model_name 标记为 CLI
    assert "claude-cli" in session.model_name


@pytest.mark.unit
def test_add_message_and_get_session(db_session, chat_test_user):
    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)
    m1 = svc.add_message(session.id, "user", "你好")
    m2 = svc.add_message(session.id, "assistant", "你好，我是 Art Bot")

    fetched = svc.get_session(user_id=chat_test_user.id, session_id=session.id)
    assert fetched is not None
    assert len(fetched.messages) == 2
    assert fetched.messages[0].role == "user"
    assert fetched.messages[1].content == "你好，我是 Art Bot"


@pytest.mark.unit
def test_get_session_filters_by_user(db_session, chat_test_user, admin_user):
    svc = ChatService(db_session)
    s1 = svc.create_session(user_id=chat_test_user.id)
    s2 = svc.create_session(user_id=admin_user.id)

    assert svc.get_session(user_id=chat_test_user.id, session_id=s2.id) is None
    assert svc.get_session(user_id=chat_test_user.id, session_id=s1.id) is not None


@pytest.mark.unit
def test_delete_session_cascades(db_session, chat_test_user):
    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)
    svc.add_message(session.id, "user", "hi")

    ok = svc.delete_session(user_id=chat_test_user.id, session_id=session.id)
    assert ok is True

    msgs = db_session.execute(
        select(ChatMessage).where(ChatMessage.session_id == session.id)
    ).scalars().all()
    assert len(msgs) == 0


@pytest.mark.unit
def test_list_sessions_orders_by_updated(db_session, chat_test_user):
    svc = ChatService(db_session)
    s1 = svc.create_session(user_id=chat_test_user.id, title="old")
    s2 = svc.create_session(user_id=chat_test_user.id, title="new")

    import time
    time.sleep(0.05)
    s1.title = "old (touched)"
    db_session.commit()

    items, total = svc.list_sessions(user_id=chat_test_user.id)
    assert total == 2
    assert items[0].id == s1.id
    assert items[1].id == s2.id


@pytest.mark.unit
def test_build_history_skips_system_role_in_db(db_session, chat_test_user):
    """build_history 应只取 user/assistant。CLI 自行处理 system prompt。"""
    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)
    svc.add_message(session.id, "user", "u1")
    svc.add_message(session.id, "assistant", "a1")
    svc.add_message(session.id, "system", "should be ignored")  # noqa

    history = svc.build_history(session)
    # 2 条（CLI 自己注入 system）
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "u1"}
    assert history[1] == {"role": "assistant", "content": "a1"}


# ============== CLI 命令拼装 ==============

@pytest.mark.unit
def test_build_cli_command_contains_session_id_and_prompt(monkeypatch, db_session, chat_test_user):
    """_build_cli_command 必须包含 -p、--session-id、--output-format stream-json。"""
    monkeypatch.setattr(
        "app.services.chat_service.settings.CLAUDE_CLI_PATH", "/usr/local/bin/claude"
    )
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_NO_PERSIST", True)
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_DANGEROUSLY_SKIP", False)
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_ALLOWED_TOOLS", "")
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_MODEL", "sonnet")
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_EFFORT", "medium")
    monkeypatch.setattr("app.services.chat_service.os.path.exists", lambda p: True)

    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)
    cmd = svc._build_cli_command(session, "请分析这条告警")

    assert "-p" in cmd
    assert "请分析这条告警" in cmd
    assert "--output-format" in cmd
    idx = cmd.index("--output-format")
    assert cmd[idx + 1] == "stream-json"
    assert "--include-partial-messages" in cmd
    assert "--session-id" in cmd
    assert cmd[cmd.index("--session-id") + 1] == str(session.id)
    assert "--no-session-persistence" in cmd


@pytest.mark.unit
def test_build_cli_command_contains_verbose(monkeypatch, db_session, chat_test_user):
    """stream-json 模式必须带 --verbose，否则 CLI 拒绝输出。"""
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_PATH", "/usr/bin/claude")
    monkeypatch.setattr("app.services.chat_service.os.path.exists", lambda p: True)

    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)
    cmd = svc._build_cli_command(session, "hi")

    assert "--verbose" in cmd


@pytest.mark.unit
def test_build_cli_command_adds_allowed_tools_when_skip_disabled(
    monkeypatch, db_session, chat_test_user
):
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_PATH", "/usr/bin/claude")
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_NO_PERSIST", True)
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_DANGEROUSLY_SKIP", False)
    monkeypatch.setattr(
        "app.services.chat_service.settings.CLAUDE_CLI_ALLOWED_TOOLS", "Read,Bash,Grep"
    )
    # 让 _resolve_cli_path 不再校验文件存在
    monkeypatch.setattr("app.services.chat_service.os.path.exists", lambda p: True)

    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)
    cmd = svc._build_cli_command(session, "hi")

    assert "--allowedTools" in cmd
    assert cmd[cmd.index("--allowedTools") + 1] == "Read,Bash,Grep"
    assert "--dangerously-skip-permissions" not in cmd


@pytest.mark.unit
def test_build_cli_command_uses_dangerously_skip_when_enabled(
    monkeypatch, db_session, chat_test_user
):
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_PATH", "/usr/bin/claude")
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_NO_PERSIST", True)
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_DANGEROUSLY_SKIP", True)
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_ALLOWED_TOOLS", "")
    monkeypatch.setattr("app.services.chat_service.os.path.exists", lambda p: True)

    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)
    cmd = svc._build_cli_command(session, "hi")

    assert "--dangerously-skip-permissions" in cmd
    assert "--allowedTools" not in cmd


@pytest.mark.unit
def test_resolve_cli_path_raises_when_missing(monkeypatch, db_session):
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_PATH", "/nonexistent/claude")
    svc = ChatService(db_session)
    with pytest.raises(ClaudeCLIError, match="未找到 Claude CLI"):
        svc._resolve_cli_path()


@pytest.mark.unit
def test_resolve_cli_path_uses_which(monkeypatch, db_session):
    # 模拟 PATH 中存在
    monkeypatch.setattr("app.services.chat_service.settings.CLAUDE_CLI_PATH", "claude")
    monkeypatch.setattr("app.services.chat_service.shutil.which", lambda x: f"/usr/bin/{x}")
    svc = ChatService(db_session)
    assert svc._resolve_cli_path() == "/usr/bin/claude"


# ============== 流式解析 ==============

@pytest.mark.unit
def test_extract_text_delta_handles_stream_event():
    svc = ChatService.__new__(ChatService)  # 绕过 __init__（不需 db）
    pieces = svc._extract_text_delta(STREAM_EVENT_TEXT_DELTA)
    assert pieces == ["你好"]

    # 非文本事件应返回空
    assert svc._extract_text_delta(STREAM_EVENT_TOOL_USE) == []

    # 顶层 assistant 事件（兜底）
    pieces = svc._extract_text_delta({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "完整块"}]},
    })
    assert pieces == ["完整块"]


@pytest.mark.unit
def test_extract_text_delta_returns_empty_for_unknown_types():
    svc = ChatService.__new__(ChatService)
    assert svc._extract_text_delta({"type": "system"}) == []
    assert svc._extract_text_delta({"type": "result"}) == []
    assert svc._extract_text_delta({"type": "user", "message": {"content": []}}) == []


# ============== stream_chat 集成 ==============

@pytest.mark.unit
def test_stream_chat_persists_user_message_first(
    db_session, patch_create_subprocess, chat_test_user
):
    """stream_chat 应先把 user 消息入库，再调 CLI。"""
    patch_create_subprocess["stdout_lines"] = [
        STREAM_EVENT_TEXT_DELTA,
        STREAM_EVENT_ANOTHER,
        STREAM_EVENT_RESULT,
    ]

    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)

    pieces = []
    async def collect():
        async for p in svc.stream_chat(
            session_id=session.id, user_id=chat_test_user.id, new_user_message="hi"
        ):
            pieces.append(p)
    _run_async(collect())

    # user 消息应已入库
    msgs = db_session.execute(
        select(ChatMessage).where(ChatMessage.session_id == session.id)
    ).scalars().all()
    assert len(msgs) == 1
    assert msgs[0].role == "user"
    assert msgs[0].content == "hi"

    # 流累积应拼成 "你好，我是 Art Bot"
    assert "".join(pieces) == "你好，我是 Art Bot"

    # 验证传给子进程的参数
    cmd = patch_create_subprocess["cmd"]
    assert "-p" in cmd
    assert "hi" in cmd
    assert "--session-id" in cmd
    # 工作目录
    assert patch_create_subprocess["kwargs"]["cwd"]


@pytest.mark.unit
def test_stream_chat_uses_db_session_id_for_cli(
    db_session, patch_create_subprocess, chat_test_user
):
    """CLI 的 --session-id 必须等于 DB 的 ChatSession.id。"""
    patch_create_subprocess["stdout_lines"] = [STREAM_EVENT_RESULT]
    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)

    async def collect():
        async for _ in svc.stream_chat(
            session_id=session.id, user_id=chat_test_user.id, new_user_message="x"
        ):
            pass
    _run_async(collect())

    cmd = patch_create_subprocess["cmd"]
    assert cmd[cmd.index("--session-id") + 1] == str(session.id)


@pytest.mark.unit
def test_stream_chat_raises_claude_cli_error_on_nonzero_exit(
    db_session, monkeypatch, fake_proc_factory, chat_test_user
):
    """CLI 退出码非 0 应抛 ClaudeCLIError。"""
    async def fake_exec(*args, **kwargs):
        return fake_proc_factory(
            stdout_dicts=[],
            stderr=b"some cli error",
            returncode=1,
        )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)

    async def collect():
        async for _ in svc.stream_chat(
            session_id=session.id, user_id=chat_test_user.id, new_user_message="x"
        ):
            pass
    with pytest.raises(ClaudeCLIError, match="CLI 异常退出"):
        _run_async(collect())


@pytest.mark.unit
def test_stream_chat_terminates_subprocess_on_cancel(
    db_session, monkeypatch, chat_test_user
):
    """客户端断开（asyncio.CancelledError）应触发 proc.terminate()。"""
    proc_ref = {"terminate_called": 0, "kill_called": 0}

    class TrackedFakeProcess(FakeProcess):
        def __init__(self):
            super().__init__(
                stdout_lines=[
                    b'{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}}}\n',
                    b'{"type":"result"}\n',
                ],
                returncode=0,
            )

        def terminate(self) -> None:
            proc_ref["terminate_called"] += 1
            super().terminate()

        def kill(self) -> None:
            proc_ref["kill_called"] += 1
            super().kill()

        async def wait(self) -> int:
            # 模拟僵死，让 wait_for 超时后走 kill
            await asyncio.sleep(10)
            return self._returncode

    proc = TrackedFakeProcess()

    async def fake_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)

    async def runner():
        gen = svc.stream_chat(
            session_id=session.id, user_id=chat_test_user.id, new_user_message="x"
        )
        # 拿到 first piece
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            return
        # 用 athrow 把 CancelledError 注入生成器（与 FastAPI 客户端断开同效）
        try:
            await gen.athrow(asyncio.CancelledError())
        except (asyncio.CancelledError, Exception):
            pass
        # 收尾关闭
        try:
            await gen.aclose()
        except Exception:
            pass
        # 给 cancel 处理路径一点时间
        await asyncio.sleep(0.1)

    _run_async(runner())

    # cancel 处理路径必须调过 terminate（kill 是兜底，可能不调）
    assert proc_ref["terminate_called"] >= 1, f"terminate 未被调用: {proc_ref}"


@pytest.mark.unit
def test_stream_chat_ignores_malformed_json_lines(
    db_session, monkeypatch, fake_proc_factory, chat_test_user
):
    """非 JSON 行应跳过，不影响主流程。"""
    async def fake_exec(*args, **kwargs):
        lines = [
            b"this is not json\n",
            json.dumps(STREAM_EVENT_TEXT_DELTA).encode() + b"\n",
            b"{broken\n",
            json.dumps(STREAM_EVENT_RESULT).encode() + b"\n",
        ]
        proc = FakeProcess(lines)
        return proc
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)

    pieces = []
    async def collect():
        async for p in svc.stream_chat(
            session_id=session.id, user_id=chat_test_user.id, new_user_message="x"
        ):
            pieces.append(p)
    _run_async(collect())

    assert "".join(pieces) == "你好"


# ============== finalize_assistant ==============

@pytest.mark.unit
def test_finalize_assistant_writes_message(db_session, chat_test_user):
    svc = ChatService(db_session)
    session = svc.create_session(user_id=chat_test_user.id)
    msg = _run_async(
        svc.finalize_assistant(
            session_id=session.id,
            content="完整回答",
            is_truncated=False,
        )
    )
    assert msg.role == "assistant"
    assert msg.content == "完整回答"
    assert msg.is_truncated is False
