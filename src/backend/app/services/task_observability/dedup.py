"""
通知去重：滑动窗口 + error fingerprint。

v0.4 §3.7：相同 (task_key, alert_type, error_fingerprint) 在 window_s 内只发一次。
Phase 1 用进程内 defaultdict；Phase 2 多 pod 时换 Redis SETNX TTL。
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List

logger = logging.getLogger(__name__)


class NotificationDeduplicator:
    def __init__(self, window_seconds: int = 300):
        self.window = window_seconds
        self._seen: Dict[str, List[float]] = defaultdict(list)
        self._lock = Lock()  # 短临界区，仅操作内存 list；可接受

    def _fingerprint(self, task_key: str, alert_type: str, error_text: str) -> str:
        fp_src = f"{task_key}|{alert_type}|{type(error_text).__name__}|{str(error_text)[:100]}"
        return hashlib.md5(fp_src.encode(), usedforsecurity=False).hexdigest()[:12]

    def should_send(self, task_key: str, alert_type: str, error_text: str) -> bool:
        key = self._fingerprint(task_key, alert_type, error_text or "")
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            seen = [t for t in self._seen[key] if t > cutoff]
            if seen:
                # 窗口内已发过
                self._seen[key] = seen
                return False
            seen.append(now)
            self._seen[key] = seen
            return True

    def cleanup(self) -> int:
        """清掉过期条目（看门狗周期性调）。返回清理的 key 数。"""
        now = time.time()
        cutoff = now - self.window
        removed = 0
        with self._lock:
            for k in list(self._seen.keys()):
                self._seen[k] = [t for t in self._seen[k] if t > cutoff]
                if not self._seen[k]:
                    del self._seen[k]
                    removed += 1
        return removed


notification_dedup = NotificationDeduplicator()
