"""Structured error taxonomy for tool execution with category-based retry strategies.

Replaces flat keyword matching in _is_transient_error() with proper error
classification. Each category has a retry strategy with exponential backoff.

Feature flag: CHAT_ERROR_TAXONOMY (default True)
"""
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ToolErrorCategory(str, Enum):
    """Classification of tool execution errors."""

    TRANSIENT_NETWORK = "transient_network"
    """Network-level failures: timeout, connection reset, DNS. Retry fast."""

    RATE_LIMITED = "rate_limited"
    """Provider rate limiting (429, TPM/RPM exceeded). Retry with longer backoff."""

    SERVICE_UNAVAILABLE = "service_unavailable"
    """Service-side 5xx errors (502, 503, 504). Retry with moderate backoff."""

    AUTH_ERROR = "auth_error"
    """Authentication/authorization failures (401, 403, invalid key). Never retry."""

    VALIDATION_ERROR = "validation_error"
    """Input validation failures (bad params, schema mismatch). Never retry."""

    PERMANENT_ERROR = "permanent_error"
    """Non-recoverable errors (resource not found, logic error). Never retry."""


@dataclass(frozen=True)
class RetryStrategy:
    """Retry configuration for an error category."""

    should_retry: bool
    base_delay_sec: float
    max_delay_sec: float
    backoff_factor: float  # exponential multiplier

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number (1-indexed).

        Uses exponential backoff: base_delay * (backoff_factor ^ (attempt - 1))
        capped at max_delay.
        """
        if not self.should_retry or attempt < 1:
            return 0.0
        delay = self.base_delay_sec * (self.backoff_factor ** (attempt - 1))
        return min(delay, self.max_delay_sec)


# --- Strategy registry ---

_STRATEGIES: dict[ToolErrorCategory, RetryStrategy] = {
    ToolErrorCategory.TRANSIENT_NETWORK: RetryStrategy(
        should_retry=True,
        base_delay_sec=0.5,
        max_delay_sec=5.0,
        backoff_factor=2.0,
    ),
    ToolErrorCategory.RATE_LIMITED: RetryStrategy(
        should_retry=True,
        base_delay_sec=2.0,
        max_delay_sec=30.0,
        backoff_factor=3.0,
    ),
    ToolErrorCategory.SERVICE_UNAVAILABLE: RetryStrategy(
        should_retry=True,
        base_delay_sec=1.0,
        max_delay_sec=10.0,
        backoff_factor=2.0,
    ),
    ToolErrorCategory.AUTH_ERROR: RetryStrategy(
        should_retry=False,
        base_delay_sec=0.0,
        max_delay_sec=0.0,
        backoff_factor=1.0,
    ),
    ToolErrorCategory.VALIDATION_ERROR: RetryStrategy(
        should_retry=False,
        base_delay_sec=0.0,
        max_delay_sec=0.0,
        backoff_factor=1.0,
    ),
    ToolErrorCategory.PERMANENT_ERROR: RetryStrategy(
        should_retry=False,
        base_delay_sec=0.0,
        max_delay_sec=0.0,
        backoff_factor=1.0,
    ),
}


# --- Classification patterns ---

_RATE_LIMIT_PATTERNS = re.compile(
    r"rate.?limit|429|tokens?\s*per\s*(day|minute|hour)|tpm|rpm|tpd|quota.?exceed|too\s*many\s*requests",
    re.IGNORECASE,
)

_NETWORK_PATTERNS = re.compile(
    r"timeout|timed?\s*out|connection\s*(reset|refused|error|closed)|ECONNRESET|"
    r"ECONNREFUSED|ETIMEDOUT|network\s*error|socket\s*(error|hang\s*up)|"
    r"dns\s*(resolution|lookup)|broken\s*pipe|connection\s*aborted",
    re.IGNORECASE,
)

_SERVICE_UNAVAILABLE_PATTERNS = re.compile(
    r"\b50[234]\b|service\s*unavailable|bad\s*gateway|gateway\s*timeout|"
    r"temporarily\s*unavailable|overloaded|internal\s*server\s*error|"
    r"capacity|server\s*error",
    re.IGNORECASE,
)

_AUTH_PATTERNS = re.compile(
    r"\b40[13]\b|unauthorized|forbidden|invalid\s*(api\s*)?key|"
    r"authentication\s*(failed|required|error)|access\s*denied|"
    r"permission\s*denied|credentials",
    re.IGNORECASE,
)

_VALIDATION_PATTERNS = re.compile(
    r"\b400\b|bad\s*request|invalid\s*(param|input|argument|request)|"
    r"validation\s*(error|failed)|missing\s*required|schema\s*(error|mismatch)|"
    r"failed\s*to\s*call\s*a\s*function|failed_generation|"
    r"malformed|unprocessable",
    re.IGNORECASE,
)


def classify_error(error_msg: str) -> ToolErrorCategory:
    """Classify an error message into a category.

    Order matters: more specific patterns are checked first.
    """
    if not error_msg:
        return ToolErrorCategory.PERMANENT_ERROR

    msg = str(error_msg)

    # Check auth first (401/403 should not be retried)
    if _AUTH_PATTERNS.search(msg):
        return ToolErrorCategory.AUTH_ERROR

    # Rate limiting (429, quota exceeded)
    if _RATE_LIMIT_PATTERNS.search(msg):
        return ToolErrorCategory.RATE_LIMITED

    # Validation errors (400, bad request, schema issues)
    if _VALIDATION_PATTERNS.search(msg):
        return ToolErrorCategory.VALIDATION_ERROR

    # Network-level transient errors
    if _NETWORK_PATTERNS.search(msg):
        return ToolErrorCategory.TRANSIENT_NETWORK

    # Service unavailability (5xx)
    if _SERVICE_UNAVAILABLE_PATTERNS.search(msg):
        return ToolErrorCategory.SERVICE_UNAVAILABLE

    # Default: permanent
    return ToolErrorCategory.PERMANENT_ERROR


def get_retry_strategy(category: ToolErrorCategory) -> RetryStrategy:
    """Get the retry strategy for an error category."""
    return _STRATEGIES.get(category, _STRATEGIES[ToolErrorCategory.PERMANENT_ERROR])


def get_retry_delay(category: ToolErrorCategory, attempt: int) -> float:
    """Convenience: get delay for a category and attempt number."""
    return get_retry_strategy(category).get_delay(attempt)


def is_retryable(error_msg: str) -> bool:
    """Backward-compatible wrapper: returns True if the error is retryable.

    Drop-in replacement for the old _is_transient_error() keyword matcher.
    """
    category = classify_error(error_msg)
    return get_retry_strategy(category).should_retry
