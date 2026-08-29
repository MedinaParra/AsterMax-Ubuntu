from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.adaptive_tet10_section import build_adaptive_tet10_section
from astermax.fea.section_polyline_assembly import assemble_section_polylines
from astermax.fea.section_displacement_field import build_section_displacement_field


def _linear_tet10() -> tuple[np.ndarray, np.ndarray]:
    corners = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ),
        dtype=float,
    )
    nodes = np.vstack(
        (
            corners,
            0.5 * (corners[0] + corners[1]),
            0.5 * (corners[1] + corners[2]),
            0.5 * (corners[2] + corners[0]),
            0.5 * (corners[0] + corners[3]),
            0.5 * (corners[2] + corners[3]),
            0.5 * (corners[1] + corners[3]),
        )
    )
    return nodes, np.arange(10, dtype=np.int64).reshape(1, 10)


def _assembly(nodes: np.ndarray, elements: np.ndarray):
    section = build_adaptive_tet10_section(
        nodes,
        elements,
        plane_origin_mm=(0.0, 0.0, 0.3),
        plane_normal=(0.0, 0.0, 1.0),
        workspace_sha256="workspace-c5-4s",
        solve_evidence_sha256="solve-c5-4s",
        target_error_mm=1.0e-10,
        topology_tolerance_mm=1.0e-8,
        initial_sampling_divisions=4,
        max_sampling_divisions=8,
    )
    assembly = assemble_section_polylines(section, endpoint_tolerance_mm=1.0e-8)
    assert assembly.ready_for_results
    assert assembly.closed_polyline_count == 1
    return assembly


def _affine_displacement(points: np.ndarray) -> np.ndarray:
    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]
    return np.column_stack(
        (
            1.0 + 2.0 * x - 3.0 * y + 0.5 * z,
            -2.0 + x + 4.0 * y - z,
            0.25 - 0.5 * x + 2.0 * z,
        )
    )


def test_affine_displacement_is_reproduced_on_verified_section() -> None:
    nodes, elements = _linear_tet10()
    assembly = _assembly(nodes, elements)
    field = build_section_displacement_field(
        nodes,
        elements,
        _affine_displacement(nodes),
        assembly,
        workspace_sha256="workspace-c5-4s",
        solve_evidence_sha256="solve-c5-4s",
        geometry_tolerance_mm=1.0e-10,
        cross_element_tolerance_mm=1.0e-10,
    )
    assert field.status == "READY"
    assert field.sample_count == len(assembly.polylines[0].points_mm)
    assert field.max_geometry_residual_mm < 1.0e-10
    for sample in field.samples:
        expected = _affine_displacement(np.asarray([sample.point_mm]))[0]
        assert np.allclose(sample.displacement_mm, expected, rtol=0.0, atol=1.0e-11)


def test_rigid_translation_is_exact_and_deterministic() -> None:
    nodes, elements = _linear_tet10()
    assembly = _assembly(nodes, elements)
    nodal = np.tile(np.asarray((0.125, -0.25, 1.5)), (nodes.shape[0], 1))
    a = build_section_displacement_field(
        nodes, elements, nodal, assembly,
        workspace_sha256="workspace-c5-4s", solve_evidence_sha256="solve-c5-4s",
    )
    b = build_section_displacement_field(
        nodes, elements, nodal, assembly,
        workspace_sha256="workspace-c5-4s", solve_evidence_sha256="solve-c5-4s",
    )
    assert a.field_sha256 == b.field_sha256
    for sample in a.samples:
        assert np.allclose(sample.displacement_mm, (0.125, -0.25, 1.5), rtol=0.0, atol=1.0e-12)


def test_field_identity_changes_when_solved_nodal_field_changes() -> None:
    nodes, elements = _linear_tet10()
    assembly = _assembly(nodes, elements)
    nodal = _affine_displacement(nodes)
    a = build_section_displacement_field(
        nodes, elements, nodal, assembly,
        workspace_sha256="workspace-c5-4s", solve_evidence_sha256="solve-c5-4s",
    )
    changed = nodal.copy()
    changed[0, 0] += 0.01
    b = build_section_displacement_field(
        nodes, elements, changed, assembly,
        workspace_sha256="workspace-c5-4s", solve_evidence_sha256="solve-c5-4s",
    )
    assert a.nodal_field_sha256 != b.nodal_field_sha256
    assert a.field_sha256 != b.field_sha256


def test_stale_solve_provenance_fails_closed() -> None:
    nodes, elements = _linear_tet10()
    assembly = _assembly(nodes, elements)
    with pytest.raises(ValueError, match="SECTION_DISPLACEMENT_STALE_SECTION"):
        build_section_displacement_field(
            nodes,
            elements,
            _affine_displacement(nodes),
            assembly,
            workspace_sha256="workspace-c5-4s",
            solve_evidence_sha256="different-solve",
        )


def test_geometry_mismatch_fails_closed() -> None:
    nodes, elements = _linear_tet10()
    assembly = _assembly(nodes, elements)
    modified = nodes.copy()
    modified[0, 0] += 0.001
    with pytest.raises(ValueError, match="SECTION_DISPLACEMENT_GEOMETRY_MISMATCH"):
        build_section_displacement_field(
            modified,
            elements,
            _affine_displacement(modified),
            assembly,
            workspace_sha256="workspace-c5-4s",
            solve_evidence_sha256="solve-c5-4s",
        )


def test_invalid_nodal_field_rejected() -> None:
    nodes, elements = _linear_tet10()
    assembly = _assembly(nodes, elements)
    with pytest.raises(ValueError, match="SECTION_DISPLACEMENT_FIELD"):
        build_section_displacement_field(
            nodes,
            elements,
            np.zeros((nodes.shape[0], 2)),
            assembly,
            workspace_sha256="workspace-c5-4s",
            solve_evidence_sha256="solve-c5-4s",
        )


def test_contract_does_not_claim_unverified_cut_stress_or_resultants() -> None:
    nodes, elements = _linear_tet10()
    assembly = _assembly(nodes, elements)
    field = build_section_displacement_field(
        nodes,
        elements,
        _affine_displacement(nodes),
        assembly,
        workspace_sha256="workspace-c5-4s",
        solve_evidence_sha256="solve-c5-4s",
    )
    text = (field.schema + " " + field.semantics).lower()
    forbidden = ("von_mises", "stress_interpolation", "section_resultant", "ansys_equivalence")
    assert not any(token in text for token in forbidden)
