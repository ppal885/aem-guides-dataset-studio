"""UIEvidenceCurrentnessResolver + versioned-knowledge helpers.

Decides whether a stored UI observation applies to a given query context. It
never uses 'newest screenshot always wins': a historical query prefers evidence
compatible with the historical release; an unknown target version yields explicit
uncertainty rather than a silent merge.
"""

# currentness tags stored on each UI record.
CURRENTNESS = (
    "CURRENT_UI_REFERENCE", "HISTORICAL_UI_REFERENCE", "SUPERSEDED_UI_REFERENCE",
    "VERSION_UNKNOWN", "ENVIRONMENT_SPECIFIC",
)

# resolver verdicts.
APPLICABLE_CURRENT = "APPLICABLE_CURRENT"
APPLICABLE_HISTORICAL = "APPLICABLE_HISTORICAL"
POSSIBLY_APPLICABLE = "POSSIBLY_APPLICABLE"
VERSION_MISMATCH = "VERSION_MISMATCH"
SUPERSEDED = "SUPERSEDED"
UNKNOWN = "UNKNOWN"


def resolve(*, target_product, target_version, intent, evidence):
    """Return one of the resolver verdicts.

    intent: 'current' or 'historical' (what the caller is asking about).
    evidence: a UI record's currentness metadata dict with keys
      {product, product_version, currentness, superseded_by}.
    """
    ev_product = (evidence.get("product") or "").upper()
    if target_product and ev_product and target_product.upper() != ev_product:
        return VERSION_MISMATCH

    currentness = evidence.get("currentness") or "VERSION_UNKNOWN"
    if evidence.get("superseded_by") or currentness == "SUPERSEDED_UI_REFERENCE":
        # A superseded record is only offered when the caller explicitly wants history.
        return SUPERSEDED if intent != "historical" else APPLICABLE_HISTORICAL

    ev_version = evidence.get("product_version") or "UNKNOWN"
    if ev_version == "UNKNOWN" or not target_version:
        # Cannot prove version compatibility -> explicit uncertainty, never a merge.
        return POSSIBLY_APPLICABLE if currentness != "VERSION_UNKNOWN" else UNKNOWN

    if intent == "historical":
        return APPLICABLE_HISTORICAL if _version_le(ev_version, target_version) else VERSION_MISMATCH

    # intent == current
    if ev_version == target_version:
        return APPLICABLE_CURRENT
    if _version_le(ev_version, target_version):
        return POSSIBLY_APPLICABLE  # older evidence may still hold; do not assert
    return VERSION_MISMATCH


def _version_parts(v):
    parts = []
    for token in str(v).replace("-", ".").split("."):
        parts.append(int(token) if token.isdigit() else 0)
    return parts


def _version_le(a, b):
    """a <= b by dotted numeric comparison (non-numeric tokens treated as 0)."""
    pa, pb = _version_parts(a), _version_parts(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return pa <= pb
