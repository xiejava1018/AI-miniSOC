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
import time
from enum import Enum
from typing import AsyncIterator, Dict, Any, Optional

from pydantic import BaseModel, Field


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
        # 以下参数在 POC 阶段由 Manager 持有, 进程本身暂不实例化
        _proc: Optional[Any] = None,  # subprocess.Popen
        _stdin_writer: Optional[asyncio.StreamWriter] = None,
        _stdout_reader: Optional[asyncio.StreamReader] = None,
    ) -> None:
        self.session_id = session_id
        self.role = role
        self.state: AgentProcessState = "idle"
        self.last_heartbeat: float = time.time()
        self._proc = _proc
        self._stdin_writer = _stdin_writer
        self._stdout_reader = _stdout_reader
        # 请求 ID → Future[JSONRPCResponse]
        self._pending_requests: Dict[str, asyncio.Future[JSONRPCResponse]] = {}
        # asyncio.Lock 防止并发写 stdin
        self._write_lock = asyncio.Lock()

    # -----------------------------------------------------------------------
    # RPC 调用
    # -----------------------------------------------------------------------

    async def call(self, method: str, params: dict, timeout: float = 60.0) -> dict:
        """
        发送 JSON-RPC 请求, 等待响应。

        流程:
        1. 生成 request_id, 创建 asyncio.Future
        2. 写入 stdin (加锁, 防并发写)
        3. await future until timeout
        4. 返回 result 或 raise

        Raises:
            NotImplementedError: POC 阶段不真正与进程通信
            asyncio.TimeoutError: 超时
        """
        raise NotImplementedError("POC 阶段: 未真正 spawn 进程")

    # -----------------------------------------------------------------------
    # 事件流
    # -----------------------------------------------------------------------

    async def stream_events(self) -> AsyncIterator[dict]:
        """
        监听 stdout 事件流, yeild AgentEvent。

        流程:
        1. 启动一个 asyncio.Task 持续读取 stdout
        2. 解析 JSON 行, 过滤 id == 'evt' 的消息
        3. yield AgentEvent 直到进程退出或取消

        Yields:
            AgentEvent: 解析后的事件对象

        Raises:
            NotImplementedError: POC 阶段未建立进程管道
        """
        raise NotImplementedError("POC 阶段: 未建立 stdout 监听管道")
        yield  # noqa: 声明 AsyncIterator 必须有 yield

    # -----------------------------------------------------------------------
    # 生命周期
    # -----------------------------------------------------------------------

    async def kill(self, grace_period: float = 5.0) -> None:
        """
        优雅终止进程:
        1. SIGTERM → 等待 grace_period
        2. 若仍存活 → SIGKILL

        Raises:
            NotImplementedError: POC 阶段无进程可杀
        """
        raise NotImplementedError("POC 阶段: 无进程可杀")

    # -----------------------------------------------------------------------
    # 内部工具
    # -----------------------------------------------------------------------

    def _ensure_alive(self) -> None:
        """若进程已 DEAD, raise RuntimeError"""
        if self.state == "dead":
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

    async def get_or_create(self, session_id: str, role: str) -> AgentProcess:
        """
        获取或创建进程。

        复用策略:
        - 已有 session_id → 复用, 更新 last_heartbeat
        - 无空闲进程且未达上限 → 启动新进程
        - 池满 → raise RuntimeError (或按策略 evict)

        Args:
            session_id: 会话 ID (UUID)
            role:       Agent 角色 (alert-triage / chat / report-writer / ...)

        Returns:
            AgentProcess 实例

        Raises:
            NotImplementedError: POC 阶段不真正 spawn 进程
            RuntimeError:       进程池已满
        """
        raise NotImplementedError("POC 阶段: 不真正创建进程")

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
            KeyError:            session 不存在且无法创建
            NotImplementedError: POC 阶段
        """
        raise NotImplementedError("POC 阶段: 不真正调用 RPC")

    async def stream_events(self, session_id: str) -> AsyncIterator[dict]:
        """
        流式监听 session 事件。

        Yields:
            AgentEvent 字典 (转发到 SSE)

        Raises:
            NotImplementedError: POC 阶段无事件流
        """
        raise NotImplementedError("POC 阶段: 无事件流")
        yield  # noqa

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
        by_state: Dict[str, int] = {"idle": 0, "running": 0, "dead": 0}
        by_role: Dict[str, int] = {}

        for proc in self._processes.values():
            by_state[proc.state] = by_state.get(proc.state, 0) + 1
            by_role[proc.role] = by_role.get(proc.role, 0) + 1

        return {
            "total": len(self._processes),
            "by_state": by_state,
            "by_role": by_role,
        }
