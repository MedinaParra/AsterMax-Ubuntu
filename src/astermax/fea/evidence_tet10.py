from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

import numpy as np

from .evidence import (
    AnalysisEvidenceManifest,
    EvidenceArtifact,
    canonical_sha256,
    sha256_bytes,
    sha256_file,
)


def mesh_fingerprint_tet10(nodes_mm: np.ndarray, elements: np.ndarray) -> str:
    """Binary fingerprint for a Gmsh-order TET10 mesh in millimetres."""
    nodes = np.asarray(nodes_mm, dtype="<f8")
    elems = np.asarray(elements, dtype="<i8")
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10) for TET10")
    if not np.all(np.isfinite(nodes)):
        raise ValueError("mesh coordinates must be finite")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contains an out-of-range node index")
    header = json.dumps(
        {
            "schema": "AsterMaxMeshFingerprintV2",
            "nodes_shape": list(nodes.shape),
            "elements_shape": list(elems.shape),
            "coordinate_dtype": "float64-little-endian",
            "connectivity_dtype": "int64-little-endian",
            "units": "mm",
            "element": "TET10_GMSH_TYPE_11",
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(header + b"\0" + nodes.tobytes(order="C") + b"\0" + elems.tobytes(order="C"))


def _artifact(root: Path, path: str | Path, role: str) -> EvidenceArtifact:
    resolved_root = root.resolve()
    resolved_path = (root / Path(path)).resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("evidence artifact must be inside package_dir") from exc
    if not resolved_path.is_file():
        raise ValueError(f"missing evidence artifact: {relative}")
    return EvidenceArtifact(
        role=str(role),
        relative_path=relative.as_posix(),
        sha256=sha256_file(resolved_path),
        size_bytes=int(resolved_path.stat().st_size),
    )


def _source_record(root: Path, source_path: str | Path) -> dict[str, Any]:
    source = Path(source_path).resolve()
    try:
        relative = source.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("source STEP must be staged inside package_dir") from exc
    if not source.is_file():
        raise ValueError("source STEP must exist")
    if source.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("TET10 evidence source must be STEP/STP")
    return {
        "kind": "STEP_CAD_SOURCE",
        "path": relative.as_posix(),
        "sha256": sha256_file(source),
        "size_bytes": int(source.stat().st_size),
    }


def write_tet10_analysis_evidence_manifest(
    package_dir: str | Path,
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    analysis_definition: dict[str, Any],
    solver_identity: dict[str, Any],
    convergence_evidence: dict[str, Any],
    artifacts: list[tuple[str | Path, str]],
    source_path: str | Path,
    classification: str = "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
    converged_claim: bool = False,
    industrial_validation_claim: bool = False,
    ansys_equivalence_claim: bool = False,
) -> AnalysisEvidenceManifest:
    """Write a tamper-evident STEP -> TET10 -> solve -> viewer evidence chain.

    ``converged_claim`` may only be true when the supplied convergence evidence
    itself contains a true convergence decision.  Industrial validation and
    ANSYS-equivalence remain independent claims and default to false.
    """
    root = Path(package_dir)
    root.mkdir(parents=True, exist_ok=True)
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)

    decision = convergence_evidence.get("convergence_decision", {})
    evidence_converged = bool(decision.get("converged", convergence_evidence.get("converged_claim", False)))
    if converged_claim and not evidence_converged:
        raise ValueError("converged_claim cannot be true when convergence evidence is not converged")
    if industrial_validation_claim:
        raise ValueError("industrial_validation_claim is outside the current T10-C verification scope")
    if ansys_equivalence_claim:
        raise ValueError("ansys_equivalence_claim is outside the current T10-C verification scope")

    source = _source_record(root, source_path)
    artifact_records = [_artifact(root, path, role) for path, role in artifacts]
    if len({item.relative_path for item in artifact_records}) != len(artifact_records):
        raise ValueError("artifact paths must be unique")
    if len({item.role for item in artifact_records}) != len(artifact_records):
        raise ValueError("artifact roles must be unique")

    mesh_hash = mesh_fingerprint_tet10(nodes, elems)
    analysis_hash = canonical_sha256(analysis_definition)
    solver_hash = canonical_sha256(solver_identity)
    convergence_hash = canonical_sha256(convergence_evidence)
    claims = {
        "converged": bool(converged_claim),
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    chain_payload = {
        "schema_version": "AsterMaxAnalysisEvidenceTET10V1",
        "classification": str(classification),
        "analysis_type": "LINEAR_STATIC_3D_TET10",
        "units": {"length": "mm", "force": "N", "stress": "MPa", "moment": "N*mm"},
        "source": source,
        "mesh": {
            "fingerprint_sha256": mesh_hash,
            "nodes": int(nodes.shape[0]),
            "tet10": int(elems.shape[0]),
            "gmsh_element_type": 11,
            "vtk_cell_type": 24,
        },
        "analysis_definition": {
            "sha256": analysis_hash,
            "canonical": analysis_definition,
        },
        "solver": {
            "sha256": solver_hash,
            "identity": solver_identity,
        },
        "convergence": {
            "sha256": convergence_hash,
            "evidence": convergence_evidence,
        },
        "stress_policy": {
            "location": "FOUR_TET10_INTEGRATION_POINTS",
            "nodal_smoothing": False,
            "viewer_summary_fields": ["VON_MISES_IP_MAX_MPa", "VON_MISES_IP_MEAN_MPa"],
        },
        "claims": claims,
        "artifacts": [asdict(item) for item in artifact_records],
    }
    chain_hash = canonical_sha256(chain_payload)
    manifest = AnalysisEvidenceManifest(
        schema_version=chain_payload["schema_version"],
        classification=chain_payload["classification"],
        analysis_type=chain_payload["analysis_type"],
        units=chain_payload["units"],
        source=source,
        mesh=chain_payload["mesh"],
        analysis_definition=chain_payload["analysis_definition"],
        solver={
            **chain_payload["solver"],
            "convergence": chain_payload["convergence"],
            "stress_policy": chain_payload["stress_policy"],
        },
        claims=claims,
        artifacts=artifact_records,
        chain_sha256=chain_hash,
    )

    # AnalysisEvidenceManifest does not have dedicated convergence/stress-policy
    # fields.  Write the exact chain payload directly so verification hashes the
    # complete T10-C contract rather than the compatibility dataclass projection.
    output = {**chain_payload, "chain_sha256": chain_hash}
    (root / "analysis_evidence.json").write_text(
        json.dumps(output, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest
