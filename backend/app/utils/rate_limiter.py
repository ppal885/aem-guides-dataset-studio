"""Token bucket rate limiter for API calls."""
import asyncio
import os
import threading
import time
from typing import Optional


class TokenBucket:
    """Token bucket rate limiter. Blocks until a token is available."""

    def __init__(self, rpm: float, name: str = "default"):
        self.rpm = max(1.0, rpm)
        self.name = name
        self._tokens = self.rpm
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        refill_amount = elapsed * (self.rpm / 60.0)
        self._tokens = min(self.rpm, self._tokens + refill_amount)
        self._last_refill = now

    def acquire(self) -> None:
        """Block until a token is available, then consume one."""
        with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                sleep_time = (1.0 - self._tokens) * 60.0 / self.rpm
                self._tokens = 0.0
                self._last_refill = time.monotonic()
                time.sleep(min(sleep_time, 60.0))

    async def acquire_async(self) -> None:
        """Async: wait until a token is available, then consume one."""
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                sleep_time = (1.0 - self._tokens) * 60.0 / self.rpm
                self._tokens = 0.0
                self._last_refill = time.monotonic()
            await asyncio.sleep(min(sleep_time, 60.0))


def _get_rpm(env_var: str, default: int = 60) -> float:
    try:
        return float(os.getenv(env_var, str(default)))
    except (ValueError, TypeError):
        return float(default)


_jira_limiter: Optional[TokenBucket] = None
_llm_limiter: Optional[TokenBucket] = None
_limiter_lock = threading.Lock()


def get_jira_limiter() -> TokenBucket:
    """Get or create Jira API rate limiter."""
    global _jira_limiter
    with _limiter_lock:
        if _jira_limiter is None:
            rpm = _get_rpm("JIRA_RATE_LIMIT_RPM", 60)
            _jira_limiter = TokenBucket(rpm, "jira")
        return _jira_limiter


def get_llm_limiter() -> TokenBucket:
    """Get or create LLM API rate limiter."""
    global _llm_limiter
    with _limiter_lock:
        if _llm_limiter is None:
            rpm = _get_rpm("LLM_RATE_LIMIT_RPM", 60)
            _llm_limiter = TokenBucket(rpm, "llm")
        return _llm_limiter
