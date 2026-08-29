from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.results_clip import build_clipped_results_render_payload
from astermax.fea.results_workspace import build_professional_results_workspace
from astermax.fea.solver import Tet10LinearStaticResult


def _fixture():
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
    stress = np.zeros((1, 4, 6), dtype=float)
    vm = np.asarray([[11.0, 22.0, 33.0, 44.0]], dtype=float)
    result = Tet10LinearStaticResult(displacement, np.zeros_like(nodes), stress, vm)
    workspace = build_professional_results_workspace(
        nodes,
        elements,
        result,
        solve_evidence_sha256="a" * 64,
        deformation_scale=0.0,
    )
    return nodes, elements, result, workspace


def test_clip_plane_is_deterministic_and_provenance_bound() -> None:
    nodes, elements, result, workspace = _fixture()
    first = build_clipped_results_render_payload(
        workspace, nodes, elements, result,
        field="VON_MISES_IP_MAX",
        plane_origin_mm=(2.0, 0.0, 0.0),
        plane_normal=(2.0, 0.0, 0.0),
        keep_side="POSITIVE",
    )
    second = build_clipped_results_render_payload(
        workspace, nodes, elements, result,
        field="VON_MISES_IP_MAX",
        plane_origin_mm=(2.0, 0.0, 0.0),
        plane_normal=(1.0, 0.0, 0.0),
        keep_side="POSITIVE",
    )
    assert first == second
    assert first.clip_plane.workspace_sha256 == workspace.workspace_sha256
    assert first.clip_plane.solve_evidence_sha256 == workspace.solve_evidence_sha256
    assert first.clip_plane.normal_unit == pytest.approx((1.0, 0.0, 0.0))
    assert first.kept_triangle_count + first.removed_triangle_count == len(first.base_payload.triangles)
    assert first.removed_triangle_count > 0
    assert {tri.value for tri in first.triangles} <= {44.0}


def test_clip_plane_side_and_origin_change_view_identity() -> None:
    nodes, elements, result, workspace = _fixture()
    positive = build_clipped_results_render_payload(
        workspace, nodes, elements, result, field="U_MAG",
        plane_origin_mm=(2.0, 0.0, 0.0), plane_normal=(1.0, 0.0, 0.0), keep_side="POSITIVE",
    )
    negative = build_clipped_results_render_payload(
        workspace, nodes, elements, result, field="U_MAG",
        plane_origin_mm=(2.0, 0.0, 0.0), plane_normal=(1.0, 0.0, 0.0), keep_side="NEGATIVE",
    )
    moved = build_clipped_results_render_payload(
        workspace, nodes, elements, result, field="U_MAG",
        plane_origin_mm=(8.0, 0.0, 0.0), plane_normal=(1.0, 0.0, 0.0), keep_side="POSITIVE",
    )
    assert positive.clip_plane.clip_sha256 != negative.clip_plane.clip_sha256
    assert positive.clip_plane.clip_sha256 != moved.clip_plane.clip_sha256
    assert positive.triangles != negative.triangles


def test_clip_plane_preserves_raw_result_ranges() -> None:
    nodes, elements, result, workspace = _fixture()
    payload = build_clipped_results_render_payload(
        workspace, nodes, elements, result, field="VON_MISES_IP_MAX",
        plane_origin_mm=(2.0, 0.0, 0.0), plane_normal=(1.0, 0.0, 0.0),
    )
    assert payload.base_payload.value_min == pytest.approx(44.0)
    assert payload.base_payload.value_max == pytest.approx(44.0)
    assert payload.base_payload.field == "VON_MISES_IP_MAX"
    assert payload.base_payload.unit == "MPa"


def test_clip_plane_fails_closed_on_invalid_contract() -> None:
    nodes, elements, result, workspace = _fixture()
    with pytest.raises(ValueError, match="NORMAL_ZERO"):
        build_clipped_results_render_payload(workspace, nodes, elements, result, field="U_MAG", plane_normal=(0.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="KEEP_SIDE"):
        build_clipped_results_render_payload(workspace, nodes, elements, result, field="U_MAG", keep_side="BOTH")
    with pytest.raises(ValueError, match="TOLERANCE"):
        build_clipped_results_render_payload(workspace, nodes, elements, result, field="U_MAG", tolerance_mm=-1.0)
    with pytest.raises(ValueError, match="ORIGIN"):
        build_clipped_results_render_payload(workspace, nodes, elements, result, field="U_MAG", plane_origin_mm=(0.0, 0.0))
