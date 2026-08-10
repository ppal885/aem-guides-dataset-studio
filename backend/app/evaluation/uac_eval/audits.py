"""
UAC quality audits: hallucination detection, scope expansion, and performance-test false positives.

Each audit takes the Jira issue text and the generated scenarios as input
and returns an AuditResult with a pass/fail flag, per-issue list, and a 0–100 score.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence


# ── shared helpers ────────────────────────────────────────────────────────────

def _tokens(text: str) -> set[str]:
    text = re.sub(r"[^a-z0-9_\-/\.]", " ", text.lower())
    return {w for w in text.split() if len(w) > 2}


# ── result type ───────────────────────────────────────────────────────────────

@dataclass
class AuditResult:
    audit_name: str
    passed: bool            # True = no issues found
    score: float            # 0–100; 100 = perfect, 0 = worst
    issues: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "audit": self.audit_name,
            "passed": self.passed,
            "score": round(self.score, 1),
            "issue_count": len(self.issues),
            "issues": self.issues[:10],
            **{k: v for k, v in self.details.items()},
        }


# ── 1. Hallucination detection ────────────────────────────────────────────────

# Patterns that suggest a generated scenario is referring to something specific
_ENTITY_PATTERNS: list[re.Pattern] = [
    re.compile(r'\b(DXML|GUIDES)-\d+\b'),                # Jira key reference
    re.compile(r'\b[A-Z][a-zA-Z]{3,}(?:Service|Handler|Servlet|Manager|Controller|Helper|Impl)\b'),  # Java class names
    re.compile(r'\b(?:get|set|is|has|build|create|update|delete)[A-Z][a-zA-Z]+\b'),  # method names
    re.compile(r'/(?:content|apps|etc|var)/[a-zA-Z_/\-\.]+'),  # JCR paths
    re.compile(r'\b\d{4,}\b'),                            # large numbers (version IDs, line numbers)
]

_GENERIC_HALLUCINATION_PHRASES = {
    "rest api", "graphql", "microservice", "kubernetes", "docker", "cloud deployment",
    "machine learning", "artificial intelligence", "batch processing", "message queue",
    "elasticsearch", "apache kafka", "redis cache",
}


def audit_hallucination(
    jira_summary: str,
    jira_description: str,
    generated_scenarios: Sequence[str],
) -> AuditResult:
    """Detect scenarios that reference entities absent from the Jira issue text."""
    source_text = (jira_summary + " " + jira_description).lower()
    source_tokens = _tokens(source_text)
    issues: list[str] = []
    hallucinated_entities: list[str] = []

    for scenario in generated_scenarios:
        sc_lower = scenario.lower()

        # check for specific entity patterns
        for pat in _ENTITY_PATTERNS:
            for match in pat.findall(scenario):
                entity = match if isinstance(match, str) else match[0]
                if entity.lower() not in source_text:
                    issues.append(f"'{entity}' in scenario not found in Jira text")
                    hallucinated_entities.append(entity)

        # check for clearly off-domain phrases
        for phrase in _GENERIC_HALLUCINATION_PHRASES:
            if phrase in sc_lower and phrase not in source_text:
                issues.append(f"Possible hallucination: '{phrase}' not mentioned in Jira")

    score = max(0.0, 100.0 - len(issues) * 15)
    return AuditResult(
        audit_name="hallucination",
        passed=len(issues) == 0,
        score=score,
        issues=issues,
        details={"hallucinated_entities": list(set(hallucinated_entities))},
    )


# ── 2. Scope expansion detection ─────────────────────────────────────────────

# Output types mentioned in the Jira should be the only ones tested
_OUTPUT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "native_pdf": ["native pdf", "native-pdf", "pdf", "xsl-fo", "fop"],
    "html5": ["html5", "html 5", "responsive html", "ditaot"],
    "aem_sites": ["aem sites", "sites output", "site component"],
    "epub": ["epub", "e-pub"],
    "web_editor": ["web editor", "author view", "xml editor"],
    "review": ["review", "annotation", "reviewer"],
    "translation": ["translation", "locali", "language copy"],
    "baseline": ["baseline", "version label"],
    "search": ["search index", "full-text", "search result"],
}

_SCOPE_EXPANSION_MARKERS: list[str] = [
    "all output types", "all outputs", "every output format",
    "regression across", "regression test all", "end-to-end regression",
    "load test", "stress test", "penetration test", "security test", "soak test",
]


def _output_types_in_text(text: str) -> set[str]:
    text_l = text.lower()
    found: set[str] = set()
    for otype, kws in _OUTPUT_TYPE_KEYWORDS.items():
        if any(kw in text_l for kw in kws):
            found.add(otype)
    return found


def audit_scope_expansion(
    jira_summary: str,
    jira_description: str,
    generated_scenarios: Sequence[str],
) -> AuditResult:
    """Detect scenarios that test features or output types not mentioned in the Jira."""
    source_text = (jira_summary + " " + jira_description).lower()
    source_outputs = _output_types_in_text(source_text)
    issues: list[str] = []
    expanded_outputs: set[str] = set()

    for scenario in generated_scenarios:
        sc_lower = scenario.lower()

        # blanket expansion phrases
        for marker in _SCOPE_EXPANSION_MARKERS:
            if marker in sc_lower:
                issues.append(f"Blanket scope phrase: '{marker}'")

        # output types mentioned in generated but not in Jira
        gen_outputs = _output_types_in_text(scenario)
        new_outputs = gen_outputs - source_outputs
        for extra in new_outputs:
            issues.append(f"Output type '{extra}' tested but not mentioned in Jira")
            expanded_outputs.add(extra)

    score = max(0.0, 100.0 - len(issues) * 20)
    return AuditResult(
        audit_name="scope_expansion",
        passed=len(issues) == 0,
        score=score,
        issues=issues,
        details={
            "source_output_types": sorted(source_outputs),
            "expanded_output_types": sorted(expanded_outputs),
        },
    )


# ── 3. Performance-test false-positive detection ──────────────────────────────

_PERF_MARKERS: list[str] = [
    "load time", "response time", "throughput", "latency", "tps", "requests per second",
    "memory usage", "memory leak", "cpu usage", "jvm heap", "gc overhead",
    "concurrent users", "simultaneous users", "10k", "100k", "1 million",
    "sla", "service level agreement", "performance benchmark", "jmeter", "gatling",
]

_PERF_JIRA_SIGNALS: list[str] = [
    "performance", "slow", "timeout", "oom", "out of memory", "heap", "latency",
    "throughput", "benchmark", "jmeter", "load test", "stress test", "scalab",
]


def _is_performance_issue(summary: str, description: str) -> bool:
    combined = (summary + " " + description).lower()
    return any(sig in combined for sig in _PERF_JIRA_SIGNALS)


def audit_performance_false_positive(
    jira_summary: str,
    jira_description: str,
    generated_scenarios: Sequence[str],
) -> AuditResult:
    """Flag performance-test scenarios added for a non-performance Jira issue."""
    is_perf_issue = _is_performance_issue(jira_summary, jira_description)
    issues: list[str] = []
    flagged_scenarios: list[str] = []

    if is_perf_issue:
        # performance scenarios are expected — only flag them if they're vague
        for scenario in generated_scenarios:
            sc_l = scenario.lower()
            if any(m in sc_l for m in _PERF_MARKERS):
                if "verify" not in sc_l and "measure" not in sc_l:
                    issues.append(f"Performance scenario lacks measurable criterion: '{scenario[:80]}'")
    else:
        # non-perf issue — any performance scenario is a false positive
        for scenario in generated_scenarios:
            sc_l = scenario.lower()
            if any(m in sc_l for m in _PERF_MARKERS):
                issues.append(f"Performance test scenario on non-perf issue: '{scenario[:80]}'")
                flagged_scenarios.append(scenario)

    score = max(0.0, 100.0 - len(issues) * 25)
    return AuditResult(
        audit_name="performance_false_positive",
        passed=len(issues) == 0,
        score=score,
        issues=issues,
        details={
            "jira_is_performance_issue": is_perf_issue,
            "flagged_scenario_count": len(flagged_scenarios),
        },
    )


# ── run all audits ────────────────────────────────────────────────────────────

@dataclass
class TicketAuditReport:
    jira_key: str
    hallucination: AuditResult
    scope_expansion: AuditResult
    performance_false_positive: AuditResult

    @property
    def overall_score(self) -> float:
        return (
            self.hallucination.score * 0.40
            + self.scope_expansion.score * 0.35
            + self.performance_false_positive.score * 0.25
        )

    @property
    def passed(self) -> bool:
        return (
            self.hallucination.passed
            and self.scope_expansion.passed
            and self.performance_false_positive.passed
        )

    def to_dict(self) -> dict:
        return {
            "jira_key": self.jira_key,
            "overall_score": round(self.overall_score, 1),
            "passed": self.passed,
            "audits": {
                "hallucination": self.hallucination.to_dict(),
                "scope_expansion": self.scope_expansion.to_dict(),
                "performance_false_positive": self.performance_false_positive.to_dict(),
            },
        }


def run_all_audits(
    jira_key: str,
    jira_summary: str,
    jira_description: str,
    generated_scenarios: Sequence[str],
) -> TicketAuditReport:
    return TicketAuditReport(
        jira_key=jira_key,
        hallucination=audit_hallucination(jira_summary, jira_description, generated_scenarios),
        scope_expansion=audit_scope_expansion(jira_summary, jira_description, generated_scenarios),
        performance_false_positive=audit_performance_false_positive(
            jira_summary, jira_description, generated_scenarios
        ),
    )
