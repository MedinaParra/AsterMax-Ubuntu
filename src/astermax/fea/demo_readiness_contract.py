from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


REQUIRED_DEMO_STAGES = (
    "CAD_IMPORT",
    "MODEL_PREP",
    "MESH",
    "SETUP",
    "SOLVE",
    "RESULTS",
    "SECTION",
    "PROBE",
    "EVIDENCE",
)


@dataclass(frozen=True)
class DemoStageEvidenceV1:
    stage: str
    status: str
    workspace_sha256: str
    evidence_sha256: str
    parent_evidence_sha256: str | None
    length_unit: str
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class DemoReadinessManifestV1:
    schema: str
    semantics: str
    status: str
    workspace_sha256: str
    length_unit: str
    blockers: tuple[str, ...]
    stage_count: int
    completed_stage_count: int
    terminal_evidence_sha256: str
    manifest_sha256: str
    stages: tuple[DemoStageEvidenceV1, ...]


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validate_token(value: str, code: str) -> str:
    token = str(value).strip()
    if not token:
        raise ValueError(code)
    return token


def build_demo_readiness_manifest(
    stages: tuple[DemoStageEvidenceV1, ...] | list[DemoStageEvidenceV1],
    *,
    expected_workspace_sha256: str,
) -> DemoReadinessManifestV1:
    """Gate the Windows PMV demo on a complete, provenance-closed evidence chain.

    This function does not run CAD import, meshing, solving, stress recovery or any
    synthetic simulation. It only verifies that evidence produced by those stages is
    complete, ordered, millimetre-consistent and connected by explicit identities.
    A broken or incomplete chain fails closed and cannot be advertised as demo-ready.
    """
    expected_workspace = _validate_token(expected_workspace_sha256, "DEMO_WORKSPACE_REQUIRED")
    supplied = tuple(stages)
    blockers: list[str] = []

    by_stage: dict[str, DemoStageEvidenceV1] = {}
    for item in supplied:
        stage = str(item.stage).strip().upper()
        if stage in by_stage:
            blockers.append(f"DUPLICATE_STAGE:{stage}")
            continue
        by_stage[stage] = item

    ordered: list[DemoStageEvidenceV1] = []
    previous_sha: str | None = None
    for stage_name in REQUIRED_DEMO_STAGES:
        item = by_stage.get(stage_name)
        if item is None:
            blockers.append(f"MISSING_STAGE:{stage_name}")
            previous_sha = None
            continue

        ordered.append(item)
        workspace = str(item.workspace_sha256).strip()
        evidence_sha = str(item.evidence_sha256).strip()
        parent_sha = None if item.parent_evidence_sha256 is None else str(item.parent_evidence_sha256).strip()
        status = str(item.status).strip().upper()
        length_unit = str(item.length_unit).strip().lower()

        if workspace != expected_workspace:
            blockers.append(f"WORKSPACE_MISMATCH:{stage_name}")
        if not evidence_sha:
            blockers.append(f"MISSING_EVIDENCE_SHA:{stage_name}")
        if status != "READY":
            blockers.append(f"STAGE_NOT_READY:{stage_name}")
        if item.blockers:
            blockers.append(f"STAGE_HAS_BLOCKERS:{stage_name}")
        if length_unit != "mm":
            blockers.append(f"LENGTH_UNIT_NOT_MM:{stage_name}")

        if stage_name == REQUIRED_DEMO_STAGES[0]:
            if parent_sha not in (None, ""):
                blockers.append("CAD_IMPORT_UNEXPECTED_PARENT")
        else:
            if previous_sha is None or parent_sha != previous_sha:
                blockers.append(f"BROKEN_EVIDENCE_CHAIN:{stage_name}")
        previous_sha = evidence_sha or None

    unexpected = sorted(set(by_stage).difference(REQUIRED_DEMO_STAGES))
    if unexpected:
        blockers.append("UNEXPECTED_STAGES:" + ",".join(unexpected))

    unique_evidence = [str(item.evidence_sha256).strip() for item in ordered if str(item.evidence_sha256).strip()]
    if len(unique_evidence) != len(set(unique_evidence)):
        blockers.append("DUPLICATE_EVIDENCE_IDENTITY")

    status = "READY" if not blockers and len(ordered) == len(REQUIRED_DEMO_STAGES) else "BLOCKED"
    terminal_sha = ordered[-1].evidence_sha256 if status == "READY" and ordered else ""
    identity = {
        "schema": "AsterMaxDemoReadinessManifestV1",
        "semantics": "windows_pmv_end_to_end_evidence_chain_fail_closed",
        "workspace_sha256": expected_workspace,
        "length_unit": "mm",
        "status": status,
        "blockers": blockers,
        "required_stages": list(REQUIRED_DEMO_STAGES),
        "stages": [
            {
                "stage": str(item.stage).strip().upper(),
                "status": str(item.status).strip().upper(),
                "workspace_sha256": str(item.workspace_sha256).strip(),
                "evidence_sha256": str(item.evidence_sha256).strip(),
                "parent_evidence_sha256": item.parent_evidence_sha256,
                "length_unit": str(item.length_unit).strip().lower(),
                "blockers": list(item.blockers),
            }
            for item in ordered
        ],
    }
    return DemoReadinessManifestV1(
        schema="AsterMaxDemoReadinessManifestV1",
        semantics="windows_pmv_end_to_end_evidence_chain_fail_closed",
        status=status,
        workspace_sha256=expected_workspace,
        length_unit="mm",
        blockers=tuple(blockers),
        stage_count=len(REQUIRED_DEMO_STAGES),
        completed_stage_count=sum(1 for item in ordered if str(item.status).strip().upper() == "READY" and not item.blockers),
        terminal_evidence_sha256=str(terminal_sha),
        manifest_sha256=_sha256_json(identity),
        stages=tuple(ordered),
    )
