"""Admin Jira CSV preview and asynchronous SQL/Chroma ingestion."""

from __future__ import annotations

import asyncio
import copy
import csv
import hashlib
import io
import json
import re
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.structured_logging import get_structured_logger
from app.db.jira_enrichment_models import JiraCsvImportRun, JiraEnrichedIssue, JiraIssueChunk
from app.db.jira_enrichment_repository import insert_jira_chunks, upsert_jira_issue
from app.db.session import SessionLocal
from app.services.embedding_service import embed_texts_batched, is_embedding_available
from app.services.jira_chunking_service import build_comments_digest
from app.services.jira_component_metadata_service import (
    CANONICAL_JIRA_COMPONENTS,
    COMPONENT_TEXT_CLASSIFIER_VERSION,
    canonical_component_name,
    canonical_component_names,
    component_filter_metadata,
    infer_component_names,
)
from app.services.jira_enrichment_service import enrich_jira
from app.services.jira_historical_uac_import_service import (
    COMPONENT_ASSIGNMENT_EVIDENCE_HEADER,
    COMPONENT_ASSIGNMENT_METHOD_HEADER,
    SOURCE_COMPONENTS_HEADER,
    SOURCE_FILE_HASH_HEADER,
)
from app.services.jira_qa_chunking_service import build_jira_qa_chunks
from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    add_documents,
    delete_documents,
    is_chroma_available,
    update_documents_metadata,
)

logger = get_structured_logger(__name__)

MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_CSV_ROWS = 10_000
IMPORTER_VERSION = "customer-intelligence-v14"
SUPPORTED_IMPORT_PROFILES = ("auto", "editor-new", "native-pdf", "customer-history")
NATIVE_PDF_PROFILE_MIN_RATIO = 0.75
CORE_REQUIRED_HEADERS = {"Summary", "Issue key", "Issue Type", "Status"}
BEHAVIORAL_EVIDENCE_HEADERS = {"Resolution", "Description", "Updated"}
REQUIRED_HEADERS = CORE_REQUIRED_HEADERS
_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_IMS_ORG_RE = re.compile(r"\b[A-Z0-9]{8,}@AdobeOrg\b", re.I)
_MENTION_RE = re.compile(r"\[~[^\]]+\]")
_SECRET_RE = re.compile(
    r"(?i)\b(client[_ -]?secret|access[_ -]?token|oauth[_ -]?token|api[_ -]?token|password)\b\s*[:=]\s*\S+"
)
_URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)[^\s/:@]+:[^\s/@]+@")
_STRONG_CREDENTIAL_PAIR_RE = re.compile(
    r"(?im)^\s*(?:[*_~]|[-+]\s*)?[A-Z0-9._-]{2,64}/(?=\S{8,}\s*$)"
    r"(?=\S*[A-Z])(?=\S*[a-z])(?=\S*\d)(?=\S*[^A-Z0-9])\S+\s*$"
)
_LINK_HEADER_RE = re.compile(r"issue link", re.I)
_RUN_TASKS: set[asyncio.Task[Any]] = set()
_CUSTOMER_ALIASES = {
    "3m": "3M",
    "aetna": "Aetna",
    "abs": "American Bureau of Shipping",
    "american express": "American Express",
    "american bureau of shipping": "American Bureau of Shipping",
    "amex": "American Express",
    "ariel cop": "Ariel Corporation",
    "ariel corp": "Ariel Corporation",
    "ariel corporation": "Ariel Corporation",
    "astrazeneca": "AstraZeneca",
    "avaya": "Avaya",
    "banner engineering": "Banner Engineering",
    "basco": "BASCO",
    "benq": "BenQ",
    "blackberry": "BlackBerry",
    "bretting": "Bretting",
    "broadcom": "Broadcom",
    "centene": "Centene",
    "citrix": "Citrix",
    "cisco": "Cisco",
    "cloud software group": "Cloud Software Group",
    "ciena": "Ciena",
    "ciena corporation": "Ciena",
    "cmr surgical": "CMR Surgical",
    "crown": "Crown Equipment",
    "crown equipment": "Crown Equipment",
    "dfs": "DFS",
    "deluxe": "Deluxe",
    "dow": "Dow",
    "dsv": "DSV",
    "eaton": "Eaton",
    "emerson": "Emerson",
    "emerson process management": "Emerson",
    "enbridge": "Enbridge",
    "erie": "Erie Insurance",
    "erie insurance": "Erie Insurance",
    "ey": "EY",
    "eycom": "EY",
    "faa": "FAA",
    "gm": "GM",
    "greenbytes": "GreenBytes",
    "gulfstream": "Gulfstream",
    "grundfos": "Grundfos",
    "haas equipment": "Haas Equipment",
    "haas automation": "Haas Automation",
    "hyundai": "Hyundai",
    "hunter douglas": "Hunter Douglas",
    "ibm dx platforms": "IBM",
    "lanl": "LANL",
    "lloyds": "Lloyds",
    "red hat": "Red Hat",
    "redhat": "Red Hat",
    "red_hat": "Red Hat",
    "ibm": "IBM",
    "international business machines": "IBM",
    "intel": "Intel",
    "informatica": "Informatica",
    "isuzu intec corp": "Isuzu Intec Corporation",
    "isuzu intec corporation": "Isuzu Intec Corporation",
    "swift": "Swift",
    "s.w.i.f.t": "Swift",
    "lexmark": "Lexmark",
    "topcon": "Topcon",
    "fidelity": "Fidelity",
    "jpmc": "JPMC",
    "jp morgan": "JPMC",
    "jpmorgan": "JPMC",
    "jpmorgan chase": "JPMC",
    "kone": "KONE",
    "kyndryl": "Kyndryl",
    "kogei intec corp": "Kogei Intec Corporation",
    "kogei intec corporation": "Kogei Intec Corporation",
    "kyocera": "Kyocera",
    "mayo clinic": "Mayo Clinic",
    "mayoclinic": "Mayo Clinic",
    "mayo foundation for medical education and research": "Mayo Clinic",
    "marriott": "Marriott",
    "micron": "Micron",
    "navico": "Navico",
    "nutanix": "Nutanix",
    "optum": "Optum",
    "pan": "PAN",
    "piaggio": "Piaggio",
    "qualcomm": "Qualcomm",
    "raymond corp": "Raymond Corporation",
    "raymond corporation": "Raymond Corporation",
    "rbs": "RBS",
    "thomson reuters": "Thomson Reuters",
    "thomsonreuters": "Thomson Reuters",
    "pwc": "PwC",
    "pricewaterhousecoopers": "PwC",
    "pricewaterhouse coopers": "PwC",
    "linkedin": "LinkedIn",
    "linked in": "LinkedIn",
    "sonova": "Sonova",
    "resmed": "ResMed",
    "ringcentral": "RingCentral",
    "rockwell automation": "Rockwell Automation",
    "samsung": "Samsung",
    "sandia": "Sandia",
    "signify": "Signify",
    "splunk": "Splunk",
    "stihl": "STIHL",
    "servicenow": "ServiceNow",
    "signify": "Signify",
    "sub zero": "Sub-Zero",
    "ttc": "TTC",
    "toyota": "Toyota",
    "txdot": "TxDOT",
    "demant": "Demant",
    "transunion": "TransUnion",
    "transunion, llc": "TransUnion",
    "translation.com": "Translation.com",
    "ubs": "UBS",
    "usmc": "USMC",
    "workday": "Workday",
    "zebra": "Zebra",
    "zebra technologies": "Zebra",
    "verizon": "Verizon",
    "volkswagen": "Volkswagen",
}
_SUPPORTED_CUSTOMERS = {
    "3M", "Aetna", "American Bureau of Shipping", "American Express",
    "Ariel Corporation", "AstraZeneca", "Avaya", "Banner Engineering", "BASCO",
    "BenQ", "BlackBerry", "Bretting", "Broadcom", "Centene", "Ciena", "Cisco",
    "Citrix", "Cloud Software Group", "CMR Surgical", "Crown Equipment", "Deluxe",
    "Demant", "DFS", "Dow", "DSV", "Eaton", "Emerson",
    "Enbridge", "Erie Insurance", "EY", "FAA", "Fidelity", "Grundfos", "Gulfstream",
    "GM", "GreenBytes", "Haas Automation", "Haas Equipment", "Hunter Douglas",
    "Hyundai", "IBM", "Informatica", "Intel", "Isuzu Intec Corporation", "JPMC",
    "Kogei Intec Corporation", "KONE", "Kyndryl", "Kyocera",
    "LANL", "Lexmark", "LinkedIn", "Lloyds", "Marriott", "Mayo Clinic", "Micron",
    "Navico", "Nutanix", "Optum", "PAN", "Piaggio", "PwC", "Qualcomm",
    "Raymond Corporation", "RBS", "Red Hat", "ResMed", "RingCentral",
    "Rockwell Automation", "Samsung", "Sandia", "ServiceNow", "Signify", "Sonova",
    "Splunk", "STIHL", "Sub-Zero", "Swift", "Thomson Reuters", "Topcon",
    "Translation.com", "TransUnion", "TTC", "Toyota", "TxDOT", "UBS", "USMC",
    "Verizon", "Volkswagen", "Workday", "Zebra",
}
_MIXED_CUSTOMER = "Mixed (row-level cohorts)"
_MULTI_CUSTOMER_ALIASES = {
    "abs ubs swift": ("American Bureau of Shipping", "UBS", "Swift"),
}
MIXED_CUSTOMER_ASSIGNMENT = _MIXED_CUSTOMER
_CUSTOMER_LABELS = {
    "3m": "3M",
    "abs": "American Bureau of Shipping",
    "aetna": "Aetna",
    "amex": "American Express",
    "arielcop": "Ariel Corporation",
    "arielcorp": "Ariel Corporation",
    "astrazeneca": "AstraZeneca",
    "avaya": "Avaya",
    "bannerengineering": "Banner Engineering",
    "basco": "BASCO",
    "benq": "BenQ",
    "blackberry": "BlackBerry",
    "bretting": "Bretting",
    "broadcom": "Broadcom",
    "centene": "Centene",
    "citrix": "Citrix",
    "cisco": "Cisco",
    "csg": "Cloud Software Group",
    "ciena": "Ciena",
    "cmrsurgical": "CMR Surgical",
    "crown": "Crown Equipment",
    "deluxe": "Deluxe",
    "dfs": "DFS",
    "dow": "Dow",
    "dsv": "DSV",
    "eaton": "Eaton",
    "emerson": "Emerson",
    "enbridge": "Enbridge",
    "erie": "Erie Insurance",
    "erieinsurance": "Erie Insurance",
    "ey": "EY",
    "eycom": "EY",
    "faa": "FAA",
    "gm": "GM",
    "greenbytes": "GreenBytes",
    "gulfstream": "Gulfstream",
    "grundfos": "Grundfos",
    "haasautomation": "Haas Automation",
    "hyundai": "Hyundai",
    "hunterdouglas": "Hunter Douglas",
    "redhat": "Red Hat",
    "red_hat": "Red Hat",
    "ibm": "IBM",
    "informatica": "Informatica",
    "intel": "Intel",
    "isuzu-intec-corp": "Isuzu Intec Corporation",
    "swift": "Swift",
    "lexmark": "Lexmark",
    "topcon": "Topcon",
    "fidelity": "Fidelity",
    "jpmc": "JPMC",
    "jpmorgan": "JPMC",
    "jp_morgan": "JPMC",
    "kone": "KONE",
    "kone-production-files": "KONE",
    "kyndryl": "Kyndryl",
    "kogei-intec-corp": "Kogei Intec Corporation",
    "kyocera": "Kyocera",
    "marriott": "Marriott",
    "mayoclinic": "Mayo Clinic",
    "mayo_clinic": "Mayo Clinic",
    "micron": "Micron",
    "navico": "Navico",
    "nutanix": "Nutanix",
    "optum": "Optum",
    "pan": "PAN",
    "piaggio": "Piaggio",
    "qualcomm": "Qualcomm",
    "raymondcorp": "Raymond Corporation",
    "rbs": "RBS",
    "thomsonreuters": "Thomson Reuters",
    "thomson_reuters": "Thomson Reuters",
    "pwc": "PwC",
    "linkedin": "LinkedIn",
    "sonova": "Sonova",
    "resmed": "ResMed",
    "ringcentral": "RingCentral",
    "rockwellautomation": "Rockwell Automation",
    "samsung": "Samsung",
    "sandia": "Sandia",
    "splunk": "Splunk",
    "stihl": "STIHL",
    "servicenow": "ServiceNow",
    "subzero": "Sub-Zero",
    "transunionllc": "TransUnion",
    "ttc": "TTC",
    "toyota": "Toyota",
    "tr": "Thomson Reuters",
    "translation.com": "Translation.com",
    "txdot": "TxDOT",
    "demant": "Demant",
    "transunion": "TransUnion",
    "ubs": "UBS",
    "usmc": "USMC",
    "workday": "Workday",
    "zebra": "Zebra",
    "banner": "Banner Engineering",
    "verizon": "Verizon",
    "volkswagen": "Volkswagen",
}
_IGNORED_COMPONENT_TOKENS = {"miscellaneous", "triaged"}
_SUMMARY_CUSTOMER_PATTERNS = (
    (re.compile(r"\bJPMC\b", re.I), "JPMC"),
    (re.compile(r"\bCloud Software Group\b", re.I), "Cloud Software Group"),
    (re.compile(r"\bHaas Automation\b", re.I), "Haas Automation"),
    (re.compile(r"\bSignify\b", re.I), "Signify"),
    (re.compile(r"\bKyndryl\b", re.I), "Kyndryl"),
    (re.compile(r"\bCiena(?: Corp)?\b", re.I), "Ciena"),
    (re.compile(r"\bEnbridge\b", re.I), "Enbridge"),
    (re.compile(r"\bAetna\b", re.I), "Aetna"),
    (re.compile(r"\bServiceNow\b", re.I), "ServiceNow"),
    (re.compile(r"\bSonova\b", re.I), "Sonova"),
    (re.compile(r"\bCentene\b", re.I), "Centene"),
    (re.compile(r"\bBroadcom\b", re.I), "Broadcom"),
    (re.compile(r"\bCisco\b", re.I), "Cisco"),
    (re.compile(r"\bSub[- ]Zero\b", re.I), "Sub-Zero"),
    (re.compile(r"\bRed Hat\b", re.I), "Red Hat"),
    (re.compile(r"\bDB Instance Provisioning for HAAS Equipment\b", re.I), "Haas Equipment"),
    (re.compile(r"\bDB Instance Provisioning for Lexmark\b", re.I), "Lexmark"),
    (re.compile(r"\bDB Instance Provisioning for Workday\b", re.I), "Workday"),
    (re.compile(r"\bDB Instance Provisioning for Red\s*Hat\b", re.I), "Red Hat"),
    (re.compile(r"\bDB Instance Provisioning for Avaya\b", re.I), "Avaya"),
    (re.compile(r"\bDB Instance Provisioning for LinkedIn\b", re.I), "LinkedIn"),
    (re.compile(r"\bDB Instance Provisioning for Crown Equipment\b", re.I), "Crown Equipment"),
    (re.compile(r"\bIBM\b", re.I), "IBM"),
)
_UNSAFE_CUSTOMER_RE = re.compile(
    r"(?i)(?:https?://|@AdobeOrg|\[~|client[_ -]?secret|access[_ -]?token|oauth[_ -]?token|password|feature[_ -]?flag)"
)


@dataclass
class ParsedCsvIssue:
    issue_key: str
    issue: dict[str, Any]
    comments: list[dict[str, str]]
    acceptance_criteria: str
    root_cause: str
    test_plan: str
    resolution: str
    jira_updated_at: str
    company_names: list[str]
    customer_names: list[str]
    customer_cohorts: list[str]
    raw_components: list[str]
    component_classification_source: str
    component_inference_signals: list[str]
    source_components: list[str]
    component_assignment_method: str
    noncanonical_components: list[str]
    resolutions: list[str]
    source_file_hashes: list[str]
    import_provenance: list[dict[str, str]]
    evidence_archive: dict[str, list[str]]
    linked_issue_refs: list[str]
    attachment_filenames: list[str]
    redacted_fields: int
    source_evidence_mode: str


