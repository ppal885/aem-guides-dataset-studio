"""Static validation for Behave/feature text and step definitions (framework contract)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AutomationValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_SELENIUM_KEYS_RE = re.compile(
    r"(?:\bfrom\s+selenium\.webdriver\.common\.keys\s+import\s+Keys\b|\bKeys\.)",
    re.M,
)
_ACTION_CHAINS_RE = re.compile(
    r"\bActionChains\s*\(|from\s+selenium\.webdriver\.common\.action_chains\s+import\s+ActionChains\b",
    re.M,
)
_TIME_SLEEP_RE = re.compile(r"\btime\.sleep\s*\(|\basyncio\.sleep\s*\(", re.M)
# Raw Selenium wait drivers (framework uses Element.should_wait_till / PollerCondition).
_WEBDRIVER_WAIT_RE = re.compile(
    r"\bWebDriverWait\s*\(|\bimplicitly_wait\s*\(|\bfrom\s+selenium\.webdriver\.support(?:\.ui)?\s+import\s+WebDriverWait\b",
    re.I | re.M,
)
_EXPECTED_CONDITIONS_RE = re.compile(
    r"\bexpected_conditions\b|\bfrom\s+selenium\.webdriver\.support\s+import\s+expected_conditions\b|\bec_expected_conditions\b|\bEC\.",
    re.I | re.M,
)
_RAW_DRIVER_FIND_RE = re.compile(
    r"\b(?:driver|context\.browser)\.find_element(?:s)?\s*\(|\w+\.find_elements?\s*\(\s*By\.",
    re.I | re.M,
)
_EXECUTE_SCRIPT_CLICK_RE = re.compile(
    r"execute_script\s*\(\s*['\"][^'\"]*\bclick\s*\(",
    re.I | re.M,
)
_BY_SELENIUM_RE = re.compile(
    r"\bfrom\s+selenium\.webdriver\.common\.by\s+import\s+By\b|\bBy\.(?:XPATH|CSS(?:_SELECTOR)?|ID|NAME|TAG_NAME|CLASS_NAME|LINK_TEXT|PARTIAL_LINK_TEXT)\b",
    re.I | re.M,
)

# move_to_element(override=True) discouraged — allowed only with same-line hover/transient justification.
_MOVE_TO_ELEMENT_OVERRIDE_OK_COMMENT_RE = re.compile(
    r"move_to_element\s*\([\s\S]*?override\s*=\s*True[\s\S]*?\)\s*#.*\b("
    r"hover|transient|spectrum|menu|kebab|ellipsis|overflow|popover|tooltip"
    r")\b",
    re.I | re.M,
)

# click(override=True) only for documented ellipsis/overflow/truncation UI triggers (inline comment on same line).
_CLICK_OVERRIDE_OK_COMMENT_RE = re.compile(
    r"click\s*\(\s*override\s*=\s*True\s*\)\s*#.*\b("
    r"ellipsis|overflow|truncat|kebab|menu\s*trigger|transient|spectrum\s*menu|popover"
    r")\b",
    re.I | re.M,
)

# Raw XPath / selector literals belong in Page Objects or the XPath library, not step definitions.
_RAW_STEP_XPATH_LITERAL = re.compile(
    r"By\.XPATH\s*,\s*(?:rf|fr|r|f)?['\"]([^'\"]+)['\"]",
    re.I | re.M,
)
_RAW_STEP_CSS_LITERAL = re.compile(
    r"By\.CSS(?:_SELECTOR)?\s*,\s*(?:rf|fr|r|f)?['\"]([^'\"]+)['\"]",
    re.I | re.M,
)
_RAW_FIND_BY_XPATH_RE = re.compile(
    r"\.find_element(?:s)?_by_xpath\s*\(\s*r?['\"]([^'\"]+)['\"]",
    re.I | re.M,
)

# Page Object classes must not be invented inside Behave step files.
_INVENTED_PAGE_CLASS_IN_STEPS = re.compile(
    r"^\s*class\s+\w*[Pp]age\w*\s*(?:\([^)]*\))?\s*:",
    re.M,
)

# Generic / stub dispatcher — must be grounded in real Page Object APIs.
_PAGE_OBJECT_CALL_STUB_RE = re.compile(r"\bpage_object_call\s*\(", re.M)

# Fragile: heavy reliance on positional node indexes (not attribute-based).
_FRAGILE_XPATH_POSITION_RE = re.compile(
    r"(?://|\(/)[a-z*][a-z0-9.:*_-]*\[\s*\d+\s*\]|"
    r"ancestor::[a-z*][a-z0-9.:*_-]*\[\s*\d+\s*\]|"
    r"following-sibling::[a-z*][a-z0-9.:*_-]*\[\s*\d+\s*\]|"
    r"preceding-sibling::[a-z*][a-z0-9.:*_-]*\[\s*\d+\s*\]",
    re.I,
)

_DESTRUCTIVE_STEP_HINT = re.compile(
    r"\b(confirm|accept_alert|dismiss\(|switch_to\.alert|\.delete\(|remove\(|destructive|"
    r"press_confirm|ok_button|btn[_-]?ok|danger_zone|destructive_action)\b",
    re.I,
)

_GIVEN_DECORATOR_RE = re.compile(r"^\s*@given\s*\(", re.I)
_WHEN_THEN_DECORATOR_RE = re.compile(r"^\s*@(when|then|step)\s*\(", re.I)
_GIVEN_ASSERT_OK_COMMENT_RE = re.compile(
    r"#\s*(destructive[- ]action[- ]?precondition|precondition:\s*destructive)\b",
    re.I,
)


def _lines(text: str) -> list[str]:
    return (text or "").splitlines()


def _fragile_xpath_fragment(fragment: str) -> bool:
    f = (fragment or "").strip()
    return bool(f and _FRAGILE_XPATH_POSITION_RE.search(f))


def _collect_xpath_literals_for_fragile_scan(*texts: str) -> list[str]:
    out: list[str] = []
    for raw in texts:
        if not (raw or "").strip():
            continue
        for rx in (_RAW_STEP_XPATH_LITERAL, _RAW_FIND_BY_XPATH_RE):
            for m in rx.finditer(raw):
                g1 = (m.group(1) or "").strip()
                if g1:
                    out.append(g1)
        for m in re.finditer(r"['\"]((?://|\(\s*//)[^'\"]{2,500})['\"]", raw):
            out.append(m.group(1).strip())
    return out


def _errors_silent_is_visible_before_destructive(step_defs_text: str) -> list[str]:
    """Block .is_visible() used as a soft guard with no assert before a destructive interaction."""
    lines = _lines(step_defs_text)
    errs: list[str] = []
    for i, line in enumerate(lines):
        if ".is_visible()" not in line:
            continue
        if "assert" in line.lower():
            continue
        window_end = min(len(lines), i + 35)
        segment = lines[i:window_end]
        destructive_idx: int | None = None
        for j, seg_line in enumerate(segment[1:], start=1):
            if "assert" in seg_line.lower() and re.search(r"\bassert\b", seg_line):
                break
            if (
                _DESTRUCTIVE_STEP_HINT.search(seg_line)
                or (
                     "click" in seg_line.lower()
                     and ("confirm" in seg_line.lower() or "delete" in seg_line.lower() or "remove" in seg_line.lower())
                )
            ) and (
                "click" in seg_line.lower() or "send_keys" in seg_line.lower() or "perform" in seg_line.lower()
            ):
                destructive_idx = j
                break
        if destructive_idx is not None:
            middle = segment[1:destructive_idx]
            if not any(re.search(r"\bassert\b", ml.lower()) for ml in middle):
                errs.append(
                    "Silent .is_visible() before a destructive/confirm interaction is blocked; "
                    f"add an explicit assert precondition (destructive action) before line: {segment[destructive_idx].strip()[:200]}"
                )
    return errs


def _errors_assert_in_given_without_precondition(step_defs_text: str) -> list[str]:
    """
    assert in @given blocks is allowed only as a tight destructive-action precondition
    (documented inline or previous-line comment).
    """
    lines = _lines(step_defs_text)
    errs: list[str] = []
    current_decorator: str | None = None
    for i, line in enumerate(lines):
        if _GIVEN_DECORATOR_RE.match(line):
            current_decorator = "given"
            continue
        if _WHEN_THEN_DECORATOR_RE.match(line):
            current_decorator = None
            continue
        if current_decorator != "given":
            continue
        if not re.search(r"\bassert\b", line):
            continue
        check = line
        if i > 0:
            check = lines[i - 1] + "\n" + line
        if not _GIVEN_ASSERT_OK_COMMENT_RE.match(check) and not _GIVEN_ASSERT_OK_COMMENT_RE.search(check):
            errs.append(
                "assert inside a @given step is allowed only for a documented destructive-action precondition "
                f"(use comment: # destructive-action precondition on this or the previous line): {line.strip()[:200]}"
            )
    return errs


def validate_automation_artifacts(
    *,
    feature_text: str = "",
    step_defs_text: str = "",
    page_object_text: str = "",
    jira_summary: str = "",
    jira_description: str = "",
    jira_raw: str = "",
    repro_steps: str = "",
    expected_behavior: str = "",
    acceptance_criteria: str = "",
    ui_snapshots: list[dict[str, Any]] | None = None,
) -> AutomationValidationResult:
    """
    Validate concatenated automation source for hard contract violations.
    Callers should pass whichever parts exist (feature, steps, page object snippets).
    Optional Jira/expected fields enable full Then-to-Jira traceability checks.
    """
    from app.services.qa_studio_assertion_traceability import (
        list_generic_then_violations,
        merge_user_and_jira_fields,
        traceability_errors_for_feature_and_fields,
    )

    errors: list[str] = []
    warnings: list[str] = []
    blob = "\n\n".join(
        t for t in (feature_text, step_defs_text, page_object_text) if (t or "").strip()
    )

    if _SELENIUM_KEYS_RE.search(blob):
        errors.append("Direct Selenium Keys usage is not allowed; use framework keyboard helpers.")
    if _ACTION_CHAINS_RE.search(blob):
        errors.append("ActionChains is not allowed; use framework interaction helpers.")
    if _TIME_SLEEP_RE.search(blob):
        errors.append("Hard time.sleep / asyncio.sleep calls are blocked; use framework waits/timeouts.")
    if _WEBDRIVER_WAIT_RE.search(blob):
        errors.append("WebDriverWait / implicitly_wait is blocked; use framework Element wait helpers.")
    if _EXPECTED_CONDITIONS_RE.search(blob):
        errors.append("expected_conditions / EC is blocked; use framework wait conditions (e.g. should_wait_till).")
    if _RAW_DRIVER_FIND_RE.search(blob):
        errors.append("Raw driver.find_element(s)(By...) is blocked; use Page Object / Element wrappers.")
    if _EXECUTE_SCRIPT_CLICK_RE.search(blob):
        errors.append("execute_script(...click...) is blocked; use framework click/move_to_element.")
    if _BY_SELENIUM_RE.search(blob):
        errors.append("Raw Selenium By imports/usages are blocked; use framework Element/constants patterns.")
    for m in re.finditer(r"\bmove_to_element\s*\([\s\S]*?\boverride\s*=\s*True[\s\S]*?\)", blob, re.I | re.M):
        line_start = blob.rfind("\n", 0, m.start()) + 1
        ne = blob.find("\n", m.end())
        line = blob[line_start : ne] if ne != -1 else blob[line_start:]
        if not _MOVE_TO_ELEMENT_OVERRIDE_OK_COMMENT_RE.search(line):
            errors.append(
                "move_to_element(override=True) is allowed only with an inline comment documenting hover/transient/Spectrum menu "
                "justification (or omit override and rely on framework retry + fresh relocate)."
            )
            break

    for m in re.finditer(r"click\s*\(\s*override\s*=\s*True\s*\)", blob, re.I | re.M):
        line_start = blob.rfind("\n", 0, m.start()) + 1
        ne = blob.find("\n", m.end())
        line = blob[line_start : ne] if ne != -1 else blob[line_start:]
        if not _CLICK_OVERRIDE_OK_COMMENT_RE.search(line):
            errors.append(
                "click(override=True) is allowed only with an inline comment documenting an ellipsis/overflow/truncation "
                "trigger (e.g. # ellipsis menu)."
            )

    for line in feature_text.splitlines():
        lstripped = line.strip()
        if not re.match(r"^(Given|When|Then)\b", lstripped, re.I):
            continue
        if re.search(r"['\"]\s*//", lstripped):
            errors.append(
                "Feature step may contain raw XPath literal (selectors belong in Page Objects): "
                + lstripped[:160]
            )
        if re.search(r"['\"]\s*(#[\w-]+|\.[a-z][\w-]*\s*\[)", lstripped, re.I):
            errors.append(
                "Feature step may contain raw CSS-like selector (selectors belong in Page Objects): "
                + lstripped[:160]
            )

    for m in _RAW_STEP_XPATH_LITERAL.finditer(step_defs_text):
        inner = (m.group(1) or "").strip()
        if inner.startswith("//") or inner.startswith("(//") or inner.startswith("(/"):
            errors.append(
                "Raw XPath literal in Behave step definitions (raw_selector_in_behave_step); "
                "move to Page Object or XPath library: "
                + inner[:160]
            )
    for m in _RAW_STEP_CSS_LITERAL.finditer(step_defs_text):
        inner = (m.group(1) or "").strip()
        if re.match(r"^[.#\[*]", inner) or re.search(r"\[[\w$]", inner):
            errors.append(
                "Raw CSS selector literal in Behave step definitions (raw_selector_in_behave_step); "
                "move to Page Object or XPath library: "
                + inner[:160]
            )

    for m in _RAW_FIND_BY_XPATH_RE.finditer(step_defs_text):
        inner = (m.group(1) or "").strip()
        if inner.startswith("//") or inner.startswith("(//") or inner.startswith("(/"):
            errors.append(
                "find_element*_by_xpath with raw XPath in Behave step definitions (raw_selector_in_behave_step); "
                "move to Page Object or XPath library: "
                + inner[:160]
            )

    if _INVENTED_PAGE_CLASS_IN_STEPS.search(step_defs_text):
        errors.append(
            "Invented Page Object classes are blocked inside Behave step definition files; "
            "define Page Objects in their own modules."
        )

    if _PAGE_OBJECT_CALL_STUB_RE.search(step_defs_text):
        errors.append(
            "ungrounded page_object_call(...) is blocked; call concrete Page Object methods with traceable locators."
        )

    seen_fr: set[str] = set()
    for frag in _collect_xpath_literals_for_fragile_scan(step_defs_text, page_object_text):
        if not _fragile_xpath_fragment(frag):
            continue
        key = frag[:220]
        if key in seen_fr:
            continue
        seen_fr.add(key)
        errors.append(
            "Fragile XPath (positional node index / brittle axis) is blocked — use stable attributes or "
            f"shared locator helpers: {frag[:180]}"
        )

    errors.extend(_errors_silent_is_visible_before_destructive(step_defs_text))
    errors.extend(_errors_assert_in_given_without_precondition(step_defs_text))

    has_jira_ctx = any(
        (x or "").strip()
        for x in (
            jira_summary,
            jira_description,
            jira_raw,
            expected_behavior,
            acceptance_criteria,
        )
    )
    if has_jira_ctx:
        fields = merge_user_and_jira_fields(
            jira_summary=jira_summary,
            jira_description=jira_description,
            jira_raw=jira_raw,
            repro_steps=repro_steps,
            expected_behavior=expected_behavior,
            acceptance_criteria=acceptance_criteria,
        )
        for err in traceability_errors_for_feature_and_fields(
            feature_text, fields, ui_snapshots=ui_snapshots
        ):
            errors.append(err)
    else:
        for line in feature_text.splitlines():
            lstripped = line.strip()
            if not re.match(r"^Then\b", lstripped, re.I):
                continue
            errors.extend(list_generic_then_violations(lstripped))

    return AutomationValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


def validate_feature_and_steps(feature_text: str, step_defs_text: str) -> AutomationValidationResult:
    return validate_automation_artifacts(feature_text=feature_text, step_defs_text=step_defs_text)
