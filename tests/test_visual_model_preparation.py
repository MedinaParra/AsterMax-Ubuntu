from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pytest

from astermax.fea.model_preparation_evidence import evaluate_tet10_mesh_preparation_gate
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.visual_model_preparation import (
    VisualModelPreparationError,
    build_visual_model_preparation_snapshot,
    tet10_edge_ratio_proxy,
    tet10_jacobian_distribution,
)


def _mesh_fixture():
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [0.0, 0.0, 10.0],
        ],
        dtype=float,
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    elements = np.arange(10, dtype=np.int64)[None, :]
    faces = {
        "X_MIN": np.asarray([[0, 2, 3, 6, 8, 7]], dtype=np.int64),
        "X_MAX": np.asarray([[1, 2, 3, 5, 8, 9]], dtype=np.int64),
        "Y_MIN": np.asarray([[0, 1, 3, 4, 9, 7]], dtype=np.int64),
        "Y_MAX": np.asarray([[1, 2, 3, 5, 8, 9]], dtype=np.int64),
        "Z_MIN": np.asarray([[0, 1, 2, 4, 5, 6]], dtype=np.int64),
        "Z_MAX": np.asarray([[0, 2, 3, 6, 8, 7]], dtype=np.int64),
    }
    gate = evaluate_tet10_mesh_preparation_gate(nodes, elements)
    preparation = {
        "schema": "AsterMaxModelPreparationEvidenceV1",
        "step_sha256": "1" * 64,
        "constraint_selection_sha256": "2" * 64,
        "load_selection_sha256": "3" * 64,
        "snapshot_sha256": "4" * 64,
        "mesh_gate": asdict(gate),
    }
    return nodes, elements, faces, preparation


def test_visual_snapshot_binds_real_tri6_roles_and_mesh_diagnostics() -> None:
    nodes, elements, faces, preparation = _mesh_fixture()
    snapshot = build_visual_model_preparation_snapshot(
        nodes_mm=nodes,
        elements=elements,
        surface_triangles=faces,
        preparation=preparation,
    )
    assert snapshot.schema == "AsterMaxVisualModelPreparationV1"
    assert snapshot.support_tri6_count == 1
    assert snapshot.load_tri6_count == 1
    assert snapshot.body_tri6_count == 4
    assert snapshot.rendered_face_count == 6
    assert {face["role"] for face in snapshot.projected_faces} == {"SUPPORT", "LOAD", "BODY"}
    assert snapshot.jacobian_ip_count == 4
    assert snapshot.minimum_det_jacobian_mm3 > 0.0
    assert snapshot.maximum_det_jacobian_mm3 >= snapshot.minimum_det_jacobian_mm3
    assert 0.0 < snapshot.edge_ratio_minimum <= snapshot.edge_ratio_median <= 1.0
    assert sum(snapshot.edge_ratio_histogram_counts) == 1
    assert snapshot.converged is False
    assert snapshot.industrial_validation is False
    assert snapshot.ansys_equivalence is False
    assert "NOT_ANSYS_ELEMENT_QUALITY" in snapshot.quality_metric_boundary


def test_snapshot_is_deterministic_and_projection_is_normalized() -> None:
    nodes, elements, faces, preparation = _mesh_fixture()
    a = build_visual_model_preparation_snapshot(
        nodes_mm=nodes,
        elements=elements,
        surface_triangles=faces,
        preparation=preparation,
    )
    b = build_visual_model_preparation_snapshot(
        nodes_mm=nodes,
        elements=elements,
        surface_triangles=faces,
        preparation=preparation,
    )
    assert a.snapshot_sha256 == b.snapshot_sha256
    for face in a.projected_faces:
        pts = np.asarray(face["points"], dtype=float)
        assert np.all(pts >= 0.0)
        assert np.all(pts <= 1.0)


def test_edge_ratio_proxy_is_scale_invariant() -> None:
    nodes, elements, _, _ = _mesh_fixture()
    a = tet10_edge_ratio_proxy(nodes, elements)
    b = tet10_edge_ratio_proxy(nodes * 7.5, elements)
    assert np.allclose(a, b, rtol=0.0, atol=1.0e-14)


def test_jacobian_distribution_matches_c4_3_gate_minimum() -> None:
    nodes, elements, _, preparation = _mesh_fixture()
    values = tet10_jacobian_distribution(nodes, elements)
    assert values.shape == (4,)
    assert float(np.min(values)) == pytest.approx(preparation["mesh_gate"]["minimum_det_jacobian_mm3"])


def test_tampered_c4_3_jacobian_gate_fails_closed() -> None:
    nodes, elements, faces, preparation = _mesh_fixture()
    preparation["mesh_gate"] = dict(preparation["mesh_gate"])
    preparation["mesh_gate"]["minimum_det_jacobian_mm3"] *= 0.5
    with pytest.raises(VisualModelPreparationError, match="does not match C4.3 gate"):
        build_visual_model_preparation_snapshot(
            nodes_mm=nodes,
            elements=elements,
            surface_triangles=faces,
            preparation=preparation,
        )


def test_identical_support_and_load_provenance_fails_closed() -> None:
    nodes, elements, faces, preparation = _mesh_fixture()
    preparation["load_selection_sha256"] = preparation["constraint_selection_sha256"]
    with pytest.raises(VisualModelPreparationError, match="must differ"):
        build_visual_model_preparation_snapshot(
            nodes_mm=nodes,
            elements=elements,
            surface_triangles=faces,
            preparation=preparation,
        )


def test_missing_axis_surface_group_fails_closed() -> None:
    nodes, elements, faces, preparation = _mesh_fixture()
    faces.pop("Z_MAX")
    with pytest.raises(VisualModelPreparationError, match="all six"):
        build_visual_model_preparation_snapshot(
            nodes_mm=nodes,
            elements=elements,
            surface_triangles=faces,
            preparation=preparation,
        )