@dataclass
class ParsedCsvFile:
    filename: str
    file_hash: str
    headers: list[str]
    issues: list[ParsedCsvIssue]
    duplicate_headers: dict[str, int]
    resolution_counts: dict[str, int]
    redacted_fields: int
    component_counts: dict[str, int]
    rows_without_canonical_component: int
    rows_with_noncanonical_component: int
    noncanonical_component_values: list[str]
    rows_with_ignored_component_value: int
    ignored_component_values: list[str]
    source_evidence_mode: str
    missing_behavior_columns: list[str]
    detected_customer: str = ""
    detection_confidence: str = "none"
    detection_signals: list[str] | None = None
    detection_warnings: list[str] | None = None


def _sanitize_text(value: Any) -> tuple[str, int]:
    text = str(value or "").replace("\x00", "").strip()
    redactions = 0
    text, count = _URL_CREDENTIAL_RE.subn(r"\1[redacted-credentials]@", text)
    redactions += count
    for pattern, replacement in (
        (_EMAIL_RE, "[redacted-email]"),
        (_IMS_ORG_RE, "[redacted-ims-org]"),
        (_MENTION_RE, "[redacted-mention]"),
        (_SECRET_RE, "[redacted-secret]"),
        (_STRONG_CREDENTIAL_PAIR_RE, "[redacted-credentials]"),
    ):
        text, count = pattern.subn(replacement, text)
        redactions += count
    return text, redactions


def _dedupe(values: list[str], *, limit: int = 200) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))[:limit]


def _canonical_customer(value: str) -> str:
    clean = re.sub(r"\s+", " ", str(value or "").strip())
    key = re.sub(r"[-_]+", " ", clean).casefold()
    return _CUSTOMER_ALIASES.get(key, clean)


def _canonical_customer_values(value: str) -> list[str]:
    clean = re.sub(r"\s+", " ", str(value or "").strip())
    key = re.sub(r"[-_]+", " ", clean).casefold()
    values = _MULTI_CUSTOMER_ALIASES.get(key)
    return list(values) if values else [_canonical_customer(clean)]


def _ignored_component_value(value: str) -> bool:
    token = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
    return token in _IGNORED_COMPONENT_TOKENS


def _customers_from_summary(value: str) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return [customer for pattern, customer in _SUMMARY_CUSTOMER_PATTERNS if pattern.search(text)]


def _customer_label_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _safe_customer_label_registry(issues: list[ParsedCsvIssue]) -> dict[str, str]:
    """Build exact, source-backed label aliases from safe customer/company fields."""
    registry: dict[str, str] = {}
    legal_suffixes = {
        "co",
        "company",
        "corp",
        "corporation",
        "inc",
        "llc",
        "ltd",
        "limited",
        "plc",
    }
    acronym_stopwords = {"and", "of", "the"}
    for issue in issues:
        for raw_value in issue.customer_names + issue.company_names:
            display = _canonical_customer(raw_value)
            token = _customer_label_token(display)
            if token:
                registry.setdefault(token, display)
            words = re.findall(r"[A-Za-z0-9]+", display)
            trimmed = list(words)
            while trimmed and trimmed[-1].casefold() in legal_suffixes:
                trimmed.pop()
            if trimmed and len(trimmed) < len(words):
                trimmed_token = _customer_label_token(" ".join(trimmed))
                if trimmed_token:
                    registry.setdefault(trimmed_token, display)
            acronym_words = [
                word
                for word in words
                if word.casefold() not in acronym_stopwords and word
            ]
            acronym = "".join(word[0] for word in acronym_words)
            if 2 <= len(acronym) <= 6:
                registry.setdefault(acronym.casefold(), display)
    return registry


def _safe_customer_values(values: list[str]) -> tuple[list[str], int]:
    output: list[str] = []
    redactions = 0
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        if raw.isdigit() or _UNSAFE_CUSTOMER_RE.search(raw) or _EMAIL_RE.search(raw) or _IMS_ORG_RE.search(raw):
            redactions += 1
            continue
        clean, count = _sanitize_text(raw)
        redactions += count
        if not clean or clean.startswith("[redacted-"):
            continue
        output.extend(_canonical_customer_values(clean))
    return _dedupe(output, limit=100), redactions


def _detect_file_customer(item: ParsedCsvFile) -> tuple[str, str, list[str], list[str]]:
    label_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    summary_counts: Counter[str] = Counter()
    total = max(len(item.issues), 1)
    for issue in item.issues:
        labels = issue.issue.get("fields", {}).get("labels") or []
        row_labels = {_CUSTOMER_LABELS.get(str(label).strip().casefold(), "") for label in labels}
        for customer in row_labels - {""}:
            label_counts[customer] += 1
        for customer in issue.customer_names + issue.company_names:
            canonical = _canonical_customer(customer)
            if canonical in _SUPPORTED_CUSTOMERS:
                field_counts[canonical] += 1
        for customer in set(_customers_from_summary(issue.issue.get("fields", {}).get("summary") or "")):
            summary_counts[customer] += 1
    signals: list[str] = []
    candidates = set(label_counts) | set(field_counts) | set(summary_counts)
    for customer in sorted(candidates):
        signals.append(
            f"{customer}: label rows {label_counts[customer]}/{total}; "
            f"safe customer-field rows {field_counts[customer]}/{total}; "
            f"explicit summary rows {summary_counts[customer]}/{total}"
        )
    unanimous = [customer for customer, count in label_counts.items() if count == total]
    warnings: list[str] = []
    if len(unanimous) == 1:
        return unanimous[0], "high", signals, warnings
    row_covered = sum(1 for issue in item.issues if issue.customer_cohorts)
    row_cohorts = sorted(
        {customer for issue in item.issues for customer in issue.customer_cohorts},
        key=str.casefold,
    )
    if row_covered == total and len(row_cohorts) > 1:
        signals.append(f"Mixed row-level cohort coverage: {row_covered}/{total} rows; {', '.join(row_cohorts)}")
        return _MIXED_CUSTOMER, "high", signals, warnings
    ranked = (label_counts + field_counts + summary_counts).most_common()
    if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        warnings.append("Customer was inferred from majority evidence; confirm before import.")
        return ranked[0][0], "medium", signals, warnings
    warnings.append("Customer could not be inferred unambiguously; assign it before import.")
    return "", "low" if ranked else "none", signals, warnings


def _parse_comment(value: str) -> tuple[dict[str, str] | None, int]:
    parts = value.split(";", 2)
    created = parts[0].strip() if parts else ""
    body = parts[2] if len(parts) == 3 else value
    clean, redactions = _sanitize_text(body)
    if not clean:
        return None, redactions
    return {"created": created[:80], "author": "", "body_text": clean[:12_000]}, redactions


def _attachment_filename(value: str) -> str:
    parts = value.split(";", 3)
    raw = parts[2] if len(parts) >= 3 else ""
    filename = Path(raw.replace("\\", "/")).name
    filename, _ = _sanitize_text(filename)
    return filename[:500]


