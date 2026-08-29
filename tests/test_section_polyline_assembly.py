import numpy as np
import pytest

from astermax.fea.adaptive_tet10_section import build_adaptive_tet10_section
from astermax.fea.section_polyline_assembly import assemble_section_polylines


def _multi_tet_fixture(apices: list[tuple[float, float, float]]) -> tuple[np.ndarray, np.ndarray]:
    nodes: list[np.ndarray] = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ]
    for apex in apices:
        nodes.append(np.asarray(apex, dtype=float))

    coordinate_index = {tuple(point.tolist()): index for index, point in enumerate(nodes)}

    def midpoint_index(a: int, b: int) -> int:
        point = 0.5 * (nodes[a] + nodes[b])
        key = tuple(float(value) for value in point)
        if key not in coordinate_index:
            coordinate_index[key] = len(nodes)
            nodes.append(point)
        return coordinate_index[key]

    elements: list[list[int]] = []
    for apex_index in range(3, 3 + len(apices)):
        c0, c1, c2, c3 = 0, 1, 2, apex_index
        elements.append(
            [
                c0,
                c1,
                c2,
                c3,
                midpoint_index(c0, c1),
                midpoint_index(c1, c2),
                midpoint_index(c2, c0),
                midpoint_index(c0, c3),
                midpoint_index(c2, c3),
                midpoint_index(c1, c3),
            ]
        )
    return np.vstack(nodes), np.asarray(elements, dtype=np.int64)


def _adaptive(nodes: np.ndarray, elements: np.ndarray):
    return build_adaptive_tet10_section(
        nodes,
        elements,
        plane_origin_mm=(0.23, 0.0, 0.0),
        plane_normal=(1.0, 0.0, 0.0),
        workspace_sha256="workspace",
        solve_evidence_sha256="solve",
        target_error_mm=1.0e-10,
        topology_tolerance_mm=1.0e-8,
        initial_sampling_divisions=8,
        max_sampling_divisions=16,
    )


def test_two_tets_cancel_shared_face_and_assemble_one_cross_element_closed_loop():
    nodes, elements = _multi_tet_fixture([(0.0, 0.0, 1.0), (0.0, 0.0, -1.0)])
    section = _adaptive(nodes, elements)
    result = assemble_section_polylines(section, endpoint_tolerance_mm=1.0e-8)

    assert section.converged
    assert result.ready_for_results
    assert result.topology_valid
    assert result.length_unit == "mm"
    assert result.cancelled_internal_edge_count > 0
    assert result.nonmanifold_shared_face_count == 0
    assert result.branch_node_count == 0
    assert result.open_polyline_count == 0
    assert result.closed_polyline_count == 1
    assert result.cross_element_polyline_count == 1
    assert len(result.polylines) == 1
    polyline = result.polylines[0]
    assert polyline.closed
    assert polyline.contributing_element_ids == (0, 1)
    assert polyline.points_mm[0] == polyline.points_mm[-1]
    assert polyline.unique_edge_count == len(polyline.points_mm) - 1


def test_single_linear_tet_reduces_to_one_ordered_closed_polyline():
    nodes, elements = _multi_tet_fixture([(0.0, 0.0, 1.0)])
    section = _adaptive(nodes, elements)
    result = assemble_section_polylines(section)

    assert result.ready_for_results
    assert result.closed_polyline_count == 1
    assert result.open_polyline_count == 0
    assert result.polylines[0].contributing_element_ids == (0,)
    assert result.unique_boundary_edge_count == result.polylines[0].unique_edge_count


def test_three_tets_sharing_one_tri6_face_fail_closed_as_nonmanifold():
    nodes, elements = _multi_tet_fixture(
        [(0.0, 0.0, 1.0), (0.0, 0.0, -1.0), (0.0, 0.0, 2.0)]
    )
    section = _adaptive(nodes, elements)
    result = assemble_section_polylines(section)

    assert result.nonmanifold_shared_face_count > 0
    assert not result.topology_valid
    assert not result.ready_for_results


def test_assembly_identity_is_deterministic_and_bound_to_source_section():
    nodes, elements = _multi_tet_fixture([(0.0, 0.0, 1.0), (0.0, 0.0, -1.0)])
    first = assemble_section_polylines(_adaptive(nodes, elements))
    second = assemble_section_polylines(_adaptive(nodes, elements))
    assert first == second
    assert first.assembly_sha256 == second.assembly_sha256
    assert first.source_section_sha256 == _adaptive(nodes, elements).section_sha256

    altered = build_adaptive_tet10_section(
        nodes,
        elements,
        plane_origin_mm=(0.31, 0.0, 0.0),
        plane_normal=(1.0, 0.0, 0.0),
        workspace_sha256="workspace",
        solve_evidence_sha256="solve",
        target_error_mm=1.0e-10,
        topology_tolerance_mm=1.0e-8,
        initial_sampling_divisions=8,
        max_sampling_divisions=16,
    )
    assert assemble_section_polylines(altered).assembly_sha256 != first.assembly_sha256


def test_invalid_endpoint_tolerance_fails_closed():
    nodes, elements = _multi_tet_fixture([(0.0, 0.0, 1.0)])
    section = _adaptive(nodes, elements)
    with pytest.raises(ValueError, match="ENDPOINT_TOLERANCE"):
        assemble_section_polylines(section, endpoint_tolerance_mm=0.0)


def test_contract_does_not_claim_unvalidated_section_field_quantities():
    nodes, elements = _multi_tet_fixture([(0.0, 0.0, 1.0)])
    result = assemble_section_polylines(_adaptive(nodes, elements))
    text = repr(result).lower()
    for forbidden in (
        "stress_interpolation",
        "von_mises_field",
        "section_resultant",
        "industrial_validation",
        "ansys_equivalence",
    ):
        assert forbidden not in text
    assert "geometry_only" in result.semantics
