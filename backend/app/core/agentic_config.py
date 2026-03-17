"""
Central configuration for agentic pipeline behavior.

All thresholds and limits are configurable via environment variables
to support different environments (dev, staging, production) and A/B testing.
"""
import os
from dataclasses import dataclass, field


def _int_env(name: str, default: int, min_val: int | None = None, max_val: int | None = None) -> int:
    """Read int from env with optional bounds."""
    try:
        val = int(os.getenv(name, str(default)))
        if min_val is not None and val < min_val:
            return min_val
        if max_val is not None and val > max_val:
            return max_val
        return val
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    """Read float from env."""
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    """Read bool from env (true/1/yes = True)."""
    val = os.getenv(name, str(default)).lower().strip()
    return val in ("true", "1", "yes", "on")


@dataclass(frozen=True)
class AgenticConfig:
    """Immutable config for agentic pipeline. Read from env at import."""

    # Retry limits
    max_validation_retries: int = field(default_factory=lambda: _int_env("AI_VALIDATION_RETRIES", 2, 0, 5))
    max_execution_retries: int = field(default_factory=lambda: _int_env("AI_EXECUTION_RETRIES", 1, 0, 5))

    # Scenario and candidate limits
    max_scenarios_per_run: int = field(default_factory=lambda: _int_env("AI_MAX_SCENARIOS", 5, 1, 20))
    recipe_candidates_k: int = field(default_factory=lambda: _int_env("AI_RECIPE_CANDIDATES_K", 12, 2, 20))
    recipe_candidates_k_per_retry: int = field(default_factory=lambda: _int_env("AI_RECIPE_CANDIDATES_K_PER_RETRY", 2, 0, 10))

    # Early stopping
    consecutive_failures_to_stop: int = field(default_factory=lambda: _int_env("AI_CONSECUTIVE_FAILURES_STOP", 2, 1, 10))

    # Evidence pack
    similar_issues_k: int = field(default_factory=lambda: _int_env("AI_SIMILAR_ISSUES_K", 5, 0, 20))
    attachment_max_files: int = field(default_factory=lambda: _int_env("AI_ATTACHMENT_MAX_FILES", 5, 1, 20))

    # Index fallback (Jira)
    index_min_issues: int = field(default_factory=lambda: _int_env("AI_INDEX_MIN_ISSUES", 200, 0, 1000))
    index_fallback_limit: int = field(default_factory=lambda: _int_env("AI_INDEX_FALLBACK_LIMIT", 500, 100, 2000))

    # LLM
    llm_timeout_seconds: float = field(default_factory=lambda: _float_env("AI_LLM_TIMEOUT_SECONDS", 120.0))
    use_llm_retrieval: bool = field(default_factory=lambda: _bool_env("AI_USE_LLM_RETRIEVAL", False))
    prompt_overrides_enabled: bool = field(default_factory=lambda: _bool_env("AI_PROMPT_OVERRIDES_ENABLED", True))

    # Deterministic pipeline (mechanism classification + recipe routing)
    use_deterministic_pipeline: bool = field(default_factory=lambda: _bool_env("AI_USE_DETERMINISTIC_PIPELINE", True))

    # Confidence threshold (0 = disabled; when > 0, log warning if avg mechanism+pattern confidence below threshold)
    min_confidence_threshold: float = field(default_factory=lambda: _float_env("AI_MIN_CONFIDENCE_THRESHOLD", 0.0))

    # Mechanism classifier: prior weight (0–1). Higher = more trust in keyword priors vs LLM.
    # When priors have strong signal (max >= 0.6), effective weight is boosted.
    mechanism_prior_weight: float = field(default_factory=lambda: _float_env("AI_MECHANISM_PRIOR_WEIGHT", 0.5))

    def recipe_k_for_validation_retry(self, validation_retries: int) -> int:
        """Candidate count increases with validation retries to broaden search."""
        return self.recipe_candidates_k + self.recipe_candidates_k_per_retry * validation_retries


# Singleton - read once at import
_base_config = AgenticConfig()


class _MutableAgenticConfig:
    """Wrapper that allows runtime overrides over the base config."""

    def __init__(self) -> None:
        self._overrides: dict[str, int | float] = {}

    def __getattr__(self, name: str) -> int | float:
        if name in self._overrides:
            return self._overrides[name]
        return getattr(_base_config, name)

    def set_override(self, key: str, value: int | float) -> None:
        if hasattr(_base_config, key):
            self._overrides[key] = value

    def clear_overrides(self) -> None:
        self._overrides.clear()

    def get_overrides(self) -> dict[str, int | float]:
        return dict(self._overrides)

    def recipe_k_for_validation_retry(self, validation_retries: int) -> int:
        return self.recipe_candidates_k + self.recipe_candidates_k_per_retry * validation_retries


agentic_config = _MutableAgenticConfig()