def _parse_datetime(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        for fmt in ("%d/%b/%y %I:%M %p", "%d/%b/%y %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
    return None


def should_skip_existing(existing_updated: datetime | None, incoming_updated: str) -> bool:
    """Protect dated evidence when an incoming CSV timestamp is older or absent."""
    incoming = _parse_datetime(incoming_updated)
    return bool(existing_updated and (incoming is None or existing_updated > incoming))


def parse_jira_csv_bytes(data: bytes, filename: str) -> ParsedCsvFile:
    if not filename.lower().endswith(".csv"):
        raise ValueError("Only .csv Jira exports are accepted")
    if not data:
        raise ValueError("CSV file is empty")
    if len(data) > MAX_CSV_BYTES:
        raise ValueError(f"CSV file exceeds the {MAX_CSV_BYTES // (1024 * 1024)} MB limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        headers = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV file has no header row") from exc
    missing = sorted(CORE_REQUIRED_HEADERS - set(headers))
    if missing:
        raise ValueError("Missing required Jira columns: " + ", ".join(missing))
    missing_behavior_columns = sorted(BEHAVIORAL_EVIDENCE_HEADERS - set(headers))
    if not missing_behavior_columns:
        source_evidence_mode = "behavioral"
    elif len(missing_behavior_columns) == len(BEHAVIORAL_EVIDENCE_HEADERS):
        source_evidence_mode = "metadata_only"
    else:
        source_evidence_mode = "partial"

    positions: dict[str, list[int]] = defaultdict(list)
    for index, header in enumerate(headers):
        positions[header].append(index)
    duplicate_headers = {key: len(indexes) for key, indexes in positions.items() if len(indexes) > 1}

    normalized_file_hash = hashlib.sha256(data).hexdigest()
    issues: list[ParsedCsvIssue] = []
    resolution_counts: Counter[str] = Counter()
    total_redactions = 0
    seen_keys: set[str] = set()

    def values(row: list[str], header: str) -> list[str]:
        return [row[index].strip() for index in positions.get(header, []) if index < len(row) and row[index].strip()]

    def first(row: list[str], header: str) -> str:
        found = values(row, header)
        return found[0] if found else ""

    rows = list(reader)
    if len(rows) > MAX_CSV_ROWS:
        raise ValueError(f"CSV exceeds the {MAX_CSV_ROWS} row limit")
    for row_number, row in enumerate(rows, start=2):
        if len(row) != len(headers):
            raise ValueError(f"Row {row_number} has {len(row)} columns; expected {len(headers)}")
        issue_key = first(row, "Issue key").upper()
        if not _JIRA_KEY_RE.match(issue_key):
            raise ValueError(f"Row {row_number} has an invalid Issue key")
        if issue_key in seen_keys:
            raise ValueError(f"Duplicate Issue key in CSV: {issue_key}")
        seen_keys.add(issue_key)

        redactions = 0
        sanitized: dict[str, str] = {}
        for name in (
            "Summary",
            "Description",
            "Environment",
            "Custom field (Acceptance Criteria)",
            "Custom field (Root Cause)",
            "Custom field (Test Plan)",
        ):
            sanitized[name], count = _sanitize_text(first(row, name))
            redactions += count

        labels = _dedupe(values(row, "Labels"))
        raw_components = _dedupe(values(row, "Component/s"))
        source_components = list(raw_components)
        encoded_source_components = first(row, SOURCE_COMPONENTS_HEADER)
        if encoded_source_components:
            try:
                decoded_source_components = json.loads(encoded_source_components)
            except (json.JSONDecodeError, TypeError):
                decoded_source_components = []
            if isinstance(decoded_source_components, list):
                source_components = _dedupe(
                    [str(value) for value in decoded_source_components if str(value).strip()]
                )
        component_assignment_method = first(row, COMPONENT_ASSIGNMENT_METHOD_HEADER)[:80]
        source_file_hash = first(row, SOURCE_FILE_HASH_HEADER).strip().casefold()
        if not re.fullmatch(r"[a-f0-9]{64}", source_file_hash):
            source_file_hash = normalized_file_hash
        components = canonical_component_names(raw_components)
        component_classification_source = "jira_component" if components else "unclassified"
        component_inference_signals: list[str] = []
        if not components:
            components, component_inference_signals = infer_component_names(
                sanitized["Summary"],
                sanitized["Description"],
            )
            if components:
                component_classification_source = COMPONENT_TEXT_CLASSIFIER_VERSION
        noncanonical_components = [
            component
            for component in raw_components
            if not canonical_component_name(component) and not _ignored_component_value(component)
        ]
        fix_versions = _dedupe(values(row, "Fix Version/s"))
        affected_versions = _dedupe(values(row, "Affects Version/s"))
        customer_names, customer_redactions = _safe_customer_values(
            values(row, "Custom field (Customer Names)")
            + values(row, "Custom field (Customers)")
            + values(row, "Custom field (Beta Customer Name)")
        )
        company_names, company_redactions = _safe_customer_values(
            values(row, "Custom field (Company)") + values(row, "Company")
        )
        redactions += customer_redactions + company_redactions
        row_customer_cohorts = _dedupe(
            [
                customer
                for customer in (
                    [_CUSTOMER_LABELS.get(str(label).strip().casefold(), "") for label in labels]
                    + [_canonical_customer(value) for value in customer_names + company_names]
                    + _customers_from_summary(sanitized["Summary"])
                )
                if customer in _SUPPORTED_CUSTOMERS
            ],
            limit=20,
        )

        comments: list[dict[str, str]] = []
        for raw_comment in values(row, "Comment"):
            comment, count = _parse_comment(raw_comment)
            redactions += count
            if comment:
                comments.append(comment)

        attachment_filenames = _dedupe(
            [_attachment_filename(raw) for raw in values(row, "Attachment")],
            limit=100,
        )
        linked_refs: list[str] = []
        for header, indexes in positions.items():
            if not _LINK_HEADER_RE.search(header):
                continue
            relation = header.replace("Inward issue link", "inward").replace("Outward issue link", "outward")
            for index in indexes:
                raw = row[index].strip()
                for linked_key in re.findall(r"\b[A-Z][A-Z0-9]+-\d+\b", raw.upper()):
                    linked_refs.append(f"{relation}: {linked_key}")

        resolution = first(row, "Resolution")
        resolution_counts[resolution or "Unspecified"] += 1
        description = sanitized["Description"]
        if sanitized["Environment"]:
            description = f"{description}\n\nEnvironment:\n{sanitized['Environment']}".strip()

        fields = {
            "summary": sanitized["Summary"],
            "description": description,
            "issuetype": {"name": first(row, "Issue Type")},
            "status": {"name": first(row, "Status")},
            "priority": {"name": first(row, "Priority")},
            "labels": labels,
            "components": [{"name": item} for item in components],
            "_components_raw": source_components,
            "_component_classification_source": component_classification_source,
            "_component_inference_signals": component_inference_signals,
            "_component_assignment_method": component_assignment_method,
            "fixVersions": [{"name": item} for item in fix_versions],
            "versions": [{"name": item} for item in affected_versions],
            "created": first(row, "Created"),
            "updated": first(row, "Updated"),
            "resolutiondate": first(row, "Resolved"),
            "customfield_13400": sanitized["Custom field (Acceptance Criteria)"],
            "_csv_resolution": resolution,
            "_source_type": "jira_csv",
            "_source_file_hash": source_file_hash,
            "_csv_source_evidence_mode": source_evidence_mode,
        }
        issues.append(
            ParsedCsvIssue(
                issue_key=issue_key,
                issue={"key": issue_key, "fields": fields},
                comments=comments,
                acceptance_criteria=sanitized["Custom field (Acceptance Criteria)"],
                root_cause=sanitized["Custom field (Root Cause)"],
                test_plan=sanitized["Custom field (Test Plan)"],
                resolution=resolution,
                jira_updated_at=first(row, "Updated"),
                company_names=company_names,
                customer_names=customer_names,
                customer_cohorts=row_customer_cohorts,
                raw_components=raw_components,
                component_classification_source=component_classification_source,
                component_inference_signals=component_inference_signals,
                source_components=source_components,
                component_assignment_method=component_assignment_method,
                noncanonical_components=noncanonical_components,
                resolutions=[resolution] if resolution else [],
                source_file_hashes=_dedupe([source_file_hash, normalized_file_hash], limit=50),
                import_provenance=[
                    {
                        "filename": Path(filename).name,
                        "file_hash": source_file_hash,
                        "normalized_file_hash": normalized_file_hash,
                        "jira_updated_at": first(row, "Updated")[:80],
                        "source_evidence_mode": source_evidence_mode,
                        "component_classification_source": component_classification_source,
                        "component_assignment_method": component_assignment_method,
                    }
                ],
                evidence_archive={
                    "acceptance_criteria": [sanitized["Custom field (Acceptance Criteria)"]]
                    if sanitized["Custom field (Acceptance Criteria)"] else [],
                    "root_causes": [sanitized["Custom field (Root Cause)"]]
                    if sanitized["Custom field (Root Cause)"] else [],
                    "test_plans": [sanitized["Custom field (Test Plan)"]]
                    if sanitized["Custom field (Test Plan)"] else [],
                    "comments": [comment["body_text"] for comment in comments if comment.get("body_text")],
                    "linked_issue_refs": _dedupe(linked_refs, limit=200),
                    "attachment_filenames": attachment_filenames,
                    "component_normalization": [
                        first(row, COMPONENT_ASSIGNMENT_EVIDENCE_HEADER)
                    ]
                    if first(row, COMPONENT_ASSIGNMENT_EVIDENCE_HEADER)
                    else [],
                },
                linked_issue_refs=_dedupe(linked_refs, limit=200),
                attachment_filenames=attachment_filenames,
                redacted_fields=redactions,
                source_evidence_mode=source_evidence_mode,
            )
        )
        total_redactions += redactions

    safe_label_registry = _safe_customer_label_registry(issues)
    for issue in issues:
        labels = issue.issue.get("fields", {}).get("labels") or []
        verified_label_customers = [
            safe_label_registry[token]
            for label in labels
            for token in [_customer_label_token(str(label))]
            if token in safe_label_registry
        ]
        issue.customer_cohorts = _dedupe(
            issue.customer_cohorts + verified_label_customers,
            limit=20,
        )

    component_counts = Counter(
        str(component.get("name") or "")
        for issue in issues
        for component in issue.issue.get("fields", {}).get("components", [])
        if isinstance(component, dict) and str(component.get("name") or "")
    )
    parsed_file = ParsedCsvFile(
        filename=Path(filename).name,
        file_hash=normalized_file_hash,
        headers=headers,
        issues=issues,
        duplicate_headers=duplicate_headers,
        resolution_counts=dict(resolution_counts),
        redacted_fields=total_redactions,
        component_counts={
            component: component_counts.get(component, 0)
            for component in CANONICAL_JIRA_COMPONENTS
        },
        rows_without_canonical_component=sum(
            1
            for issue in issues
            if not issue.issue.get("fields", {}).get("components")
        ),
        rows_with_noncanonical_component=sum(
            1 for issue in issues if issue.noncanonical_components
        ),
        noncanonical_component_values=_dedupe(
            [
                component
                for issue in issues
                for component in issue.noncanonical_components
            ]
        ),
        rows_with_ignored_component_value=sum(
            1
            for issue in issues
            if any(_ignored_component_value(component) for component in issue.raw_components)
        ),
        ignored_component_values=_dedupe(
            [
                component
                for issue in issues
                for component in issue.raw_components
                if _ignored_component_value(component)
            ]
        ),
        source_evidence_mode=source_evidence_mode,
        missing_behavior_columns=missing_behavior_columns,
    )
    detected, confidence, signals, warnings = _detect_file_customer(parsed_file)
    parsed_file.detected_customer = detected
    parsed_file.detection_confidence = confidence
    parsed_file.detection_signals = signals
    parsed_file.detection_warnings = warnings
    return parsed_file


def classify_jira_import_profile(
    parsed: ParsedCsvFile, requested_profile: str = "auto"
) -> str:
    """Classify a CSV without treating a few Native PDF rows as a PDF-only corpus."""
    requested = str(requested_profile or "auto").strip().casefold()
    if requested not in SUPPORTED_IMPORT_PROFILES:
        raise ValueError(f"Unsupported Jira import profile: {requested_profile}")
    if requested != "auto":
        return requested

    total = len(parsed.issues)
    editor_rows = 0
    new_editor_rows = 0
    native_pdf_rows = 0
    for issue in parsed.issues:
        components = {
            str(component.get("name") or "")
            for component in issue.issue.get("fields", {}).get("components", [])
            if isinstance(component, dict)
        }
        if "Editor" in components:
            editor_rows += 1
        if "new_editor" in enrich_jira(issue.issue).affected_features:
            new_editor_rows += 1
        if any(
            re.sub(r"[_-]+", " ", str(component or "").strip()).casefold()
            == "native pdf"
            for component in issue.raw_components
        ):
            native_pdf_rows += 1

    if total and editor_rows == total and new_editor_rows:
        return "editor-new"
    if total and native_pdf_rows / total >= NATIVE_PDF_PROFILE_MIN_RATIO:
        return "native-pdf"
    return "customer-history"


def _normalize_customer_assignments(
    parsed: list[ParsedCsvFile], assignments: dict[str, str] | None
) -> dict[str, str]:
    supplied = assignments or {}
    normalized: dict[str, str] = {}
    for item in parsed:
        raw = supplied.get(item.file_hash, item.detected_customer)
        if str(raw).strip() == _MIXED_CUSTOMER:
            normalized[item.file_hash] = _MIXED_CUSTOMER
            continue
        customer = _canonical_customer(raw)
        if customer not in _SUPPORTED_CUSTOMERS:
            customer = ""
        normalized[item.file_hash] = customer
    return normalized


def _issue_richness(issue: ParsedCsvIssue) -> tuple[int, str]:
    fields = issue.issue.get("fields") or {}
    score = sum(len(str(fields.get(key) or "")) for key in ("summary", "description", "customfield_13400"))
    score += sum(len(values) for values in (issue.comments, issue.linked_issue_refs, issue.attachment_filenames)) * 100
    return score, issue.import_provenance[0].get("file_hash", "") if issue.import_provenance else ""


def merge_parsed_issues(
    parsed_files: list[ParsedCsvFile], assignments: dict[str, str] | None = None
) -> list[ParsedCsvIssue]:
    """Merge cross-file snapshots while retaining every safe customer association and evidence signal."""
    assignment_map = _normalize_customer_assignments(parsed_files, assignments)
    grouped: dict[str, list[ParsedCsvIssue]] = defaultdict(list)
    for parsed_file in parsed_files:
        cohort = assignment_map.get(parsed_file.file_hash, "")
        if cohort == _MIXED_CUSTOMER:
            cohort = ""
        for issue in parsed_file.issues:
            grouped[issue.issue_key].append(
                replace(
                    issue,
                    customer_cohorts=_dedupe(
                        issue.customer_cohorts + ([cohort] if cohort else []),
                        limit=20,
                    ),
                )
            )

    merged: list[ParsedCsvIssue] = []
    for issue_key in sorted(grouped):
        snapshots = grouped[issue_key]
        winner = max(
            snapshots,
            key=lambda item: (_parse_datetime(item.jira_updated_at) or datetime.min, *_issue_richness(item)),
        )
        output = replace(winner, issue=copy.deepcopy(winner.issue), comments=list(winner.comments))
        fields = output.issue.setdefault("fields", {})

        def union(attr: str, limit: int = 200) -> list[str]:
            return _dedupe([value for snapshot in snapshots for value in getattr(snapshot, attr)], limit=limit)

        def field_union(key: str, object_values: bool = False) -> list[Any]:
            values: list[str] = []
            for snapshot in snapshots:
                raw_values = snapshot.issue.get("fields", {}).get(key) or []
                for value in raw_values:
                    values.append(str(value.get("name") or "") if object_values and isinstance(value, dict) else str(value))
            clean = _dedupe(values)
            return [{"name": value} for value in clean] if object_values else clean

        fields["labels"] = field_union("labels")
        output.source_evidence_mode = max(
            (snapshot.source_evidence_mode for snapshot in snapshots),
            key={"metadata_only": 0, "partial": 1, "behavioral": 2}.get,
        )
        fields["_csv_source_evidence_mode"] = output.source_evidence_mode
        output.raw_components = union("raw_components")
        classification_sources = {
            snapshot.component_classification_source
            for snapshot in snapshots
            if snapshot.component_classification_source
        }
        output.component_classification_source = (
            "jira_component"
            if "jira_component" in classification_sources
            else COMPONENT_TEXT_CLASSIFIER_VERSION
            if COMPONENT_TEXT_CLASSIFIER_VERSION in classification_sources
            else "unclassified"
        )
        output.component_inference_signals = union("component_inference_signals", 50)
        output.source_components = union("source_components")
        output.component_assignment_method = ",".join(
            _dedupe(
                [snapshot.component_assignment_method for snapshot in snapshots],
                limit=20,
            )
        )[:80]
        output.noncanonical_components = union("noncanonical_components")
        fields["components"] = [
            {"name": value}
            for value in canonical_component_names(
                [
                    str(item.get("name") or "")
                    for item in field_union("components", object_values=True)
                    if isinstance(item, dict)
                ]
            )
        ]
        fields["_components_raw"] = output.source_components or output.raw_components
        fields["_component_classification_source"] = output.component_classification_source
        fields["_component_inference_signals"] = output.component_inference_signals
        fields["_component_assignment_method"] = output.component_assignment_method
        fields["fixVersions"] = field_union("fixVersions", object_values=True)
        fields["versions"] = field_union("versions", object_values=True)
        output.company_names = union("company_names", 100)
        output.customer_names = union("customer_names", 100)
        output.customer_cohorts = union("customer_cohorts", 20)
        output.resolutions = union("resolutions", 50)
        output.source_file_hashes = union("source_file_hashes", 50)
        output.linked_issue_refs = union("linked_issue_refs")
        output.attachment_filenames = union("attachment_filenames", 100)
        output.comments = list(
            {
                (comment.get("created", ""), comment.get("body_text", "")): comment
                for snapshot in snapshots
                for comment in snapshot.comments
            }.values()
        )[:40]
        provenance_seen: set[tuple[str, str]] = set()
        output.import_provenance = []
        for snapshot in snapshots:
            for entry in snapshot.import_provenance:
                key = (entry.get("file_hash", ""), entry.get("jira_updated_at", ""))
                if key not in provenance_seen:
                    provenance_seen.add(key)
                    output.import_provenance.append(entry)
        archive_keys = {
            key for snapshot in snapshots for key in snapshot.evidence_archive
        }
        output.evidence_archive = {
            key: _dedupe(
                [value for snapshot in snapshots for value in snapshot.evidence_archive.get(key, [])],
                limit=200,
            )
            for key in sorted(archive_keys)
        }
        output.redacted_fields = sum(snapshot.redacted_fields for snapshot in snapshots)
        merged.append(output)
    return merged


def preview_jira_csv_files(
    files: list[tuple[str, bytes]], customer_assignments: dict[str, str] | None = None
) -> dict[str, Any]:
    parsed = [parse_jira_csv_bytes(data, filename) for filename, data in files]
    keys = [issue.issue_key for item in parsed for issue in item.issues]
    duplicate_keys = sorted(key for key, count in Counter(keys).items() if count > 1)
    assignment_map = _normalize_customer_assignments(parsed, customer_assignments)
    completed_hashes = _completed_file_hashes()
    customer_assignment_valid = all(assignment_map.values())
    rows_without_canonical_component = sum(
        item.rows_without_canonical_component for item in parsed
    )
    rows_with_noncanonical_component = sum(
        item.rows_with_noncanonical_component for item in parsed
    )
    component_quality_valid = (
        rows_without_canonical_component == 0
        and rows_with_noncanonical_component == 0
    )
    validation_errors: list[str] = []
    if not customer_assignment_valid:
        validation_errors.append("Confirm a supported customer assignment for every file")
    if rows_without_canonical_component:
        validation_errors.append(
            f"{rows_without_canonical_component} Jira rows lack a canonical Component/s value"
        )
    if rows_with_noncanonical_component:
        validation_errors.append(
            f"{rows_with_noncanonical_component} Jira rows contain unsupported Component/s values"
        )
    return {
        "valid": customer_assignment_valid and component_quality_valid,
        "importer_version": IMPORTER_VERSION,
        "canonical_components": list(CANONICAL_JIRA_COMPONENTS),
        "customer_assignment_valid": customer_assignment_valid,
        "component_quality_valid": component_quality_valid,
        "validation_errors": validation_errors,
        "total_files": len(parsed),
        "total_rows": len(keys),
        "unique_issue_keys": len(set(keys)),
        "overlap_count": len(keys) - len(set(keys)),
        "overlapping_issue_keys": duplicate_keys,
        "redacted_fields": sum(item.redacted_fields for item in parsed),
        "rows_without_canonical_component": rows_without_canonical_component,
        "rows_with_noncanonical_component": rows_with_noncanonical_component,
        "source_evidence_modes": dict(
            Counter(issue.source_evidence_mode for item in parsed for issue in item.issues)
        ),
        "metadata_only_rows": sum(
            1
            for item in parsed
            for issue in item.issues
            if issue.source_evidence_mode == "metadata_only"
        ),
        "files": [
            {
                "filename": item.filename,
                "file_hash": item.file_hash,
                "rows": len(item.issues),
                "columns": len(item.headers),
                "duplicate_headers": item.duplicate_headers,
                "resolution_counts": item.resolution_counts,
                "component_counts": item.component_counts,
                "rows_without_canonical_component": item.rows_without_canonical_component,
                "rows_with_noncanonical_component": item.rows_with_noncanonical_component,
                "noncanonical_component_values": item.noncanonical_component_values,
                "rows_with_ignored_component_value": item.rows_with_ignored_component_value,
                "ignored_component_values": item.ignored_component_values,
                "source_evidence_mode": item.source_evidence_mode,
                "missing_behavior_columns": item.missing_behavior_columns,
                "already_imported": item.file_hash in completed_hashes,
                "detected_customer": item.detected_customer,
                "assigned_customer": assignment_map.get(item.file_hash, ""),
                "customer_confidence": item.detection_confidence,
                "customer_evidence_signals": item.detection_signals or [],
                "warnings": (item.detection_warnings or [])
                + (
                    [
                        "Every Jira row must include at least one of the six canonical components."
                    ]
                    if item.rows_without_canonical_component
                    else []
                )
                + (
                    [
                        "Unsupported component values: "
                        + ", ".join(item.noncanonical_component_values)
                    ]
                    if item.noncanonical_component_values
                    else []
                )
                + (
                    [
                        "Ignored non-taxonomy values found in Component/s: "
                        + ", ".join(item.ignored_component_values)
                    ]
                    if item.ignored_component_values
                    else []
                )
                + (
                    [
                        "Metadata-only Jira export: missing "
                        + ", ".join(item.missing_behavior_columns)
                        + "; rows are indexed as scope/history signals only."
                    ]
                    if item.source_evidence_mode == "metadata_only"
                    else []
                ),
            }
            for item in parsed
        ],
    }


def _completed_file_hashes(*, exclude_run_id: str = "") -> set[str]:
    db = SessionLocal()
    try:
        rows = db.query(JiraCsvImportRun).filter(JiraCsvImportRun.status == "completed").all()
        return {
            str(file_hash)
            for row in rows
            if row.id != exclude_run_id and str(row.importer_version or "1") == IMPORTER_VERSION
            for file_hash in (row.file_hashes or [])
            if file_hash
        }
    finally:
        db.close()


def create_import_run(
    files: list[tuple[str, bytes]], *, created_by: str, customer_assignments: dict[str, str] | None = None
) -> tuple[str, list[Path]]:
    preview = preview_jira_csv_files(files, customer_assignments)
    if not preview["valid"]:
        raise ValueError("; ".join(preview["validation_errors"]))
    run_id = str(uuid.uuid4())
    import_dir = Path(__file__).resolve().parents[2] / "storage" / "jira_csv_imports" / run_id
    import_dir.mkdir(parents=True, exist_ok=False)
    paths: list[Path] = []
    for index, (filename, data) in enumerate(files):
        path = import_dir / f"{index:03d}-{Path(filename).name}"
        path.write_bytes(data)
        paths.append(path)
    db = SessionLocal()
    try:
        db.add(
            JiraCsvImportRun(
                id=run_id,
                status="pending",
                filenames=[item["filename"] for item in preview["files"]],
                file_hashes=[item["file_hash"] for item in preview["files"]],
                importer_version=IMPORTER_VERSION,
                customer_assignments={item["file_hash"]: item["assigned_customer"] for item in preview["files"]},
                total_rows=int(preview["total_rows"]),
                redacted_fields=int(preview["redacted_fields"]),
                created_by=created_by[:120],
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        for path in paths:
            path.unlink(missing_ok=True)
        import_dir.rmdir()
        raise
    finally:
        db.close()
    return run_id, paths


def get_import_run(run_id: str) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        row = db.query(JiraCsvImportRun).filter(JiraCsvImportRun.id == run_id).first()
        if row is None:
            return None
        percent = 100 if row.status == "completed" else int((row.processed_rows / row.total_rows) * 100) if row.total_rows else 0
        return {
            "import_id": row.id,
            "status": row.status,
            "filenames": row.filenames or [],
            "file_hashes": row.file_hashes or [],
            "importer_version": row.importer_version,
            "customer_assignments": row.customer_assignments or {},
            "profile_rebuild": row.profile_rebuild or {},
            "total_rows": row.total_rows,
            "processed_rows": row.processed_rows,
            "indexed_issues": row.indexed_issues,
            "skipped_issues": row.skipped_issues,
            "metadata_merged_issues": row.metadata_merged_issues,
            "failed_issues": row.failed_issues,
            "chunks_indexed": row.chunks_indexed,
            "redacted_fields": row.redacted_fields,
            "errors": row.errors or [],
            "progress_percent": max(0, min(100, percent)),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }
    finally:
        db.close()


def _set_run(run_id: str, **changes: Any) -> None:
    db = SessionLocal()
    try:
        row = db.query(JiraCsvImportRun).filter(JiraCsvImportRun.id == run_id).first()
        if row is None:
            return
        for key, value in changes.items():
            setattr(row, key, value)
        db.commit()
    finally:
        db.close()


def _union_values(existing: Any, incoming: list[str], *, limit: int = 200) -> list[str]:
    current = existing if isinstance(existing, list) else []
    return _dedupe([str(value) for value in current] + incoming, limit=limit)


def _trusted_csv_customer_names(
    existing: Any,
    parsed_issue: ParsedCsvIssue,
) -> list[str]:
    """Persist only explicit CSV customer fields and allowlisted row cohorts."""
    trusted = _dedupe(
        parsed_issue.customer_names + parsed_issue.customer_cohorts,
        limit=100,
    )
    trusted_tokens = {_customer_label_token(value) for value in trusted}
    label_tokens = {
        _customer_label_token(str(label))
        for label in parsed_issue.issue.get("fields", {}).get("labels") or []
    }
    current = existing if isinstance(existing, list) else []
    retained_existing = [
        str(value)
        for value in current
        if _customer_label_token(str(value)) not in label_tokens
        or _customer_label_token(str(value)) in trusted_tokens
    ]
    return _union_values(
        retained_existing,
        trusted,
        limit=100,
    )


def _metadata_only_merge(parsed_issue: ParsedCsvIssue) -> bool:
    """Union cohort/provenance evidence into a newer SQL/Chroma issue without replacing its content."""
    db = SessionLocal()
    try:
        row = db.query(JiraEnrichedIssue).filter(JiraEnrichedIssue.jira_key == parsed_issue.issue_key).first()
        if row is None:
            return False
        parsed_enriched = enrich_jira(parsed_issue.issue)
        row.company_names = _union_values(row.company_names, parsed_issue.company_names, limit=100)
        row.customer_names = _trusted_csv_customer_names(row.customer_names, parsed_issue)
        row.customer_cohorts = _union_values(row.customer_cohorts, parsed_issue.customer_cohorts, limit=20)
        row.affected_features = _union_values(
            row.affected_features,
            list(parsed_enriched.affected_features or []),
            limit=40,
        )
        row.affected_outputs = _union_values(
            row.affected_outputs,
            list(parsed_enriched.affected_outputs or []),
            limit=30,
        )
        if str(row.domain or "").strip().casefold() in {"", "unknown"}:
            row.domain = parsed_enriched.domain or "unknown"
            row.sub_domain = parsed_enriched.sub_domain or ""
        existing_components = list(row.components or [])
        parsed_components = [
            str(component.get("name") or "")
            for component in parsed_issue.issue.get("fields", {}).get("components", [])
            if isinstance(component, dict) and str(component.get("name") or "")
        ]
        raw_components = _dedupe(
            existing_components
            + parsed_issue.source_components
            + parsed_issue.raw_components
        )
        row.components = canonical_component_names(
            existing_components
            + parsed_components
            + parsed_issue.source_components
            + parsed_issue.raw_components
        )
        component_classification_source = (
            "existing_component_metadata"
            if existing_components
            else parsed_issue.component_classification_source
        )
        row.resolutions = _union_values(row.resolutions, parsed_issue.resolutions, limit=50)
        row.source_file_hashes = _union_values(row.source_file_hashes, parsed_issue.source_file_hashes, limit=50)
        provenance = list(row.import_provenance or [])
        seen = {(str(item.get("file_hash") or ""), str(item.get("jira_updated_at") or "")) for item in provenance}
        for item in parsed_issue.import_provenance:
            key = (item.get("file_hash", ""), item.get("jira_updated_at", ""))
            if key not in seen:
                seen.add(key)
                provenance.append(item)
        row.import_provenance = provenance[:100]
        archive = dict(row.evidence_archive or {})
        for key, values in parsed_issue.evidence_archive.items():
            archive[key] = _union_values(archive.get(key), values, limit=200)
        row.evidence_archive = archive
        row.updated_at = datetime.utcnow()
        db.query(JiraIssueChunk).filter(JiraIssueChunk.jira_key == parsed_issue.issue_key).update(
            {JiraIssueChunk.customer_names: row.customer_names}, synchronize_session=False
        )
        db.commit()
        component_metadata = component_filter_metadata(row.components)
        updated_chunks = update_documents_metadata(
            CHROMA_COLLECTION_JIRA_QA,
            {"jira_key": parsed_issue.issue_key},
            {
                "enrich_customers": json.dumps(row.customer_names, ensure_ascii=False)[:4000],
                "company_names": json.dumps(row.company_names, ensure_ascii=False)[:4000],
                "customer_cohorts": json.dumps(row.customer_cohorts, ensure_ascii=False)[:4000],
                "resolutions": json.dumps(row.resolutions, ensure_ascii=False)[:4000],
                "source_file_hashes": json.dumps(row.source_file_hashes, ensure_ascii=False)[:4000],
                "components": json.dumps(row.components, ensure_ascii=False)[:4000],
                "components_raw": json.dumps(raw_components, ensure_ascii=False)[:4000],
                "component_classification_source": component_classification_source[:80],
                "component_inference_signals": json.dumps(
                    parsed_issue.component_inference_signals,
                    ensure_ascii=False,
                )[:4000],
                **component_metadata,
                "enrich_domain": (row.domain or "unknown")[:120],
                "enrich_outputs": json.dumps(row.affected_outputs, ensure_ascii=False)[:4000],
                "enrich_features": json.dumps(row.affected_features, ensure_ascii=False)[:4000],
                "editor_variant": "new_editor" if "new_editor" in row.affected_features else "",
                "metadata_only_merge": True,
                "import_evidence_archive": json.dumps(row.evidence_archive, ensure_ascii=False)[:4000],
            },
        )
        if updated_chunks <= 0:
            raise RuntimeError(
                f"no Chroma chunks were updated for metadata-only Jira {parsed_issue.issue_key}"
            )
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _flush_issue_batch(
    batch: list[tuple[ParsedCsvIssue, Any, list[dict[str, Any]]]],
) -> tuple[int, int, list[str]]:
    rows = [chunk for _, _, chunks in batch for chunk in chunks]
    if not rows:
        return 0, 0, []
    embeddings = embed_texts_batched([row["document"] for row in rows], batch_size=48)
    if embeddings is None:
        return 0, 0, [f"{item.issue_key}: embedding batch failed" for item, _, _ in batch]
    ids = [row["chunk_id"] for row in rows]
    metadata = [
        {key: value for key, value in row["metadata"].items() if isinstance(value, (str, int, float, bool))}
        for row in rows
    ]
    vectors = [embeddings[index].tolist() for index in range(len(ids))]
    chroma_ok = False
    for attempt in range(1, 4):
        chroma_ok = add_documents(
            CHROMA_COLLECTION_JIRA_QA,
            ids,
            [row["document"] for row in rows],
            metadata,
            vectors,
        )
        if chroma_ok:
            break
        if attempt < 3:
            time.sleep(0.5 * attempt)
    if not chroma_ok:
        return 0, 0, [f"{item.issue_key}: Chroma upsert failed" for item, _, _ in batch]

    errors: list[str] = []
    persisted = 0
    db = SessionLocal()
    try:
        for parsed_issue, enriched, chunks in batch:
            try:
                upsert_jira_issue(db, enriched)
                insert_jira_chunks(db, parsed_issue.issue_key, chunks, enrichment=enriched)
                db.commit()
                persisted += len(chunks)
            except Exception as exc:
                db.rollback()
                delete_documents(CHROMA_COLLECTION_JIRA_QA, [chunk["chunk_id"] for chunk in chunks])
                errors.append(f"{parsed_issue.issue_key}: SQL persistence failed: {exc}")
    finally:
        db.close()
    return persisted, len(batch) - len(errors), errors


def run_import(run_id: str, paths: list[Path]) -> None:
    errors: list[str] = []
    processed = indexed = skipped = metadata_merged = failed = chunks_indexed = 0
    import_dir = paths[0].parent if paths else None
    try:
        if not is_chroma_available():
            raise RuntimeError("ChromaDB is not available")
        if not is_embedding_available():
            raise RuntimeError("Embedding model is not available")
        _set_run(run_id, status="running", started_at=datetime.utcnow())
        completed_hashes = _completed_file_hashes(exclude_run_id=run_id)
        db = SessionLocal()
        try:
            run_row = db.query(JiraCsvImportRun).filter(JiraCsvImportRun.id == run_id).first()
            customer_assignments = dict(run_row.customer_assignments or {}) if run_row else {}
        finally:
            db.close()
        parsed_files = [parse_jira_csv_bytes(path.read_bytes(), path.name.split("-", 1)[-1]) for path in paths]
        import_files = [item for item in parsed_files if item.file_hash not in completed_hashes]
        for item in parsed_files:
            if item.file_hash in completed_hashes:
                skipped += len(item.issues)
                processed += len(item.issues)
        merged_issues = merge_parsed_issues(import_files, customer_assignments)
        batch: list[tuple[ParsedCsvIssue, Any, list[dict[str, Any]]]] = []

        def flush() -> None:
            nonlocal chunks_indexed, indexed, failed, batch
            count, persisted_issues, batch_errors = _flush_issue_batch(batch)
            chunks_indexed += count
            indexed += persisted_issues
            failed += len(batch_errors)
            errors.extend(batch_errors)
            batch = []

        for parsed_issue in merged_issues:
                source_row_count = max(1, len(parsed_issue.import_provenance))
                db = SessionLocal()
                try:
                    existing = db.query(JiraEnrichedIssue).filter(JiraEnrichedIssue.jira_key == parsed_issue.issue_key).first()
                    existing_updated = existing.jira_updated_at if existing else None
                    existing_metadata = {
                        "components": list(existing.components or []),
                        "company_names": list(existing.company_names or []),
                        "customer_names": list(existing.customer_names or []),
                        "customer_cohorts": list(existing.customer_cohorts or []),
                        "resolutions": list(existing.resolutions or []),
                        "source_file_hashes": list(existing.source_file_hashes or []),
                        "import_provenance": list(existing.import_provenance or []),
                        "evidence_archive": dict(existing.evidence_archive or {}),
                    } if existing else {}
                finally:
                    db.close()
                if existing is not None and parsed_issue.source_evidence_mode == "metadata_only":
                    try:
                        if _metadata_only_merge(parsed_issue):
                            metadata_merged += 1
                        else:
                            skipped += 1
                    except Exception as exc:
                        failed += 1
                        errors.append(f"{parsed_issue.issue_key}: metadata-only merge failed: {exc}")
                    processed += source_row_count
                    continue
                if should_skip_existing(existing_updated, parsed_issue.jira_updated_at):
                    try:
                        if _metadata_only_merge(parsed_issue):
                            metadata_merged += 1
                        else:
                            skipped += 1
                    except Exception as exc:
                        failed += 1
                        errors.append(f"{parsed_issue.issue_key}: metadata-only merge failed: {exc}")
                    processed += source_row_count
                    continue
                try:
                    enriched = enrich_jira(parsed_issue.issue)
                    existing_provenance = existing_metadata.get("import_provenance", [])
                    provenance = list(existing_provenance)
                    seen_provenance = {
                        (str(item.get("file_hash") or ""), str(item.get("jira_updated_at") or ""))
                        for item in provenance if isinstance(item, dict)
                    }
                    for item in parsed_issue.import_provenance:
                        key = (item.get("file_hash", ""), item.get("jira_updated_at", ""))
                        if key not in seen_provenance:
                            seen_provenance.add(key)
                            provenance.append(item)
                    evidence_archive = dict(existing_metadata.get("evidence_archive") or {})
                    for key, values in parsed_issue.evidence_archive.items():
                        evidence_archive[key] = _union_values(evidence_archive.get(key), values, limit=200)
                    enriched = enriched.model_copy(
                        update={
                            "resolution": parsed_issue.resolution,
                            "resolutions": _union_values(existing_metadata.get("resolutions"), parsed_issue.resolutions, limit=50),
                            "jira_updated_at": parsed_issue.jira_updated_at,
                            "source_type": "jira_csv",
                            "source_file_hash": parsed_issue.source_file_hashes[0] if parsed_issue.source_file_hashes else "",
                            "source_file_hashes": _union_values(
                                existing_metadata.get("source_file_hashes"), parsed_issue.source_file_hashes, limit=50
                            ),
                            "import_provenance": provenance[:100],
                            "evidence_archive": evidence_archive,
                            "acceptance_criteria": parsed_issue.acceptance_criteria,
                            "root_cause": parsed_issue.root_cause,
                            "test_plan": parsed_issue.test_plan,
                            "linked_issue_refs": parsed_issue.linked_issue_refs,
                            "attachment_filenames": parsed_issue.attachment_filenames,
                            "comments_digest": build_comments_digest(parsed_issue.comments),
                            "components": canonical_component_names(
                                _union_values(
                                    existing_metadata.get("components"),
                                    list(enriched.components or []),
                                    limit=200,
                                )
                            ),
                            "company_names": _union_values(
                                existing_metadata.get("company_names"), parsed_issue.company_names, limit=100
                            ),
                            "customer_names": _trusted_csv_customer_names(
                                existing_metadata.get("customer_names"),
                                parsed_issue,
                            ),
                            "customer_cohorts": _union_values(
                                existing_metadata.get("customer_cohorts"), parsed_issue.customer_cohorts, limit=20
                            ),
                        }
                    )
                    chunks = build_jira_qa_chunks(
                        parsed_issue.issue_key,
                        parsed_issue.issue,
                        comments=parsed_issue.comments,
                        linked_issues=[],
                        enriched=enriched,
                    )
                    batch.append((parsed_issue, enriched, chunks))
                except Exception as exc:
                    failed += 1
                    errors.append(f"{parsed_issue.issue_key}: {exc}")
                processed += source_row_count
                if len(batch) >= 24:
                    flush()
                _set_run(
                    run_id,
                    processed_rows=processed,
                    indexed_issues=indexed,
                    skipped_issues=skipped,
                    metadata_merged_issues=metadata_merged,
                    failed_issues=failed,
                    chunks_indexed=chunks_indexed,
                    errors=errors[:100],
                )
        if batch:
            flush()
        affected_customers = sorted(
            {
                customer
                for issue in merged_issues
                for customer in issue.customer_cohorts
                if customer
            }
        )
        profile_rebuild: dict[str, Any] = {}
        if affected_customers and failed == 0:
            try:
                from app.services.jira_customer_profile_service import rebuild_customer_profiles

                profile_rebuild = rebuild_customer_profiles(affected_customers)
                profile_failures = [
                    customer
                    for customer, result in (profile_rebuild.get("profiles") or {}).items()
                    if result.get("status") != "completed"
                ]
                if profile_failures:
                    errors.append("Customer profile rebuild failed for: " + ", ".join(profile_failures))
                    failed += len(profile_failures)
            except Exception as exc:
                errors.append(f"Customer profile rebuild failed: {exc}")
                profile_rebuild = {"status": "failed", "error": str(exc)}
                failed += 1
        final_status = "completed" if failed == 0 else "completed_with_errors"
        _set_run(
            run_id,
            status=final_status,
            processed_rows=processed,
            indexed_issues=indexed,
            skipped_issues=skipped,
            metadata_merged_issues=metadata_merged,
            failed_issues=failed,
            chunks_indexed=chunks_indexed,
            errors=errors[:100],
            profile_rebuild=profile_rebuild,
            completed_at=datetime.utcnow(),
        )
    except Exception as exc:
        errors.append(str(exc))
        _set_run(run_id, status="failed", failed_issues=max(failed, 1), errors=errors[:100], completed_at=datetime.utcnow())
        logger.error_structured("jira_csv_import_failed", extra_fields={"import_id": run_id, "error": str(exc)})
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
        if import_dir and import_dir.exists():
            try:
                import_dir.rmdir()
            except OSError:
                pass


def start_import(run_id: str, paths: list[Path]) -> None:
    async def runner() -> None:
        await asyncio.to_thread(run_import, run_id, paths)

    task = asyncio.create_task(runner(), name=f"jira-csv-import-{run_id}")
    _RUN_TASKS.add(task)
    task.add_done_callback(_RUN_TASKS.discard)
