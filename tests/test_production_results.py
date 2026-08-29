from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from astermax.fea.arbitrary_bc import ArbitraryBcSolveEvidence
from astermax.fea.production_results import (
    ProductionResultsError,
    build_production_results_bundle,
    production_results_metadata,
)
from astermax.fea.solver import Tet10LinearStaticResult


def _fixture():
    nodes = np.asarray([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        [0.5, 0.0, 0.0], [0.5, 0.5, 0.0], [0.0, 0.5, 0.0], [0.0, 0.0, 0.5],
        [0.0, 0.5, 0.5], [0.5, 0.0, 0.5],
    ], dtype=float)
    elements = np.arange(10, dtype=np.int64).reshape((1, 10))
    displacement = np.zeros_like(nodes)
    displacement[:, 0] = np.linspace(0.0, 0.09, nodes.shape[0])
    stress = np.zeros((1, 4, 6), dtype=float)
    vm = np.asarray([[10.0, 20.0, 30.0, 40.0]], dtype=float)
    result = Tet10LinearStaticResult(displacement, np.zeros_like(nodes), stress, vm)
    evidence = ArbitraryBcSolveEvidence(
        schema="AsterMaxArbitraryBcSolveEvidenceV1",
        preparation_sha256="1" * 64,
        support_binding_sha256="2" * 64,
        load_binding_sha256="3" * 64,
        resultant_n=(0.0, -1000.0, 0.0),
        fixed_node_count=6,
        force_residual_n=0.0,
        moment_residual_nmm=0.0,
        converged=False,
        industrial_validation=False,
        ansys_equivalence=False,
        solve_evidence_sha256="4" * 64,
    )
    return nodes, elements, result, evidence


def test_production_bundle_preserves_exact_solver_semantics_and_provenance() -> None:
    nodes, elements, result, evidence = _fixture()
    bundle, workspace, displacement, stress = build_production_results_bundle(
        nodes, elements, result, evidence, deformation_scale=25.0
    )
    assert bundle.solve_evidence_sha256 == evidence.solve_evidence_sha256
    assert bundle.workspace_sha256 == workspace.workspace_sha256
    assert displacement.solve_evidence_sha256 == evidence.solve_evidence_sha256
    assert stress.solve_evidence_sha256 == evidence.solve_evidence_sha256
    assert displacement.field == "U_MAG"
    assert stress.field == "VON_MISES_IP_MAX"
    assert bundle.displacement_value_max_mm == pytest.approx(0.09)
    assert bundle.von_mises_value_max_mpa == pytest.approx(40.0)
    assert "NO_NODAL_SMOOTHING" in bundle.stress_representation
    assert bundle.converged_claim is False
    assert bundle.industrial_validation_claim is False
    assert bundle.ansys_equivalence_claim is False
    assert len(bundle.bundle_sha256) == 64


def test_production_bundle_is_deterministic_and_solve_bound() -> None:
    nodes, elements, result, evidence = _fixture()
    first = build_production_results_bundle(nodes, elements, result, evidence)[0]
    second = build_production_results_bundle(nodes, elements, result, evidence)[0]
    changed_evidence = replace(evidence, solve_evidence_sha256="5" * 64)
    changed = build_production_results_bundle(nodes, elements, result, changed_evidence)[0]
    assert first.bundle_sha256 == second.bundle_sha256
    assert first.workspace_sha256 == second.workspace_sha256
    assert first.bundle_sha256 != changed.bundle_sha256
    assert first.workspace_sha256 != changed.workspace_sha256


def test_production_metadata_fails_closed_if_bundle_is_tampered() -> None:
    nodes, elements, result, evidence = _fixture()
    bundle = build_production_results_bundle(nodes, elements, result, evidence)[0]
    metadata = production_results_metadata(bundle)
    assert metadata["bundle_sha256"] == bundle.bundle_sha256
    with pytest.raises(ProductionResultsError, match="BUNDLE_SHA_MISMATCH"):
        production_results_metadata(replace(bundle, displacement_value_max_mm=999.0))


def test_production_bundle_refuses_unverified_or_false_claim_evidence() -> None:
    nodes, elements, result, evidence = _fixture()
    with pytest.raises(ProductionResultsError, match="SOLVE_EVIDENCE_REQUIRED"):
        build_production_results_bundle(nodes, elements, result, object())
    with pytest.raises(ProductionResultsError, match="FALSE_CLAIM_REFUSED"):
        build_production_results_bundle(nodes, elements, result, replace(evidence, converged=True))
    with pytest.raises(ProductionResultsError, match="FALSE_CLAIM_REFUSED"):
        build_production_results_bundle(nodes, elements, result, replace(evidence, industrial_validation=True))
    with pytest.raises(ProductionResultsError, match="FALSE_CLAIM_REFUSED"):
        build_production_results_bundle(nodes, elements, result, replace(evidence, ansys_equivalence=True))
    with pytest.raises(ProductionResultsError, match="SOLVE_SHA_INVALID"):
        build_production_results_bundle(nodes, elements, result, replace(evidence, solve_evidence_sha256="bad"))


def test_production_bundle_rejects_stale_mesh_result_pairing() -> None:
    nodes, elements, result, evidence = _fixture()
    with pytest.raises(ValueError, match="RESULTS_WORKSPACE_DISPLACEMENT_SHAPE"):
        build_production_results_bundle(nodes[:-1], elements, result, evidence)
