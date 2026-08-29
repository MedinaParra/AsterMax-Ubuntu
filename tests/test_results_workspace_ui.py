from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.results_workspace import build_professional_results_workspace, probe_result
from astermax.fea.results_workspace_ui import build_results_render_payload
from astermax.fea.solver import Tet10LinearStaticResult


def _fixture() -> tuple[np.ndarray, np.ndarray, Tet10LinearStaticResult]:
    nodes = np.asarray([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 10.0],
        [5.0, 0.0, 0.0],
        [5.0, 5.0, 0.0],
        [0.0, 5.0, 0.0],
        [0.0, 0.0, 5.0],
        [0.0, 5.0, 5.0],
        [5.0, 0.0, 5.0],
    ], dtype=float)
    elements = np.arange(10, dtype=np.int64).reshape((1, 10))
    displacement = np.zeros_like(nodes)
    displacement[:, 0] = np.linspace(0.0, 0.9, nodes.shape[0])
    stress = np.zeros((1, 4, 6), dtype=float)
    vm = np.asarray([[11.0, 22.0, 33.0, 44.0]], dtype=float)
    result = Tet10LinearStaticResult(displacement, np.zeros_like(nodes), stress, vm)
    return nodes, elements, result


def _workspace(nodes, elements, result, sha: str = "a" * 64):
    return build_professional_results_workspace(
        nodes,
        elements,
        result,
        solve_evidence_sha256=sha,
        deformation_scale=10.0,
    )


def test_u_magnitude_render_payload_preserves_workspace_and_deformed_semantics() -> None:
    nodes, elements, result = _fixture()
    workspace = _workspace(nodes, elements, result)
    payload = build_results_render_payload(workspace, nodes, elements, result, field="U_MAG")
    assert payload.schema == "AsterMaxResultsRenderPayloadV1"
    assert payload.workspace_sha256 == workspace.workspace_sha256
    assert payload.solve_evidence_sha256 == workspace.solve_evidence_sha256
    assert payload.field == "U_MAG"
    assert payload.unit == "mm"
    assert payload.value_min == pytest.approx(0.0)
    assert payload.value_max == pytest.approx(0.9)
    assert payload.deformation_scale == pytest.approx(10.0)
    assert len(payload.triangles) == 4
    assert len(payload.projected_nodes_xy) == nodes.shape[0]
    assert payload.projected_nodes_xy != payload.undeformed_nodes_xy


def test_von_mises_payload_uses_explicit_element_ip_max_without_nodal_smoothing() -> None:
    nodes, elements, result = _fixture()
    workspace = _workspace(nodes, elements, result, "b" * 64)
    payload = build_results_render_payload(
        workspace,
        nodes,
        elements,
        result,
        field="VON_MISES_IP_MAX",
        deformation_scale=0.0,
    )
    assert payload.unit == "MPa"
    assert payload.value_min == pytest.approx(44.0)
    assert payload.value_max == pytest.approx(44.0)
    assert {tri.value for tri in payload.triangles} == {44.0}
    assert payload.projected_nodes_xy == payload.undeformed_nodes_xy
    probe = probe_result(workspace, result, kind="VON_MISES_IP_MAX", entity_id=0)
    assert probe.value == pytest.approx(payload.triangles[0].value)


def test_render_payload_is_deterministic_and_scale_sensitive() -> None:
    nodes, elements, result = _fixture()
    workspace = _workspace(nodes, elements, result, "c" * 64)
    first = build_results_render_payload(workspace, nodes, elements, result, field="U_MAG", deformation_scale=5.0)
    second = build_results_render_payload(workspace, nodes, elements, result, field="U_MAG", deformation_scale=5.0)
    changed = build_results_render_payload(workspace, nodes, elements, result, field="U_MAG", deformation_scale=20.0)
    assert first == second
    assert first.projected_nodes_xy != changed.projected_nodes_xy
    assert first.workspace_sha256 == changed.workspace_sha256


def test_render_payload_fails_closed_on_stale_mesh_unknown_field_and_bad_scale() -> None:
    nodes, elements, result = _fixture()
    workspace = _workspace(nodes, elements, result, "d" * 64)
    with pytest.raises(ValueError, match="WORKSPACE_MESH_STALE"):
        build_results_render_payload(workspace, nodes[:-1], elements, result, field="U_MAG")
    with pytest.raises(ValueError, match="UNKNOWN_FIELD"):
        build_results_render_payload(workspace, nodes, elements, result, field="NODAL_STRESS")
    with pytest.raises(ValueError, match="DEFORMATION_SCALE"):
        build_results_render_payload(workspace, nodes, elements, result, field="U_MAG", deformation_scale=-1.0)
