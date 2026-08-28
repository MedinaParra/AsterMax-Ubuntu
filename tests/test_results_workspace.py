from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.results_workspace import (
    build_professional_results_workspace,
    deformed_coordinates_mm,
    probe_result,
    workspace_to_json,
)
from astermax.fea.solver import Tet10LinearStaticResult


def _fixture() -> tuple[np.ndarray, np.ndarray, Tet10LinearStaticResult]:
    nodes = np.asarray([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        [0.5, 0.0, 0.0], [0.5, 0.5, 0.0], [0.0, 0.5, 0.0], [0.0, 0.0, 0.5],
        [0.0, 0.5, 0.5], [0.5, 0.0, 0.5],
    ])
    elements = np.arange(10, dtype=np.int64).reshape((1, 10))
    displacement = np.zeros_like(nodes)
    displacement[:, 0] = np.linspace(0.0, 0.09, nodes.shape[0])
    stress = np.zeros((1, 4, 6), dtype=float)
    vm = np.asarray([[10.0, 20.0, 30.0, 40.0]])
    result = Tet10LinearStaticResult(displacement, np.zeros_like(nodes), stress, vm)
    return nodes, elements, result


def test_workspace_preserves_solver_field_semantics_and_provenance() -> None:
    nodes, elements, result = _fixture()
    solve_sha = "a" * 64
    workspace = build_professional_results_workspace(
        nodes, elements, result, solve_evidence_sha256=solve_sha, deformation_scale=25.0
    )
    assert workspace.solve_evidence_sha256 == solve_sha
    assert workspace.node_count == 10
    assert workspace.tet10_count == 1
    assert workspace.displacement_max_mm == pytest.approx(0.09)
    assert workspace.von_mises_ip_max_max_mpa == pytest.approx(40.0)
    assert workspace.max_displacement_node_id == 9
    assert workspace.max_von_mises_element_id == 0
    assert "NO_NODAL_SMOOTHING" in workspace.stress_representation
    assert workspace.industrial_validation_claim is False
    assert workspace.ansys_equivalence_claim is False
    assert len(workspace.workspace_sha256) == 64
    assert '"solve_evidence_sha256": "' + solve_sha + '"' in workspace_to_json(workspace)


def test_deformed_overlay_is_exact_nodes_plus_scaled_solver_displacement() -> None:
    nodes, _, result = _fixture()
    deformed = deformed_coordinates_mm(nodes, result, 10.0)
    np.testing.assert_allclose(deformed, nodes + 10.0 * result.displacement_mm)
    np.testing.assert_allclose(deformed_coordinates_mm(nodes, result, 0.0), nodes)


def test_probe_reads_solver_values_without_interpolation_or_smoothing() -> None:
    nodes, elements, result = _fixture()
    workspace = build_professional_results_workspace(nodes, elements, result, solve_evidence_sha256="b" * 64)
    u = probe_result(workspace, result, kind="U_MAG", entity_id=9)
    vm = probe_result(workspace, result, kind="VON_MISES_IP_MAX", entity_id=0)
    assert u.value == pytest.approx(0.09)
    assert u.unit == "mm"
    assert vm.value == pytest.approx(40.0)
    assert vm.unit == "MPa"


def test_workspace_is_deterministic_and_bound_to_solve_evidence() -> None:
    nodes, elements, result = _fixture()
    first = build_professional_results_workspace(nodes, elements, result, solve_evidence_sha256="c" * 64)
    second = build_professional_results_workspace(nodes, elements, result, solve_evidence_sha256="c" * 64)
    changed = build_professional_results_workspace(nodes, elements, result, solve_evidence_sha256="d" * 64)
    assert first.workspace_sha256 == second.workspace_sha256
    assert first.workspace_sha256 != changed.workspace_sha256


def test_workspace_refuses_false_professional_claims_and_bad_fields() -> None:
    nodes, elements, result = _fixture()
    with pytest.raises(ValueError, match="INDUSTRIAL_CLAIM_REFUSED"):
        build_professional_results_workspace(nodes, elements, result, solve_evidence_sha256="e" * 64, industrial_validation_claim=True)
    with pytest.raises(ValueError, match="ANSYS_EQUIVALENCE_REFUSED"):
        build_professional_results_workspace(nodes, elements, result, solve_evidence_sha256="e" * 64, ansys_equivalence_claim=True)
    with pytest.raises(ValueError, match="SOLVE_EVIDENCE_REQUIRED"):
        build_professional_results_workspace(nodes, elements, result, solve_evidence_sha256="missing")
    with pytest.raises(ValueError, match="UNKNOWN_PROBE"):
        workspace = build_professional_results_workspace(nodes, elements, result, solve_evidence_sha256="f" * 64)
        probe_result(workspace, result, kind="NODAL_STRESS", entity_id=0)
