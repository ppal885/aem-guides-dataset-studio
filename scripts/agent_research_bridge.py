#!/usr/bin/env python3
"""A5 host bridge: the mechanical handoff between the canonical runtime's
pending agent-research requests and the Copilot host's delegated agents.

The canonical runtime (AGENT_RESEARCH_MODE=copilot_host) emits pending
AgentResearchRequest files and returns waiting_for_agent_research.  The
Copilot coordinator (the Test Plan Generation skill running in the host)
lists them here, delegates each to the registered custom agent
(.github/agents/*.agent.md) using Copilot's own model access, and submits
the agent's strict ResearchWorkerResult back through `fulfill`, which
validates the resume envelope before the runtime may consume it.

Usage:
  python scripts/agent_research_bridge.py pending [--store PATH]
  python scripts/agent_research_bridge.py fulfill --envelope FILE.json [--store PATH]
  python scripts/agent_research_bridge.py fulfill-agent --execution-id ID --result FILE.json --model MODEL [--store PATH]
  python scripts/agent_research_bridge.py status [--store PATH]

`fulfill-agent` is the coordinator's normal path: the delegated agent returns
only its strict ResearchWorkerResult object and reports the model that ran;
identity fields and the role-contract version come from the emitted pending
request and the canonical contract, never from agent-supplied text.

No model execution happens in this script; it is plumbing only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.agent_execution_provider import (  # noqa: E402
    agent_research_store,
    load_role_contract,
    validate_agent_result_shape,
)

_ROLE_BY_NAME = {
    # Accept both the registration name and the schema enum name: emitted
    # pending requests carry the enum value.
    "uac-doc-researcher": "DOC_RESEARCHER",
    "uac-code-researcher": "CODE_RESEARCHER",
    "uac-attachment-researcher": "ATTACHMENT_RESEARCHER",
    "DOC_RESEARCHER": "DOC_RESEARCHER",
    "CODE_RESEARCHER": "CODE_RESEARCHER",
    "ATTACHMENT_RESEARCHER": "ATTACHMENT_RESEARCHER",
}


def _pending_dir(store: Path) -> Path:
    return store / "pending"


def _fulfilled_dir(store: Path) -> Path:
    return store / "fulfilled"


def cmd_pending(store: Path, run_scope: str | None = None) -> int:
    pending = _pending_dir(store)
    rows = []
    if pending.is_dir():
        for path in sorted(pending.glob("*.json")):
            try:
                request = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if run_scope is not None and str(
                request.get("run_scope") or ""
            ) != run_scope:
                continue
            fulfilled = _fulfilled_dir(store) / path.name
            rows.append(
                {
                    "execution_id": request.get("execution_id"),
                    "run_scope": request.get("run_scope") or "",
                    "logical_execution_key": request.get(
                        "logical_execution_key"
                    ),
                    "worker_role": request.get("worker_role"),
                    "question_id": request.get("question_id"),
                    "question_revision": request.get("question_revision"),
                    "requested_claim": request.get("requested_claim"),
                    "research_requirement": request.get("research_requirement"),
                    "required_source_types": request.get(
                        "required_source_types"
                    )
                    or [],
                    "product_context": request.get("product_context") or {},
                    "research_terms": request.get("research_terms") or [],
                    "authorized_source_refs": request.get(
                        "authorized_source_refs"
                    ),
                    "authorized_evidence": request.get("authorized_evidence")
                    or [],
                    "authorized_repository_roots": request.get(
                        "authorized_repository_roots"
                    )
                    or [],
                    "attachment_files": request.get("attachment_files") or [],
                    "documentation_roots": request.get("documentation_roots")
                    or [],
                    "documentation_queries": request.get(
                        "documentation_queries"
                    )
                    or [],
                    "rag_candidates": request.get("rag_candidates") or [],
                    "rag_status": request.get("rag_status") or "",
                    "applicability": request.get("applicability"),
                    "fulfilled": fulfilled.exists(),
                    "consumed": fulfilled.with_suffix(".consumed").exists(),
                }
            )
    print(json.dumps(rows, indent=1))
    return 0


def cmd_fulfill(store: Path, envelope_path: Path) -> int:
    """Validate and accept a host agent's result envelope.

    The envelope must carry the resume contract fields and match an emitted
    pending request exactly; anything else fails closed.
    """

    try:
        envelope = json.loads(envelope_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"ERROR: envelope is not readable JSON: {exc}")
        return 1
    if not isinstance(envelope, dict):
        print("ERROR: envelope is not a JSON object")
        return 1
    execution_id = str(envelope.get("execution_id") or "")
    if not execution_id:
        print("ERROR: envelope lacks execution_id")
        return 1
    pending = _pending_dir(store) / f"{execution_id.replace(':', '_')}.json"
    if not pending.exists():
        print(f"ERROR: unknown execution - no pending request for {execution_id}")
        return 1
    request = json.loads(pending.read_text(encoding="utf-8-sig"))
    checks = {
        "question_id": envelope.get("question_id") == request.get("question_id"),
        "worker_role": envelope.get("worker_role") == request.get("worker_role"),
        "provider": envelope.get("provider") == "COPILOT_HOST",
        "question_revision": (
            not request.get("question_revision")
            or envelope.get("question_revision")
            == request.get("question_revision")
        ),
        "role_contract_version": bool(
            str(envelope.get("role_contract_version") or "").strip()
        ),
        "model": bool(str(envelope.get("model") or "").strip()),
        "result": isinstance(envelope.get("result"), dict),
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        print(f"ERROR: resume envelope failed validation: {', '.join(failed)}")
        return 1
    target = _fulfilled_dir(store) / pending.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        print(f"ERROR: duplicate result for {execution_id}")
        return 1
    target.write_text(
        json.dumps(envelope, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"FULFILLED {execution_id}")
    return 0


def _admission_rejection(request: dict, result: dict) -> str | None:
    """Run the provider's consumption-time admission against an emitted
    request, so fulfilment fails on exactly what consumption would reject.

    The emitted request already carries everything admission reads from the
    canonical bundle - the authorized evidence ids and their source types -
    so it is reconstructed here instead of re-deriving the bundle.  Returns a
    rejection reason, or None when the result is admissible.
    """

    from app.core.schemas_canonical_test_plan_runtime import (
        AgentResearchRequest,
        ResearchWorkerStatus,
    )
    from app.services.agent_execution_provider import _validate_agent_result

    class _Record:
        def __init__(self, evidence_id: str, source_type: object) -> None:
            self.evidence_id = evidence_id
            self.source_type = source_type

    class _Bundle:
        def __init__(self, records: list) -> None:
            self.records = records

    from app.core.schemas_canonical_test_plan_runtime import EvidenceSourceType

    records = []
    for row in request.get("authorized_evidence") or []:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("source_ref") or "").strip()
        if not evidence_id:
            continue
        try:
            source_type = EvidenceSourceType(str(row.get("source_type") or ""))
        except ValueError:
            continue
        records.append(_Record(evidence_id, source_type))

    request_fields = set(AgentResearchRequest.model_fields)
    try:
        typed_request = AgentResearchRequest(
            **{k: v for k, v in request.items() if k in request_fields}
        )
    except Exception as exc:  # pragma: no cover - malformed pending payload
        return f"emitted request is not readable: {exc}"

    roots = [
        str(root).strip()
        for root in (request.get("authorized_repository_roots") or [])
        if str(root).strip()
    ]
    verdict = _validate_agent_result(
        typed_request,
        result,
        _Bundle(records),
        repository_roots=roots or None,
    )
    if verdict.status == ResearchWorkerStatus.FAILED:
        return "; ".join(verdict.limitations) or "admission rejected the result"
    return None


def cmd_fulfill_agent(
    store: Path, execution_id: str, result_path: Path, model: str
) -> int:
    """Wrap a delegated agent's raw ResearchWorkerResult into a validated
    resume envelope.  The coordinator supplies only what the agent itself
    produced (the result object and the model that ran); every identity
    field is taken from the emitted pending request so a mismatched or
    fabricated identity fails closed here instead of at resume."""

    from app.core.schemas_canonical_test_plan_runtime import (
        HostAgentResultEnvelope,
        ResearchWorkerRole,
    )

    pending = _pending_dir(store) / f"{execution_id.replace(':', '_')}.json"
    if not pending.exists():
        print(f"ERROR: unknown execution - no pending request for {execution_id}")
        return 1
    request = json.loads(pending.read_text(encoding="utf-8-sig"))
    try:
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"ERROR: result is not readable JSON: {exc}")
        return 1
    if not isinstance(result, dict):
        print("ERROR: result is not a JSON object")
        return 1
    if not str(model or "").strip():
        print("ERROR: --model is required (the model the agent reported)")
        return 1
    role_name = str(request.get("worker_role") or "")
    if role_name not in _ROLE_BY_NAME:
        print(f"ERROR: pending request has unknown worker_role {role_name!r}")
        return 1
    try:
        contract_name, version, _text = load_role_contract(
            ResearchWorkerRole(_ROLE_BY_NAME[role_name])
        )
    except Exception as exc:
        print(f"ERROR: canonical role contract unavailable: {exc}")
        return 1
    # Same canonical result schema as the provider's resume validation:
    # reject shape/vocabulary/encoding violations NOW so the coordinator can
    # ask the agent to resend, instead of discovering rejection at resume.
    shape_rejection = validate_agent_result_shape(
        result, ResearchWorkerRole(_ROLE_BY_NAME[role_name])
    )
    if shape_rejection is not None:
        print(f"ERROR: result failed canonical shape validation: {shape_rejection}")
        return 1
    # Shape alone is not what the runtime admits on.  Consumption additionally
    # checks source membership, discovered-source provenance and (for code)
    # repository/path/revision.  Running only the shape subset here let a
    # result be recorded FULFILLED and then be discarded wholesale at
    # consumption, where the loss surfaces as SOURCE_UNAVAILABLE on the
    # question rather than as a fixable complaint about the result - so the
    # coordinator never learned there was anything to resend.  Run the same
    # admission now, reconstructed from the emitted request.
    admission_rejection = _admission_rejection(request, result)
    if admission_rejection is not None:
        print(f"ERROR: result failed canonical admission: {admission_rejection}")
        return 1
    # Same identity rule as the provider: the contract version is the one
    # bound into the emitted request (fall back to the current canonical
    # contract only for legacy pendings emitted before the binding existed).
    contract_version = str(
        request.get("role_contract_version") or f"{contract_name}@{version}"
    )
    # Canonical envelope: the host attaches identity + receipts; the leaf's
    # payload rides unmodified in `result`.  Construction validates the
    # schema (extra fields forbidden, provider literal, version shape).
    try:
        envelope_model = HostAgentResultEnvelope(
            execution_id=execution_id,
            question_id=str(request.get("question_id") or ""),
            question_revision=str(request.get("question_revision") or ""),
            worker_role=ResearchWorkerRole(_ROLE_BY_NAME[role_name]),
            provider="COPILOT_HOST",
            model=str(model).strip(),
            role_contract_version=contract_version,
            result=result,
        )
    except Exception as exc:
        print(f"ERROR: envelope failed the canonical schema: {exc}")
        return 1
    envelope = envelope_model.model_dump(mode="json")
    envelope_path = _fulfilled_dir(store) / f".tmp-{pending.name}"
    envelope_path.parent.mkdir(parents=True, exist_ok=True)
    envelope_path.write_text(
        json.dumps(envelope, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    outcome = cmd_fulfill(store, envelope_path)
    envelope_path.unlink(missing_ok=True)
    return outcome


def cmd_status(store: Path) -> int:
    pending = _pending_dir(store)
    fulfilled = _fulfilled_dir(store)
    pending_n = len(list(pending.glob("*.json"))) if pending.is_dir() else 0
    fulfilled_n = len(list(fulfilled.glob("*.json"))) if fulfilled.is_dir() else 0
    consumed_n = (
        len(list(fulfilled.glob("*.consumed"))) if fulfilled.is_dir() else 0
    )
    # G1: run-scope breakdown so repeated runs of the same Jira are visibly
    # distinct episodes; legacy pre-G1 pendings report an empty scope.
    scopes: dict[str, dict[str, int]] = {}
    if pending.is_dir():
        for path in sorted(pending.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            scope = str(payload.get("run_scope") or "(legacy)")
            row = scopes.setdefault(scope, {"pending": 0, "consumed": 0})
            row["pending"] += 1
            if (
                fulfilled.is_dir()
                and (fulfilled / path.name).with_suffix(".consumed").exists()
            ):
                row["consumed"] += 1
    print(
        json.dumps(
            {
                "store": str(store),
                "pending": pending_n,
                "fulfilled": fulfilled_n,
                "consumed": consumed_n,
                "remaining": pending_n - consumed_n,
                "run_scopes": scopes,
            },
            indent=1,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["pending", "fulfill", "fulfill-agent", "status"]
    )
    parser.add_argument("--store", default=None)
    parser.add_argument("--envelope", default=None)
    parser.add_argument("--execution-id", default=None)
    parser.add_argument("--result", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--run-scope",
        default=None,
        help="pending only: list just the named run scope's requests",
    )
    args = parser.parse_args()
    store = Path(args.store) if args.store else agent_research_store()
    if args.command == "pending":
        return cmd_pending(store, run_scope=args.run_scope)
    if args.command == "status":
        return cmd_status(store)
    if args.command == "fulfill-agent":
        if not args.execution_id or not args.result:
            print("ERROR: fulfill-agent requires --execution-id and --result")
            return 1
        return cmd_fulfill_agent(
            store, args.execution_id, Path(args.result), args.model
        )
    if not args.envelope:
        print("ERROR: fulfill requires --envelope")
        return 1
    return cmd_fulfill(store, Path(args.envelope))


if __name__ == "__main__":
    sys.exit(main())
