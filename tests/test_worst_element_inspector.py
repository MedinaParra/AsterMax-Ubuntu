from dataclasses import asdict
from math import sqrt
from pathlib import Path

import numpy as np
import pytest

from astermax.app import prepare_step_analysis
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.pre_solve_review import visual_preparation_payload
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet_quality import build_tet10_corner_quality_snapshot
from astermax.fea.worst_element_inspector import (
    WorstElementInspectorError,
    build_worst_element_quality_snapshot,
)


def _regular(scale: float = 1.0, xoff: float = 0.0) -> np.ndarray:
    v = np.asarray([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.5, sqrt(3.0) / 2.0, 0.0],
        [0.5, sqrt(3.0) / 6.0, sqrt(2.0 / 3.0)],
    ])
    return v * scale + np.asarray([xoff, 0.0, 0.0])


def _two_tet_mesh() -> tuple[np.ndarray, np.ndarray]:
    a = straight_sided_tet10_from_vertices(_regular(scale=10.0, xoff=0.0))
    degraded_vertices = _regular(scale=10.0, xoff=30.0)
    degraded_vertices[3, 2] *= 0.15
    b = straight_sided_tet10_from_vertices(degraded_vertices)
    nodes = np.vstack([a, b])
    elements = np.vstack([np.arange(10), np.arange(10, 20)]).astype(np.int64)
    return nodes, elements


def test_worst_element_order_and_distribution_match_c4_6_evidence() -> None:
    nodes, elements = _two_tet_mesh()
    quality = build_tet10_corner_quality_snapshot(nodes, elements)
    snapshot = build_worst_element_quality_snapshot(
        nodes_mm=nodes,
        elements=elements,
        tetra_quality=asdict(quality),
        worst_count=2,
    )
    assert snapshot.schema == "AsterMaxWorstElementQualityInspectorV1"
    assert snapshot.worst_elements[0]["element_index"] == 1
    assert snapshot.worst_elements[1]["element_index"] == 0
    assert snapshot.worst_elements[0]["quality"] < snapshot.worst_elements[1]["quality"]
    assert sum(snapshot.histogram_counts) == 2
    assert snapshot.quality_minimum == pytest.approx(quality.minimum)
    assert snapshot.quality_p10 == pytest.approx(quality.percentile_10)
    assert snapshot.quality_median == pytest.approx(quality.median)
    assert snapshot.crosscheck_verified is True
    assert snapshot.ansys_metric_equivalence is False
    assert snapshot.industrial_acceptance_threshold_declared is False


def test_snapshot_is_deterministic() -> None:
    nodes, elements = _two_tet_mesh()
    quality = asdict(build_tet10_corner_quality_snapshot(nodes, elements))
    a = build_worst_element_quality_snapshot(nodes_mm=nodes, elements=elements, tetra_quality=quality)
    b = build_worst_element_quality_snapshot(nodes_mm=nodes, elements=elements, tetra_quality=quality)
    assert a.snapshot_sha256 == b.snapshot_sha256
    assert a.worst_elements == b.worst_elements


def test_tampered_c4_6_summary_fails_closed() -> None:
    nodes, elements = _two_tet_mesh()
    quality = asdict(build_tet10_corner_quality_snapshot(nodes, elements))
    quality["minimum"] += 0.01
    with pytest.raises(WorstElementInspectorError, match="minimum"):
        build_worst_element_quality_snapshot(nodes_mm=nodes, elements=elements, tetra_quality=quality)


def test_unverified_or_ansys_equivalent_quality_fails_closed() -> None:
    nodes, elements = _two_tet_mesh()
    quality = asdict(build_tet10_corner_quality_snapshot(nodes, elements))
    bad = dict(quality); bad["crosscheck_verified"] = False
    with pytest.raises(WorstElementInspectorError, match="CROSSCHECK"):
        build_worst_element_quality_snapshot(nodes_mm=nodes, elements=elements, tetra_quality=bad)
    bad = dict(quality); bad["ansys_metric_equivalence"] = True
    with pytest.raises(WorstElementInspectorError, match="ANSYS"):
        build_worst_element_quality_snapshot(nodes_mm=nodes, elements=elements, tetra_quality=bad)


def test_worst_element_locations_stay_inside_normalized_view() -> None:
    nodes, elements = _two_tet_mesh()
    quality = asdict(build_tet10_corner_quality_snapshot(nodes, elements))
    snapshot = build_worst_element_quality_snapshot(nodes_mm=nodes, elements=elements, tetra_quality=quality)
    for row in snapshot.worst_elements:
        assert all(0.0 <= value <= 1.0 for value in row["projected_centroid"])
        for point in row["projected_corners"]:
            assert all(0.0 <= value <= 1.0 for value in point)


def _write_box(path: Path) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c4_7_fixture")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 80.0, 25.0, 15.0)
        gmsh.model.occ.synchronize(); gmsh.write(str(path))
    finally:
        gmsh.finalize()


def test_real_step_gmsh_payload_produces_worst_element_inspector(tmp_path: Path) -> None:
    step = tmp_path / "box.step"; _write_box(step)
    prepared = prepare_step_analysis(
        step,
        mesh_size_mm=20.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.3,
        resultant_n=(1500.0, 0.0, 0.0),
    )
    payload = visual_preparation_payload(prepared)
    snapshot = build_worst_element_quality_snapshot(
        nodes_mm=payload["nodes_mm"],
        elements=payload["elements"],
        tetra_quality=payload["tetra_quality"],
    )
    assert snapshot.element_count == prepared["review"].tet10_count
    assert snapshot.quality_minimum == pytest.approx(prepared["review"].tetra_mean_ratio_minimum)
    assert 1 <= len(snapshot.worst_elements) <= 12
    assert snapshot.crosscheck_verified is True
    assert snapshot.ansys_metric_equivalence is False
