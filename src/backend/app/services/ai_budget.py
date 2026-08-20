"""
AI 调用预算与限流（PRD §4.4）

进程内实现（单 worker 部署，MVP 级别）：
- QPS 上限 2（最小间隔 0.5s）
- 单日调用上限 500 次，超限直接走降级，次日自动恢复
- 熔断：5 分钟窗口内失败 ≥5 次熔断 10 分钟（防重试风暴）

不做跨进程共享（多 worker 需升级为 Redis，超 200 台规模再考虑）。
调用次数与 token 用量的持久化由各产物表的溯源字段承担（PRD X2），此处只做闸门。
"""
import logging
import threading
import time
from datetime import date

logger = logging.getLogger(__name__)

# 可通过环境变量/配置覆盖的默认值（MVP 硬编码，后续可接 soc_system_config）
QPS_LIMIT = 2
MIN_INTERVAL_SECONDS = 1.0 / QPS_LIMIT
DAILY_CAP = 500
CIRCUIT_FAILURE_THRESHOLD = 5      # 5 分钟窗口内失败次数
CIRCUIT_WINDOW_SECONDS = 300
CIRCUIT_OPEN_SECONDS = 600         # 熔断 10 分钟


class AIBudget:
    """进程级 AI 调用预算/限流/熔断（线程安全）"""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_call_ts = 0.0
        self._daily_date = None
        self._daily_count = 0
        self._failures = []  # [(ts, ...)] 最近失败时间戳
        self._circuit_opened_at = None
        self.total_allowed = 0
        self.total_rejected = 0

    # ---------- 主入口 ----------

    def allow(self) -> bool:
        """调用前检查；True=允许调用，False=预算/限流/熔断拒绝（走降级）"""
        now = time.time()
        with self._lock:
            # 1) 熔断检查
            if self._circuit_opened_at is not None:
                if now - self._circuit_opened_at < CIRCUIT_OPEN_SECONDS:
                    self.total_rejected += 1
                    return False
                # 熔断恢复
                logger.info("AI 熔断恢复，重新放行")
                self._circuit_opened_at = None
                self._failures.clear()
            # 2) QPS（最小间隔）
            if now - self._last_call_ts < MIN_INTERVAL_SECONDS:
                self.total_rejected += 1
                return False
            # 3) 单日上限
            today = date.today()
            if self._daily_date != today:
                self._daily_date = today
                self._daily_count = 0
            if self._daily_count >= DAILY_CAP:
                self.total_rejected += 1
                return False
            # 放行
            self._last_call_ts = now
            self._daily_count += 1
            self.total_allowed += 1
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failures.clear()

    def record_failure(self) -> None:
        """记录失败；窗口内失败达阈值则熔断"""
        now = time.time()
        with self._lock:
            self._failures.append(now)
            self._failures = [t for t in self._failures if now - t < CIRCUIT_WINDOW_SECONDS]
            if len(self._failures) >= CIRCUIT_FAILURE_THRESHOLD:
                self._circuit_opened_at = now
                logger.warning(
                    "AI 熔断触发：%d 次失败/%ds 窗口，熔断 %ds",
                    len(self._failures), CIRCUIT_WINDOW_SECONDS, CIRCUIT_OPEN_SECONDS,
                )

    def stats(self) -> dict:
        with self._lock:
            return {
                "daily_count": self._daily_count if self._daily_date == date.today() else 0,
                "daily_cap": DAILY_CAP,
                "qps_limit": QPS_LIMIT,
                "circuit_open": self._circuit_opened_at is not None
                and (time.time() - self._circuit_opened_at < CIRCUIT_OPEN_SECONDS),
                "total_allowed": self.total_allowed,
                "total_rejected": self.total_rejected,
            }


# 进程级单例
ai_budget = AIBudget()
