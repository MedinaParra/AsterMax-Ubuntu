from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import astermax.project_runner as runner
from astermax.fea.tet10_geometry import Tet10GeometryScopeError


def _curved_tet10_mesh():
    corners = np.asarray(
        [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0]],
        dtype=float,
    )
    mids = np.asarray(
        [
            0.5 * (corners[0] + corners[1]),
            0.5 * (corners[1] + corners[2]),
            0.5 * (corners[2] + corners[0]),
            0.5 * (corners[0] + corners[3]),
            0.5 * (corners[2] + corners[3]),
            0.5 * (corners[1] + corners[3]),
        ]
    )
    mids[0, 2] += 0.05
    nodes = np.vstack([corners, mids])
    return SimpleNamespace(
        nodes_mm=nodes,
        elements=np.arange(10, dtype=np.int64).reshape(1, 10),
        surface_triangles={
            "SUPPORT": np.array([[0, 1, 2, 4, 5, 6]], dtype=np.int64),
            "LOAD": np.array([[0, 1, 3, 4, 9, 7]], dtype=np.int64),
        },
    )


def test_project_runner_blocks_curved_tet10_before_bc_or_solver(monkeypatch, tmp_path):
    project = SimpleNamespace(
        mesh_size_mm=10.0,
        support=object(),
        load_surface=object(),
        resultant_n=(0.0, -1000.0, 0.0),
        young_modulus_mpa=200000.0,
        poisson_ratio=0.3,
        geometry_sha256="g",
    )
    monkeypatch.setattr(runner, "read_project", lambda path: project)
    monkeypatch.setattr(runner, "resolve_project_geometry", lambda project_file, p: tmp_path / "fixture.step")
    monkeypatch.setattr(runner, "mesh_step_tet10_with_selections", lambda *args, **kwargs: _curved_tet10_mesh())
    monkeypatch.setattr(runner, "write_mesh_inspector", lambda *args, **kwargs: {"worst_element_index": 0, "html_sha256": "x"})

    bc_called = False
    solver_called = False

    def forbidden_bc(*args, **kwargs):
        nonlocal bc_called
        bc_called = True
        raise AssertionError("BC resolution must not be reached after TET10 geometry-scope FAIL")

    def forbidden_solver(*args, **kwargs):
        nonlocal solver_called
        solver_called = True
        raise AssertionError("solver must not be reached after TET10 geometry-scope FAIL")

    monkeypatch.setattr(runner, "unique_surface_nodes", forbidden_bc)
    monkeypatch.setattr(runner, "solve_linear_static_tet10", forbidden_solver)

    with pytest.raises(Tet10GeometryScopeError, match="failed before assembly"):
        runner.run_project(tmp_path / "model.astermax", tmp_path / "results")

    assert bc_called is False
    assert solver_called is False
