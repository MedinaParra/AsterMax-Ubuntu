from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from astermax.solver.fe_result_package import (
    ElementFamily,
    FEFieldV1,
    FEResultPackageV1,
    FEStateV1,
    FieldAssociation,
    FieldEvidenceClass,
    MeshTopologyV1,
)
from astermax.solver.mesh_convergence import (
    ConvergenceStatus,
    MeshLevelV1,
    MeshMetricsV1,
    MeshRunV1,
    evaluate_mesh_convergence,
)
from astermax.ui.ansys_style_post import (
    AnsysStyleViewConfig,
    StressDisplayMode,
    build_ansys_style_grid,
    volume_weighted_cell_to_point_scalar,
)


def package() -> FEResultPackageV1:
    mesh = MeshTopologyV1(
        element_family=ElementFamily.TET4,
        nodes_mm=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.0, 0.0, 2.0),
        ],
        connectivity=[[0, 1, 2, 3], [0, 1, 2, 4]],
        body_ids=[1, 2],
        named_cell_sets={"CONTACT_REGION": [0, 1]},
    )
    displacement = FEFieldV1(
        name="DISPLACEMENT",
        association=FieldAssociation.POINT,
        components=3,
        values=[
            [0.0, 0.0, 0.0],
            [0.1, 0.0, 0.0],
            [0.0, 0.1, 0.0],
            [0.0, 0.0, 0.1],
            [0.0, 0.0, 0.2],
        ],
        unit="mm",
        evidence_class=FieldEvidenceClass.SOLVER_RESULT,
    )
    vm = FEFieldV1(
        name="VON_MISES",
        association=FieldAssociation.CELL,
        components=1,
        values=[[10.0], [40.0]],
        unit="MPa",
        evidence_class=FieldEvidenceClass.SOLVER_RESULT,
        averaged=False,
    )
    return FEResultPackageV1(
        result_class="SOLVER_RESULT",
        mesh=mesh,
        states=[FEStateV1(load_factor=1.0, fields=[displacement, vm])],
    )


def run(level: str, local_size: float, elements: int, family: str, scale: float = 1.0) -> MeshRunV1:
    return MeshRunV1(
        mesh=MeshLevelV1(
            level_id=level,
            global_size_mm=local_size * 3.0,
            local_size_mm=local_size,
            element_family=family,
            node_count=max(elements // 3, 4),
            element_count=elements,
        ),
        metrics=MeshMetricsV1(
            max_displacement_mm=0.3000 * scale,
            reaction_resultant_n=1_000_000.0 * scale,
            contact_resultant_n=999_000.0 * scale,
            active_contact_area_mm2=20_000.0 * scale,
            von_mises_p95_mpa=250.0 * scale,
            von_mises_p99_mpa=300.0 * scale,
            contact_pressure_p95_mpa=420.0 * scale,
            contact_pressure_p99_mpa=500.0 * scale,
            reported_peak_von_mises_mpa=1200.0 * scale,
            reported_peak_contact_pressure_mpa=1800.0 * scale,
        ),
    )


def test_result_package_requires_complete_connectivity_and_field_lengths() -> None:
    p = package()
    assert len(p.mesh.connectivity) == 2
    assert p.state_at_or_before(1.0).load_factor == 1.0

    with pytest.raises(ValidationError):
        MeshTopologyV1(
            element_family=ElementFamily.TET4,
            nodes_mm=[(0, 0, 0)] * 4,
            connectivity=[[0, 1, 2]],
            body_ids=[1],
        )

    bad_field = FEFieldV1(
        name="DISPLACEMENT",
        association=FieldAssociation.POINT,
        components=3,
        values=[[0.0, 0.0, 0.0]] * 4,
        evidence_class=FieldEvidenceClass.SOLVER_RESULT,
    )
    with pytest.raises(ValidationError):
        FEResultPackageV1(
            result_class="SOLVER_RESULT",
            mesh=p.mesh,
            states=[FEStateV1(load_factor=1.0, fields=[bad_field])],
        )


def test_volume_weighted_nodal_averaging_is_deterministic_and_preserves_raw_values() -> None:
    p = package()
    raw = np.array([10.0, 40.0])
    averaged = volume_weighted_cell_to_point_scalar(p, raw)
    # Tet volumes are 1/6 and 2/6. Shared nodes receive volume-weighted value 30 MPa.
    np.testing.assert_allclose(averaged, [30.0, 30.0, 30.0, 10.0, 40.0], rtol=0, atol=1e-12)
    np.testing.assert_array_equal(raw, [10.0, 40.0])


def test_convergence_gate_passes_adjacent_same_family_meshes_within_thresholds() -> None:
    m0 = run("M0", 3.0, 10_000, "TET10", 1.000)
    m1 = run("M1", 2.0, 24_000, "TET10", 1.012)
    report = evaluate_mesh_convergence(m0, m1)
    assert report.status == ConvergenceStatus.PASS
    assert report.same_element_family is True
    assert "reported_peak_von_mises_mpa" in report.maxima_excluded_from_gate


def test_singular_peak_growth_does_not_fake_failure_when_gated_metrics_converge() -> None:
    m1 = run("M1", 2.0, 24_000, "TET4", 1.000)
    m2 = run("M2", 1.5, 52_000, "TET4", 1.010)
    m2.metrics.reported_peak_von_mises_mpa = 5000.0
    m2.metrics.reported_peak_contact_pressure_mpa = 9000.0
    report = evaluate_mesh_convergence(m1, m2)
    assert report.status == ConvergenceStatus.PASS


def test_element_family_change_cannot_be_silently_declared_converged() -> None:
    m1 = run("M1", 2.0, 24_000, "TET4", 1.000)
    m2 = run("M2", 1.5, 52_000, "TET10", 1.001)
    report = evaluate_mesh_convergence(m1, m2)
    assert report.same_element_family is False
    assert report.status == ConvergenceStatus.FAIL


def test_ansys_style_vtk_grid_keeps_raw_elemental_and_separate_smoothed_display() -> None:
    pytest.importorskip("vtkmodules")
    p = package()
    config = AnsysStyleViewConfig(
        field_name="VON_MISES",
        stress_display_mode=StressDisplayMode.NODAL_AVERAGED,
        deformation_scale=10.0,
        show_mesh=True,
    )
    grid, meta = build_ansys_style_grid(p, 0, config)
    raw = grid.GetCellData().GetArray("VON_MISES__ELEMENTAL_UNAVERAGED")
    smooth = grid.GetPointData().GetArray("VON_MISES__NODAL_AVERAGED_DISPLAY")
    assert raw is not None
    assert smooth is not None
    assert raw.GetTuple1(0) == pytest.approx(10.0)
    assert raw.GetTuple1(1) == pytest.approx(40.0)
    assert smooth.GetTuple1(0) == pytest.approx(30.0)
    assert meta["display_is_averaged"] is True
    assert meta["deformation_scale"] == 10.0


def test_elemental_display_remains_unaveraged() -> None:
    pytest.importorskip("vtkmodules")
    p = package()
    config = AnsysStyleViewConfig(
        field_name="VON_MISES",
        stress_display_mode=StressDisplayMode.ELEMENTAL_UNAVERAGED,
        deformation_scale=0.0,
    )
    grid, meta = build_ansys_style_grid(p, 0, config)
    assert meta["association"] == "CELL"
    assert meta["active_array"] == "VON_MISES__ELEMENTAL_UNAVERAGED"
    assert meta["display_is_averaged"] is False
