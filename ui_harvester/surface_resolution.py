"""Lifecycle-aware UI surface identity and retrieval policy.

Capabilities are never identified by name alone. A capability belongs to a
concrete product surface and route. Lifecycle relationships are evidence-gated:
similar labels, routes, or UI placement cannot establish replacement.
"""

import hashlib
import json
from dataclasses import dataclass, field


CURRENT_UI = "CURRENT_UI"
LEGACY_UI = "LEGACY_UI"
VERSION_UNKNOWN = "VERSION_UNKNOWN"
ENVIRONMENT_SPECIFIC = "ENVIRONMENT_SPECIFIC"

HAS_CURRENT_SURFACE = "HAS_CURRENT_SURFACE"
HAS_LEGACY_SURFACE = "HAS_LEGACY_SURFACE"
SUPERSEDED_BY = "SUPERSEDED_BY"
REPLACED_BY = "REPLACED_BY"

CURRENT_TEST_PLAN = "CURRENT_TEST_PLAN"
HISTORICAL_JIRA = "HISTORICAL_JIRA"

_LIFECYCLE_CLASSES = {
    CURRENT_UI,
    LEGACY_UI,
    VERSION_UNKNOWN,
    ENVIRONMENT_SPECIFIC,
}
_LIFECYCLE_RELATIONS = {SUPERSEDED_BY, REPLACED_BY}
_RELATION_EVIDENCE_SOURCES = {"CODE", "DOCUMENTATION", "JIRA"}


def _stable_id(prefix, payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LifecycleEvidence:
    source_type: str
    source_ref: str
    assertion: str
    classification: str = ""
    relation: str = ""
    environment: str = ""
    product_version: str = ""
    evidence_id: str = field(init=False)

    def __post_init__(self):
        payload = {
            "source_type": self.source_type.upper(),
            "source_ref": self.source_ref,
            "assertion": self.assertion,
            "classification": self.classification,
            "relation": self.relation,
            "environment": self.environment,
            "product_version": self.product_version,
        }
        object.__setattr__(
            self,
            "evidence_id",
            _stable_id("lifecycle-evidence:", payload),
        )


@dataclass(frozen=True)
class SurfaceIdentity:
    capability: str
    surface: str
    route_identity: str
    lifecycle: str = VERSION_UNKNOWN
    environment: str = ""
    product_version: str = ""
    evidence_ids: tuple = ()
    surface_id: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(
            self,
            "surface_id",
            surface_identity_key(
                self.capability,
                self.surface,
                self.route_identity,
            ),
        )


@dataclass(frozen=True)
class SurfaceRelation:
    source_surface_id: str
    target_surface_id: str
    relation: str
    evidence_ids: tuple
    authority: str = "LIFECYCLE_EVIDENCE"
    relation_id: str = field(init=False)

    def __post_init__(self):
        payload = {
            "source": self.source_surface_id,
            "target": self.target_surface_id,
            "relation": self.relation,
            "evidence_ids": sorted(self.evidence_ids),
        }
        object.__setattr__(
            self,
            "relation_id",
            _stable_id("surface-relation:", payload),
        )


def surface_identity_key(capability, surface, route_identity):
    """Return a stable key that prevents same-name capabilities from merging."""
    payload = {
        "capability": (capability or "UNKNOWN").upper(),
        "surface": (surface or "UNKNOWN").upper(),
        "route_identity": (route_identity or "UNKNOWN").lower(),
    }
    return _stable_id("surface-capability:", payload)


def classify_route_hint(route_identity):
    """Classify only product routes with an explicit lifecycle hint."""
    route = (route_identity or "").lower()
    if route.startswith("/libs/fmdita/mapcollections"):
        return LEGACY_UI
    if route.startswith("/libs/fmdita/clientlibs/xmleditor/page.html"):
        return CURRENT_UI
    return VERSION_UNKNOWN


def classify_surface(evidence=()):
    """Resolve lifecycle from explicit evidence; conflicts remain unknown."""
    classifications = {
        item.classification
        for item in evidence
        if item.classification in _LIFECYCLE_CLASSES
        and item.classification != VERSION_UNKNOWN
    }
    if len(classifications) == 1:
        return next(iter(classifications))
    return VERSION_UNKNOWN


def make_surface_identity(
    capability,
    surface,
    route_identity,
    *,
    evidence=(),
    lifecycle="",
    environment="",
    product_version="",
):
    evidence = tuple(evidence)
    resolved = (
        lifecycle
        if lifecycle in _LIFECYCLE_CLASSES
        else classify_surface(evidence)
    )
    if not evidence and resolved == VERSION_UNKNOWN:
        resolved = classify_route_hint(route_identity)
    return SurfaceIdentity(
        capability=capability,
        surface=surface,
        route_identity=route_identity,
        lifecycle=resolved,
        environment=environment,
        product_version=product_version,
        evidence_ids=tuple(sorted(item.evidence_id for item in evidence)),
    )


def make_surface_relation(source, target, relation, *, evidence=()):
    """Create a replacement relation only with direct docs/code/Jira support."""
    if relation not in _LIFECYCLE_RELATIONS:
        raise ValueError("Unsupported lifecycle relation: " + str(relation))
    supporting = [
        item
        for item in evidence
        if item.source_type.upper() in _RELATION_EVIDENCE_SOURCES
        and item.relation == relation
        and item.assertion.strip()
    ]
    if not supporting:
        raise ValueError(
            f"{relation} requires explicit documentation, code, or Jira "
            "lifecycle evidence"
        )
    return SurfaceRelation(
        source_surface_id=source.surface_id,
        target_surface_id=target.surface_id,
        relation=relation,
        evidence_ids=tuple(sorted(item.evidence_id for item in supporting)),
    )


def _rank(surface, purpose, requested_route, environment):
    exact_route = bool(
        requested_route and surface.route_identity == requested_route
    )
    environment_match = bool(
        environment
        and surface.lifecycle == ENVIRONMENT_SPECIFIC
        and surface.environment == environment
    )
    if purpose == HISTORICAL_JIRA:
        order = {
            LEGACY_UI: 0,
            CURRENT_UI: 1,
            ENVIRONMENT_SPECIFIC: 2,
            VERSION_UNKNOWN: 3,
        }
    else:
        order = {
            CURRENT_UI: 0,
            ENVIRONMENT_SPECIFIC: 1,
            VERSION_UNKNOWN: 2,
            LEGACY_UI: 9,
        }
    return (
        0 if exact_route else 1,
        0 if environment_match else 1,
        order.get(surface.lifecycle, 8),
    )


def select_surfaces(
    surfaces,
    *,
    purpose=CURRENT_TEST_PLAN,
    requested_route="",
    environment="",
):
    """Return applicable surfaces in retrieval order.

    Current planning never falls back to a known legacy UI unless the caller
    explicitly requested that exact legacy route. Historical Jira analysis may
    prefer legacy surfaces because old placement is valid historical context.
    """
    candidates = list(surfaces)
    if purpose == CURRENT_TEST_PLAN and not requested_route:
        candidates = [
            item for item in candidates if item.lifecycle != LEGACY_UI
        ]
    elif purpose == CURRENT_TEST_PLAN and requested_route:
        candidates = [
            item
            for item in candidates
            if item.lifecycle != LEGACY_UI
            or item.route_identity == requested_route
        ]
    return sorted(
        candidates,
        key=lambda item: _rank(
            item,
            purpose,
            requested_route,
            environment,
        ),
    )


def is_current_product_contract(surface, *, environment=""):
    """Return whether a surface can establish the current UI contract."""
    if surface.lifecycle == CURRENT_UI:
        return True
    return bool(
        surface.lifecycle == ENVIRONMENT_SPECIFIC
        and environment
        and surface.environment == environment
    )
