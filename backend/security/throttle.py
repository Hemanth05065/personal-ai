"""In-memory login throttling. One process, one user machine: no shared store needed."""

import math
import threading
import time
from collections import deque


class LoginThrottle:
    def __init__(self, max_failures: int, window_seconds: int, lockout_seconds: int):
        self.max_failures = max_failures
        self.window = window_seconds
        self.lockout = lockout_seconds
        self._failures: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, *keys: str) -> int:
        """Seconds the caller must wait, or 0 when a login attempt is allowed."""
        now = time.monotonic()
        with self._lock:
            waits = [self._locked_until.get(key, 0) - now for key in keys]
        longest = max(waits, default=0)
        return math.ceil(longest) if longest > 0 else 0

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in keys:
                attempts = self._failures.setdefault(key, deque())
                attempts.append(now)
                while attempts and attempts[0] < now - self.window:
                    attempts.popleft()
                if len(attempts) >= self.max_failures:
                    self._locked_until[key] = now + self.lockout
                    attempts.clear()

    def record_success(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)
                self._locked_until.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()


# 5 wrong passwords for one username within 15 minutes locks that username for
# 15 minutes. A wider per-address limit stops guessing across many usernames.
login_throttle = LoginThrottle(max_failures=5, window_seconds=900, lockout_seconds=900)
address_throttle = LoginThrottle(max_failures=20, window_seconds=900, lockout_seconds=900)
