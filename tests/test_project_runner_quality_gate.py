from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import astermax.project_runner as runner
from astermax.fea.mesh_quality import MeshQualityError, MeshQualityReport
from astermax.fea.tet10_geometry import Tet10GeometryScopeReport
from astermax.fea.tet10_jacobian import Tet10JacobianReport


def test_project_runner_blocks_before_solver_when_mesh_quality_fails(monkeypatch, tmp_path):
    project = SimpleNamespace(
        mesh_size_mm=10.0,
        support=object(),
        load_surface=object(),
        resultant_n=(0.0, -1000.0, 0.0),
        young_modulus_mpa=200000.0,
        poisson_ratio=0.3,
        geometry_sha256="g",
    )
    bad_mesh = SimpleNamespace(
        nodes_mm=np.array(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]],
            dtype=float,
        ),
        elements=np.array([[0, 1, 2, 3]], dtype=np.int64),
        surface_triangles={"SUPPORT": np.array([[0, 1, 2]]), "LOAD": np.array([[0, 1, 2]])},
    )
    passing_jacobian = Tet10JacobianReport(
        schema="AsterMaxTet10SampledJacobianReportV1",
        status="PASS",
        element_count=1,
        sample_count_per_element=15,
        nonpositive_sample_count=0,
        minimum_determinant=1.0,
        worst_element_index=0,
        worst_sample_index=0,
        worst_natural_coordinates=(0.0, 0.0, 0.0),
        policy={"determinant_epsilon": 1.0e-12, "sample_schema": "TET10_JACOBIAN_SAMPLE_POINTS_V1"},
        evidence_boundary="SAMPLED_ONLY",
    )
    passing_geometry = Tet10GeometryScopeReport(
        element_count=1,
        non_straight_sided_elements=0,
        max_midpoint_deviation_mm=0.0,
        max_relative_midpoint_deviation=0.0,
        worst_element_index=0,
        status="PASS",
        solver_scope="STRAIGHT_SIDED_TET10_FOUR_POINT_VERIFICATION",
        policy={"relative_midpoint_tolerance": 1.0e-10, "absolute_floor_mm": 1.0e-12},
    )
    failed_report = MeshQualityReport(
        element_count=1,
        min_scaled_jacobian=-1.0,
        min_mean_ratio=0.0,
        max_edge_aspect_ratio=1.41421356237,
        inverted_elements=1,
        degenerate_elements=0,
        warn_elements=0,
        fail_elements=1,
        status="FAIL",
    )

    monkeypatch.setattr(runner, "read_project", lambda path: project)
    monkeypatch.setattr(runner, "resolve_project_geometry", lambda project_file, p: tmp_path / "fixture.step")
    monkeypatch.setattr(runner, "mesh_step_tet10_with_selections", lambda *args, **kwargs: bad_mesh)
    monkeypatch.setattr(runner, "tet10_sampled_jacobian_report", lambda *args, **kwargs: passing_jacobian)
    monkeypatch.setattr(runner, "tet10_geometry_scope", lambda *args, **kwargs: passing_geometry)
    monkeypatch.setattr(runner, "tetra_mesh_quality", lambda *args, **kwargs: failed_report)

    solver_called = False

    def forbidden_solver(*args, **kwargs):
        nonlocal solver_called
        solver_called = True
        raise AssertionError("solver must not be reached after mesh-quality FAIL")

    monkeypatch.setattr(runner, "solve_linear_static_tet10", forbidden_solver)

    with pytest.raises(MeshQualityError, match="mesh quality gate failed"):
        runner.run_project(tmp_path / "model.astermax", tmp_path / "results")

    assert solver_called is False
