"""Shared, side-effect-free routing guards for DITA evidence retrieval.

These signals select sources to investigate, never expected product behavior.
Native PDF is not treated as the DITA-OT PDF2 renderer.
"""
import re


_OT_ENGINE = re.compile(r"\b(?:dita[-\s]?ot|(?:dita\s+)?open\s+toolkit|pdf\s*2)\b", re.I)
_SPEC_REQUEST = re.compile(
    r"\boasis\b|\bdita\s+(?:v?1\.[23]|spec(?:ification)?s?|standard|pdf)\b", re.I
)
_PROCESSING = re.compile(
    r"\b(?:pdf|html5?|publish(?:ing|ed)?|output|render(?:ing|ed)?|"
    r"preprocess(?:ing)?|transform(?:ation|ing)?)\b", re.I
)
_DITA_INPUT = re.compile(
    r"</?[A-Za-z][\w.:-]*(?:\s|/?>)|@[A-Za-z][\w.:-]*|"
    r"\b(?:dita|xml|xref|cross[-\s]?references?|conref|keyref|ditaval|"
    r"bookmap|ditamap|topicref|reltable)\b", re.I
)


def requires_dita_ot_documentation(question: str) -> bool:
    return bool(_OT_ENGINE.search(question or ""))


def requires_indexed_dita_evidence(question: str) -> bool:
    """Do not answer processing/versioned-spec questions from a registry alone."""
    text = question or ""
    return bool(
        _SPEC_REQUEST.search(text)
        or requires_dita_ot_documentation(text)
        or (_PROCESSING.search(text) and _DITA_INPUT.search(text))
    )


def dita_retrieval_receipt(grounding: dict) -> list[str]:
    """Small, non-sensitive receipt shared by local and HTTP MCP answer wrappers."""
    debug = grounding.get("retrieval_debug") or {}
    if not isinstance(debug, dict):
        return []
    lines = []
    spec = debug.get("dita_spec_retrieval") or {}
    if isinstance(spec, dict) and spec:
        executed = spec.get("indexed_query_executed")
        executed = "yes" if executed is True else "no" if executed is False else "unknown"
        modes = {"NONE", "CHROMA_HYBRID", "EMBEDDING_FALLBACK", "DB_LEXICAL_FALLBACK", "SEED_LEXICAL_FALLBACK"}
        mode = spec.get("mode")
        mode = mode if isinstance(mode, str) and mode in modes else "UNKNOWN"
        count = spec.get("result_count")
        count = str(count) if type(count) is int and count >= 0 else "unknown"
        lines.append(f"- DITA spec RAG: indexed query={executed}; retrieval={mode}; returned chunks={count}.")
    if grounding.get("source_domain") == "dita_ot":
        present = debug.get("official_evidence_in_pack")
        present = "yes" if present is True else "no" if present is False else "unknown"
        lines.append(f"- DITA-OT docs: official source retained in evidence={present}.")
    return lines
