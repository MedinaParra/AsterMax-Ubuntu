import math

import numpy as np
import pytest

from astermax.fea.quadratic_tri6_face_contour import build_quadratic_tri6_face_contour


def _curved_tet10_fixture() -> tuple[np.ndarray, np.ndarray]:
    # Face 0 uses x=r, y=s and z=f(r)=r^2-r+0.2 exactly under TRI6 interpolation.
    # Its z=0 contour therefore has the analytic roots r=(1±sqrt(0.2))/2.
    f = lambda r: r * r - r + 0.2
    p0 = np.array([0.0, 0.0, f(0.0)])
    p1 = np.array([1.0, 0.0, f(1.0)])
    p2 = np.array([0.0, 1.0, f(0.0)])
    p3 = np.array([0.0, 0.0, 1.0])
    p4 = np.array([0.5, 0.0, f(0.5)])
    p5 = np.array([0.5, 0.5, f(0.5)])
    p6 = np.array([0.0, 0.5, f(0.0)])
    p7 = 0.5 * (p0 + p3)
    p8 = 0.5 * (p2 + p3)
    p9 = 0.5 * (p1 + p3)
    nodes = np.vstack((p0, p1, p2, p3, p4, p5, p6, p7, p8, p9))
    elements = np.arange(10, dtype=np.int64).reshape(1, 10)
    return nodes, elements


def _build(divisions: int = 24, *, workspace: str = "workspace", solve: str = "solve"):
    nodes, elements = _curved_tet10_fixture()
    return build_quadratic_tri6_face_contour(
        nodes,
        elements,
        plane_origin_mm=(0.0, 0.0, 0.0),
        plane_normal=(0.0, 0.0, 1.0),
        workspace_sha256=workspace,
        solve_evidence_sha256=solve,
        tolerance_mm=1.0e-10,
        sampling_divisions=divisions,
    )


def test_quadratic_face_contour_is_deterministic_and_provenance_bound():
    first = _build(24)
    second = _build(24)
    assert first == second
    assert first.contour_sha256 == second.contour_sha256
    assert first.length_unit == "mm"
    assert first.segment_count > 0
    assert _build(24, solve="solve-2").contour_sha256 != first.contour_sha256
    assert _build(32).contour_sha256 != first.contour_sha256


def test_curved_face_matches_analytic_zero_contour_and_refines_residual():
    coarse = _build(8)
    fine = _build(40)
    coarse_face = [segment for segment in coarse.segments if segment.face_id == 0]
    fine_face = [segment for segment in fine.segments if segment.face_id == 0]
    assert coarse_face and fine_face

    coarse_residual = max(segment.max_plane_residual_mm for segment in coarse_face)
    fine_residual = max(segment.max_plane_residual_mm for segment in fine_face)
    assert fine_residual < coarse_residual
    assert fine_residual < 5.0e-4

    roots = ((1.0 - math.sqrt(0.2)) / 2.0, (1.0 + math.sqrt(0.2)) / 2.0)
    x_values = [point[0] for segment in fine_face for point in segment.points_mm]
    for root in roots:
        assert min(abs(x - root) for x in x_values) < 2.0e-3


def test_planar_quadratic_face_reduces_to_machine_close_plane_contour():
    nodes, elements = _curved_tet10_fixture()
    # Replace face-0 z coordinates by z=x-0.25, while retaining quadratic midside nodes.
    for node_id in (0, 1, 2, 4, 5, 6):
        nodes[node_id, 2] = nodes[node_id, 0] - 0.25
    result = build_quadratic_tri6_face_contour(
        nodes,
        elements,
        plane_origin_mm=(0.0, 0.0, 0.0),
        plane_normal=(0.0, 0.0, 1.0),
        workspace_sha256="workspace",
        solve_evidence_sha256="solve",
        sampling_divisions=12,
    )
    face = [segment for segment in result.segments if segment.face_id == 0]
    assert face
    assert max(segment.max_plane_residual_mm for segment in face) < 1.0e-12
    assert max(abs(point[0] - 0.25) for segment in face for point in segment.points_mm) < 1.0e-12


def test_invalid_contracts_fail_closed():
    nodes, elements = _curved_tet10_fixture()
    kwargs = dict(
        plane_origin_mm=(0.0, 0.0, 0.0),
        plane_normal=(0.0, 0.0, 1.0),
        workspace_sha256="workspace",
        solve_evidence_sha256="solve",
    )
    with pytest.raises(ValueError, match="DIVISIONS"):
        build_quadratic_tri6_face_contour(nodes, elements, sampling_divisions=1, **kwargs)
    with pytest.raises(ValueError, match="NORMAL"):
        build_quadratic_tri6_face_contour(
            nodes,
            elements,
            plane_origin_mm=(0.0, 0.0, 0.0),
            plane_normal=(0.0, 0.0, 0.0),
            workspace_sha256="workspace",
            solve_evidence_sha256="solve",
        )
    with pytest.raises(ValueError, match="PROVENANCE"):
        build_quadratic_tri6_face_contour(
            nodes,
            elements,
            plane_origin_mm=(0.0, 0.0, 0.0),
            plane_normal=(0.0, 0.0, 1.0),
            workspace_sha256="",
            solve_evidence_sha256="solve",
        )


def test_contract_does_not_claim_cut_surface_fea_fields_or_equivalence():
    result = _build(16)
    text = repr(result).lower()
    for forbidden in (
        "stress_interpolation",
        "von_mises_field",
        "section_resultant",
        "industrial_validation",
        "ansys_equivalence",
    ):
        assert forbidden not in text
    assert "approximation_geometry_only" in result.semantics
