from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pytest

from astermax.code_aster_mesh_attestation import (
    CodeAsterMeshAttestationError,
    attest_reference_mesh_before_solve,
)
from astermax.code_aster_mesh_quality_gate import build_tet10_presolve_quality_report
from astermax.fea.tet10 import straight_sided_tet10_from_vertices


def _write_case(root: Path):
    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0]]
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    tet10 = np.arange(10, dtype=int).reshape((1, 10))
    quality = build_tet10_presolve_quality_report(nodes, tet10)
    quality_path = root / "reference_mesh_quality.json"
    quality_path.write_text(json.dumps(quality.as_dict(), indent=2, sort_keys=True), encoding="utf-8")

    med = root / "astermax.med"
    med.write_bytes(b"MED-quality-gated-witness")
    case = {
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "mesh_quality_gate_passed": True,
        "mesh_quality_report_sha256": quality.report_sha256,
        "mesh_quality_artifact_sha256": sha256(quality_path.read_bytes()).hexdigest(),
        "med_sha256": sha256(med.read_bytes()).hexdigest(),
        "fea_solve_executed": False,
        "numerical_verification": False,
        "results_verified": False,
    }
    (root / "reference_case_evidence.json").write_text(json.dumps(case, indent=2, sort_keys=True), encoding="utf-8")


def test_exact_quality_gated_med_is_attested_without_solver_claims(tmp_path: Path):
    _write_case(tmp_path)
    ev = attest_reference_mesh_before_solve(tmp_path)
    assert ev.mesh_attested_immediately_before_solve is True
    assert ev.mesh_quality_gate_passed is True
    assert ev.all_sampled_jacobians_positive is True
    assert ev.length_unit == "mm"
    assert ev.solver_unit_system == "mm-N-MPa"
    assert ev.fea_solve_executed is False
    assert ev.numerical_verification is False
    assert ev.results_verified is False
    assert ev.industrial_validation is False
    assert ev.ansys_equivalence is False


def test_med_mutation_after_quality_gate_fails_closed(tmp_path: Path):
    _write_case(tmp_path)
    (tmp_path / "astermax.med").write_bytes(b"changed-after-quality-gate")
    with pytest.raises(CodeAsterMeshAttestationError, match="MED_HASH_MISMATCH"):
        attest_reference_mesh_before_solve(tmp_path)


def test_quality_artifact_mutation_fails_closed(tmp_path: Path):
    _write_case(tmp_path)
    path = tmp_path / "reference_mesh_quality.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["minimum_sampled_jacobian_ratio"] = 0.123
    path.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
    with pytest.raises(CodeAsterMeshAttestationError, match="CANONICAL_HASH_MISMATCH|ARTIFACT_HASH_MISMATCH"):
        attest_reference_mesh_before_solve(tmp_path)


def test_case_evidence_cannot_promote_solver_claims(tmp_path: Path):
    _write_case(tmp_path)
    path = tmp_path / "reference_case_evidence.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["fea_solve_executed"] = True
    path.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
    with pytest.raises(CodeAsterMeshAttestationError, match="CASE_FEA_SOLVE_EXECUTED_CLAIM_FORBIDDEN"):
        attest_reference_mesh_before_solve(tmp_path)


def test_ansys_metric_equivalence_promotion_in_quality_artifact_is_rejected(tmp_path: Path):
    _write_case(tmp_path)
    path = tmp_path / "reference_mesh_quality.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["ansys_metric_equivalence"] = True
    path.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
    with pytest.raises(CodeAsterMeshAttestationError, match="ANSYS_EQUIVALENCE_CLAIM_FORBIDDEN"):
        attest_reference_mesh_before_solve(tmp_path)
