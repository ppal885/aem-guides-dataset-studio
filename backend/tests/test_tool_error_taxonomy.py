"""Tests for tool_error_taxonomy — error classification and retry strategies."""
import pytest
from app.services.tool_error_taxonomy import (
    ToolErrorCategory,
    classify_error,
    get_retry_delay,
    get_retry_strategy,
    is_retryable,
)


class TestClassifyError:
    def test_rate_limit_429(self):
        assert classify_error("Rate limit reached, 429") == ToolErrorCategory.RATE_LIMITED

    def test_rate_limit_tpm(self):
        assert classify_error("tokens per minute exceeded") == ToolErrorCategory.RATE_LIMITED

    def test_rate_limit_tpd(self):
        msg = "Rate limit reached for model `llama-3.3-70b-versatile` on tokens per day (TPD)"
        assert classify_error(msg) == ToolErrorCategory.RATE_LIMITED

    def test_network_timeout(self):
        assert classify_error("Connection timed out") == ToolErrorCategory.TRANSIENT_NETWORK

    def test_network_econnreset(self):
        assert classify_error("ECONNRESET: connection reset") == ToolErrorCategory.TRANSIENT_NETWORK

    def test_network_dns(self):
        assert classify_error("DNS resolution failed") == ToolErrorCategory.TRANSIENT_NETWORK

    def test_service_503(self):
        assert classify_error("503 Service Unavailable") == ToolErrorCategory.SERVICE_UNAVAILABLE

    def test_service_502(self):
        assert classify_error("502 Bad Gateway") == ToolErrorCategory.SERVICE_UNAVAILABLE

    def test_auth_401(self):
        assert classify_error("401 Unauthorized") == ToolErrorCategory.AUTH_ERROR

    def test_auth_invalid_key(self):
        assert classify_error("Invalid API key provided") == ToolErrorCategory.AUTH_ERROR

    def test_validation_400(self):
        assert classify_error("400 Bad Request: missing required field") == ToolErrorCategory.VALIDATION_ERROR

    def test_validation_failed_generation(self):
        assert classify_error("Failed to call a function. See 'failed_generation'") == ToolErrorCategory.VALIDATION_ERROR

    def test_permanent_unknown(self):
        assert classify_error("Something completely unknown went wrong") == ToolErrorCategory.PERMANENT_ERROR

    def test_empty_string(self):
        assert classify_error("") == ToolErrorCategory.PERMANENT_ERROR

    def test_auth_takes_precedence_over_network(self):
        # "401" contains no network keywords, but test mixed
        assert classify_error("401 connection unauthorized") == ToolErrorCategory.AUTH_ERROR


class TestRetryStrategy:
    def test_transient_network_retryable(self):
        strategy = get_retry_strategy(ToolErrorCategory.TRANSIENT_NETWORK)
        assert strategy.should_retry is True
        assert strategy.base_delay_sec == 0.5

    def test_rate_limited_retryable_with_longer_backoff(self):
        strategy = get_retry_strategy(ToolErrorCategory.RATE_LIMITED)
        assert strategy.should_retry is True
        assert strategy.base_delay_sec > 1.0

    def test_auth_not_retryable(self):
        strategy = get_retry_strategy(ToolErrorCategory.AUTH_ERROR)
        assert strategy.should_retry is False

    def test_validation_not_retryable(self):
        strategy = get_retry_strategy(ToolErrorCategory.VALIDATION_ERROR)
        assert strategy.should_retry is False

    def test_permanent_not_retryable(self):
        strategy = get_retry_strategy(ToolErrorCategory.PERMANENT_ERROR)
        assert strategy.should_retry is False


class TestRetryDelay:
    def test_exponential_backoff(self):
        d1 = get_retry_delay(ToolErrorCategory.TRANSIENT_NETWORK, 1)
        d2 = get_retry_delay(ToolErrorCategory.TRANSIENT_NETWORK, 2)
        d3 = get_retry_delay(ToolErrorCategory.TRANSIENT_NETWORK, 3)
        assert d2 > d1
        assert d3 > d2

    def test_capped_at_max(self):
        strategy = get_retry_strategy(ToolErrorCategory.TRANSIENT_NETWORK)
        d100 = get_retry_delay(ToolErrorCategory.TRANSIENT_NETWORK, 100)
        assert d100 == strategy.max_delay_sec

    def test_rate_limit_has_longer_delays(self):
        net_d1 = get_retry_delay(ToolErrorCategory.TRANSIENT_NETWORK, 1)
        rate_d1 = get_retry_delay(ToolErrorCategory.RATE_LIMITED, 1)
        assert rate_d1 > net_d1

    def test_no_retry_returns_zero(self):
        assert get_retry_delay(ToolErrorCategory.AUTH_ERROR, 1) == 0.0


class TestBackwardCompat:
    def test_is_retryable_timeout(self):
        assert is_retryable("Connection timed out") is True

    def test_is_retryable_rate_limit(self):
        assert is_retryable("429 rate limit exceeded") is True

    def test_is_retryable_auth(self):
        assert is_retryable("401 Unauthorized") is False

    def test_is_retryable_permanent(self):
        assert is_retryable("Resource not found") is False
