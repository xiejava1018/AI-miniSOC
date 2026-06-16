"""
Agent Process Manager — 进程池管理器

协议: JSON-RPC over stdio (详见 docs/plans/2026-06-15-pi-ai-integration-design.md §3.1)
进程管理: §3.2 — subprocess.Popen + asyncio StreamReader/Writer

POC 阶段说明:
- 所有需要真正 spawn 进程的方法 raise NotImplementedError
- 数据结构、类型注解、接口签名完整定义
- 可通过导入验证语法
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Dict, Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# Node 脚本路径: src/agent-runner/src/pi-agent-runner.js
NODE_SCRIPT = Path(__file__).parent.parent.parent.parent / "agent-runner" / "src" / "pi-agent-runner.js"


# ---------------------------------------------------------------------------
# 类型别名
# ---------------------------------------------------------------------------

class AgentProcessState(str, Enum):
    """进程生命周期状态"""
    IDLE = "idle"
    RUNNING = "running"
    DEAD = "dead"


# ---------------------------------------------------------------------------
# Pydantic 数据类 — 请求 / 响应 / 事件
# ---------------------------------------------------------------------------

class JSONRPCRequest(BaseModel):
    """JSON-RPC 请求 (FastAPI → Node)"""
    id: str = Field(..., description="请求唯一 ID")
    method: str = Field(..., description="方法名, 如 agent.prompt")
    params: Dict[str, Any] = Field(default_factory=dict, description="参数")


class JSONRPCResponse(BaseModel):
    """JSON-RPC 响应 (Node → FastAPI)"""
    id: str = Field(..., description="与请求 ID 对应")
    result: Optional[Dict[str, Any]] = Field(default=None, description="成功时返回")
    error: Optional[Dict[str, Any]] = Field(default=None, description="错误时返回")


class JSONRPCEvent(BaseModel):
    """JSON-RPC 事件流 (Node → FastAPI, id = 'evt')"""
    id: Literal["evt"] = "evt"
    method: Literal["agent.event"] = "agent.event"
    params: Dict[str, Any] = Field(..., description="事件载荷")


class AgentEvent(BaseModel):
    """统一事件结构 — 转发到 SSE"""
    session_id: str = Field(..., description="所属 session")
    type: str = Field(..., description="事件类型: text_delta / tool_execution_start / ...")
    delta: Optional[str] = Field(default=None, description="文本增量 (text_delta)")
    tool: Optional[str] = Field(default=None, description="工具名 (tool_*_start/end)")
    status: Optional[str] = Field(default=None, description="执行状态: start / end / ok / error")
    error: Optional[str] = Field(default=None, description="错误信息")
    ts: int = Field(default_factory=lambda: int(time.time() * 1000), description="毫秒时间戳")
    trace_id: Optional[str] = Field(default=None)
    span_id: Optional[str] = Field(default=None)

    class Config:
        # 允许 extra 字段, 因为 Pi 可能返回更多字段
        extra = "allow"


class CallResult(BaseModel):
    """call() 返回结果"""
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# AgentProcess — 单个 Node 子进程封装
# ---------------------------------------------------------------------------

class AgentProcess:
    """
    单个 Node 子进程封装 (Pi Agent Runner)

    持有一个 subprocess.Popen 进程, 通过 stdin/stdout 交换 JSON-RPC 消息。
    POC 阶段: 所有真正与进程通信的方法 raise NotImplementedError。
    """

    def __init__(
        self,
        session_id: str,
        role: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.session_id = session_id
        self.role = role
        self.state: AgentProcessState = AgentProcessState.IDLE
        self.last_heartbeat: float = time.time()
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._stdin_writer: Optional[asyncio.StreamWriter] = None
        self._stdout_reader: Optional[asyncio.StreamReader] = None
        self._stderr_reader: Optional[asyncio.StreamReader] = None
        # 请求 ID → Future[JSONRPCResponse]
        self._pending_requests: Dict[str, asyncio.Future[JSONRPCResponse]] = {}
        # asyncio.Lock 防止并发写 stdin
        self._write_lock = asyncio.Lock()
        # 事件队列
        self._events: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        # 配置: env, model, trace_id 等
        self._config: Dict[str, Any] = config or {}
        # stdout 监听任务
        self._listen_task: Optional[asyncio.Task[None]] = None

    # -----------------------------------------------------------------------
    # 生命周期
    # -----------------------------------------------------------------------

    async def _spawn(self) -> None:
        """
        用 asyncio.create_subprocess_exec 启动 Node 子进程。

        流程:
        1. 合并环境变量 + 用户配置 env
        2. 设置 PI_MODEL 环境变量
        3. spawn node --stdio ...
        4. 启动 stdout 监听协程
        """
        if self._proc is not None and self._proc.returncode is None:
            return  # 进程已启动

        env: Dict[str, str] = {**os.environ, **{str(k): str(v) for k, v in self._config.get("env", {}).items()}}
        env["PI_MODEL"] = self._config.get("model", "agnes/agnes-1.5-flash")  # Agnes AI as default
        # Pass Agnes API key to Node process
        if self._config.get("api_key"):
            env["AGNES_API_KEY"] = self._config["api_key"]
        elif os.getenv("AGNES_API_KEY"):
            env["AGNES_API_KEY"] = os.getenv("AGNES_API_KEY")
        if self._config.get("trace_id"):
            env["PI_TRACE_ID"] = self._config["trace_id"]

        self._proc = await asyncio.create_subprocess_exec(
            "node",
            str(NODE_SCRIPT),
            "--stdio",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            # 不使用 SIGPIPE, 让 Python 端处理管道关闭
            start_new_session=True,
        )
        self._stdin_writer = self._proc.stdin
        self._stdout_reader = self._proc.stdout
        self._stderr_reader = self._proc.stderr

        self.state = AgentProcessState.IDLE
        self.last_heartbeat = time.time()

        # 启动 stdout 监听协程
        self._listen_task = asyncio.create_task(self._listen_stdout())
        # 可选: 启动 stderr 日志 (后台打印到日志)
        if self._stderr_reader:
            asyncio.create_task(self._log_stderr())

    async def _log_stderr(self) -> None:
        """后台读取 stderr 并打印 (调试用)"""
        if self._stderr_reader is None:
            return
        try:
            while self._proc and self._proc.returncode is None:
                line = await self._stderr_reader.readline()
                if not line:
                    break
                # 简单打印到 stderr, 避免阻塞
                import sys
                sys.stderr.write(f"[PiAgent:{self.session_id}] {line.decode('utf-8', errors='replace')}")
                sys.stderr.flush()
        except Exception:
            pass

    async def _listen_stdout(self) -> None:
        """
        持续读 stdout, 分派给 pending requests 或 yield events。

        流程:
        1. 循环读 stdout 直到进程退出
        2. 解析 JSON 行
        3. id == 'evt' → 推入 _events 队列
        4. id in _pending_requests → 完成 future
        """
        while self._proc and self._proc.returncode is None:
            try:
                if self._stdout_reader is None:
                    break
                line = await self._stdout_reader.readline()
                if not line:
                    break

                msg: Dict[str, Any] = json.loads(line.decode("utf-8"))
                req_id = msg.get("id")

                if req_id == "evt":
                    # 事件: 解析并推入队列
                    event_data = msg.get("params", {})
                    # 添加 session_id 方便上层使用
                    event_data["session_id"] = self.session_id
                    await self._events.put(event_data)
                elif req_id in self._pending_requests:
                    # 响应: 完成 future
                    future = self._pending_requests.pop(req_id)
                    if not future.done():
                        future.set_result(JSONRPCResponse.model_validate(msg))
                    self.last_heartbeat = time.time()
                else:
                    # 未知消息, 忽略
                    pass
            except asyncio.CancelledError:
                break
            except json.JSONDecodeError:
                # 非 JSON 行, 忽略
                pass
            except Exception:
                # 其他异常, 继续循环
                pass

        # 进程已退出, 标记状态
        self.state = AgentProcessState.DEAD

        # 通知所有 pending futures 以错误结束
        for req_id, future in list(self._pending_requests.items()):
            if not future.done():
                exc = RuntimeError(f"Process {self.session_id} exited unexpectedly")
                future.set_exception(exc)
        self._pending_requests.clear()

    # -----------------------------------------------------------------------
    # RPC 调用
    # -----------------------------------------------------------------------

    async def call(self, method: str, params: dict, timeout: float = 60.0) -> dict:
        """
        发送 JSON-RPC 请求, 等待响应。

        流程:
        1. 生成 request_id, 创建 asyncio.Future
        2. 若进程未启动, 调用 _spawn
        3. 写入 stdin (加锁, 防并发写)
        4. await future until timeout
        5. 返回 result 或 raise

        Raises:
            asyncio.TimeoutError: 超时
            RuntimeError: 进程异常或 RPC error
        """
        # 确保进程已启动
        if self._proc is None or self._proc.returncode is not None:
            await self._spawn()

        req_id = f"req-{int(time.time() * 1000)}-{id(self)}"
        request = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}

        future: asyncio.Future[JSONRPCResponse] = asyncio.Future()
        self._pending_requests[req_id] = future

        self.state = AgentProcessState.RUNNING
        self.last_heartbeat = time.time()

        try:
            # 写入 stdin (加锁)
            async with self._write_lock:
                self._stdin_writer.write(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")
                await self._stdin_writer.drain()

            # 等待响应
            result = await asyncio.wait_for(future, timeout)

            if result.error:
                raise RuntimeError(f"RPC error: {result.error}")

            return result.result or {}
        except asyncio.TimeoutError:
            # 超时后移除 pending
            self._pending_requests.pop(req_id, None)
            raise asyncio.TimeoutError(f"RPC call {method} timed out after {timeout}s")
        finally:
            self.state = AgentProcessState.IDLE

    # -----------------------------------------------------------------------
    # 事件流
    # -----------------------------------------------------------------------

    async def stream_events(self) -> AsyncIterator[Dict[str, Any]]:
        """
        从 _events 队列 yield 事件。

        流程:
        1. 从 _events 队列读取事件
        2. yield 直到进程退出或超时
        3. timeout=1s 检查进程是否存活

        Yields:
            Dict[str, Any]: 事件载荷

        Raises:
            RuntimeError: 进程已退出
        """
        while True:
            try:
                event = await asyncio.wait_for(self._events.get(), timeout=1.0)
                yield event
            except asyncio.TimeoutError:
                # 检查进程是否还活着
                if self._proc is None or self._proc.returncode is not None:
                    # 进程已退出, 退出循环
                    break
                # 超时但进程存活, 继续等待
                continue

    # -----------------------------------------------------------------------
    # 生命周期
    # -----------------------------------------------------------------------

    async def kill(self, grace_period: float = 5.0) -> None:
        """
        优雅终止进程:
        1. SIGTERM → 等待 grace_period
        2. 若仍存活 → SIGKILL

        注意: subprocess.Process.terminate() 发送 SIGTERM,
              但在 start_new_session=True 时需要自己处理信号。
        """
        # 取消监听任务
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        if self._proc is None:
            return

        try:
            # SIGTERM
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), grace_period)
            except asyncio.TimeoutError:
                # SIGKILL
                self._proc.kill()
                await self._proc.wait()
        except ProcessLookupError:
            # 进程已不存在
            pass

        self._proc = None
        self._stdin_writer = None
        self._stdout_reader = None
        self._stderr_reader = None
        self.state = AgentProcessState.DEAD

        # 清空 pending requests
        for req_id, future in list(self._pending_requests.items()):
            if not future.done():
                future.set_exception(RuntimeError(f"Process {self.session_id} was killed"))
        self._pending_requests.clear()

        # 清空事件队列
        while not self._events.empty():
            try:
                self._events.get_nowait()
            except asyncio.QueueEmpty:
                break

    # -----------------------------------------------------------------------
    # 内部工具
    # -----------------------------------------------------------------------

    def _ensure_alive(self) -> None:
        """若进程已 DEAD, raise RuntimeError"""
        if self.state == AgentProcessState.DEAD:
            raise RuntimeError(f"Process {self.session_id} is dead")


# ---------------------------------------------------------------------------
# AgentProcessManager — 进程池管理器
# ---------------------------------------------------------------------------

class AgentProcessManager:
    """
    Agent 进程池管理器

    职责:
    - 进程生命周期 (spawn / reuse / evict / stats)
    - session → process 映射
    - idle_timeout / max_lifetime 驱逐策略
    - 并发保护 (asyncio.Lock)

    配置:
    - max_concurrent: 进程池上限 (默认 50)
    - idle_timeout:   空闲超时秒数 (默认 1800 = 30min)
    - max_lifetime:   最大存活秒数 (默认 7200 = 2h)
    """

    def __init__(
        self,
        max_concurrent: int = 50,
        idle_timeout: int = 1800,
        max_lifetime: int = 7200,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.idle_timeout = idle_timeout
        self.max_lifetime = max_lifetime
        self._processes: Dict[str, AgentProcess] = {}
        self._lock = asyncio.Lock()  # 并发保护

    # -----------------------------------------------------------------------
    # 核心 API
    # -----------------------------------------------------------------------

    async def get_or_create(
        self,
        session_id: str,
        role: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentProcess:
        """
        获取或创建进程。

        复用策略:
        - 已有 session_id → 复用, 更新 last_heartbeat
        - 无空闲进程且未达上限 → 启动新进程
        - 池满 → raise RuntimeError (或按策略 evict)

        Args:
            session_id: 会话 ID (UUID)
            role:       Agent 角色 (alert-triage / chat / report-writer / ...)
            config:     配置 dict (env, model, trace_id 等)

        Returns:
            AgentProcess 实例

        Raises:
            RuntimeError: 进程池已满
        """
        async with self._lock:
            # 复用已有进程
            if session_id in self._processes:
                proc = self._processes[session_id]
                proc.last_heartbeat = time.time()
                return proc

            # 检查池上限
            if len(self._processes) >= self.max_concurrent:
                raise RuntimeError(f"Agent pool full ({self.max_concurrent})")

            # 创建新进程
            proc = AgentProcess(session_id, role, config)
            await proc._spawn()
            self._processes[session_id] = proc
            return proc

    async def call(self, session_id: str, method: str, params: dict) -> dict:
        """
        对指定 session 调用 RPC。

        流程:
        1. 从 _processes 查找 process
        2. 若不存在 → get_or_create
        3. process.call(method, params)

        Returns:
            JSON-RPC result dict

        Raises:
            RuntimeError: session 不存在且无法创建
            asyncio.TimeoutError: RPC 超时
        """
        proc = self._processes.get(session_id)
        if not proc:
            # 自动创建, role 从 params 提取
            role = params.pop("role", "default") if "role" in params else "default"
            proc = await self.get_or_create(session_id, role, params)

        return await proc.call(method, params)

    async def stream_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        """
        流式监听 session 事件。

        Yields:
            Dict[str, Any]: 事件载荷 (转发到 SSE)

        Raises:
            KeyError: session 不存在
        """
        proc = self._processes.get(session_id)
        if not proc:
            raise KeyError(f"Session {session_id} not found")

        async for event in proc.stream_events():
            yield event

    async def evict(self, session_id: str) -> None:
        """
        驱逐指定 session 的进程。

        Args:
            session_id: 要驱逐的会话 ID
        """
        async with self._lock:
            proc = self._processes.pop(session_id, None)
            if proc:
                await proc.kill()

    # -----------------------------------------------------------------------
    # 统计 & 运维
    # -----------------------------------------------------------------------

    def get_stats(self) -> dict:
        """
        返回进程池统计信息。

        Returns:
            {
                "total": int,
                "by_state": {"idle": N, "running": N, "dead": N},
                "by_role":  {"alert-triage": N, "chat": N, ...},
            }
        """
        by_state: Dict[str, int] = {
            AgentProcessState.IDLE.value: 0,
            AgentProcessState.RUNNING.value: 0,
            AgentProcessState.DEAD.value: 0,
        }
        by_role: Dict[str, int] = {}

        for proc in self._processes.values():
            state_key = proc.state.value if isinstance(proc.state, AgentProcessState) else str(proc.state)
            by_state[state_key] = by_state.get(state_key, 0) + 1
            by_role[proc.role] = by_role.get(proc.role, 0) + 1

        return {
            "total": len(self._processes),
            "by_state": by_state,
            "by_role": by_role,
        }