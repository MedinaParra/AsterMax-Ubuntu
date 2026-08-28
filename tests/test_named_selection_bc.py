from pathlib import Path

import pytest

from astermax.app import prepare_step_analysis, solve_prepared_analysis
from astermax.fea.gmsh_bridge import _gmsh, mesh_step_tet10
from astermax.fea.named_selection_bc import (
    NamedSelectionBindingError,
    bind_named_selection_to_mesh,
    capture_axis_named_selection,
)
from astermax.fea.pre_solve_review import PreSolveReviewError, accept_model_preparation


def _write_box(path: Path, dx: float = 60.0, dy: float = 20.0, dz: float = 10.0) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c5_1_fixture")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, dx, dy, dz)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def test_named_selection_binds_non_x_faces_to_real_tri6(tmp_path: Path) -> None:
    step = tmp_path / "box.step"; _write_box(step)
    mesh = mesh_step_tet10(step, 20.0)
    support = capture_axis_named_selection(step, mesh.bbox_mm, ("Y_MIN",), name="Bearing Support", role="SUPPORT")
    binding, triangles = bind_named_selection_to_mesh(step, support, bbox_mm=mesh.bbox_mm, surface_triangles=mesh.surface_triangles, expected_role="SUPPORT")
    assert binding.surface_keys == ("Y_MIN",)
    assert binding.tri6_count == triangles.shape[0] > 0
    assert triangles.shape[1] == 6
    assert binding.named_selection_sha256 == support.named_selection_sha256


def test_multiface_named_support_stacks_boundary_groups_deterministically(tmp_path: Path) -> None:
    step = tmp_path / "box.step"; _write_box(step)
    mesh = mesh_step_tet10(step, 20.0)
    selection = capture_axis_named_selection(step, mesh.bbox_mm, ("X_MIN", "Y_MIN"), name="Two Face Support", role="SUPPORT")
    first, tri_first = bind_named_selection_to_mesh(step, selection, bbox_mm=mesh.bbox_mm, surface_triangles=mesh.surface_triangles, expected_role="SUPPORT")
    second, tri_second = bind_named_selection_to_mesh(step, selection, bbox_mm=mesh.bbox_mm, surface_triangles=mesh.surface_triangles, expected_role="SUPPORT")
    assert first.surface_keys == ("X_MIN", "Y_MIN")
    assert first.binding_sha256 == second.binding_sha256
    assert tri_first.shape == tri_second.shape
    assert first.tri6_count == mesh.surface_triangles["X_MIN"].shape[0] + mesh.surface_triangles["Y_MIN"].shape[0]


def test_role_mismatch_and_unsupported_surface_fail_closed(tmp_path: Path) -> None:
    step = tmp_path / "box.step"; _write_box(step)
    mesh = mesh_step_tet10(step, 20.0)
    load = capture_axis_named_selection(step, mesh.bbox_mm, ("Z_MAX",), name="Load", role="LOAD")
    with pytest.raises(NamedSelectionBindingError, match="role"):
        bind_named_selection_to_mesh(step, load, bbox_mm=mesh.bbox_mm, surface_triangles=mesh.surface_triangles, expected_role="SUPPORT")
    with pytest.raises(NamedSelectionBindingError, match="surface_keys"):
        capture_axis_named_selection(step, mesh.bbox_mm, ("SLOPED_FACE",), name="Bad", role="SUPPORT")


def test_pre_solve_review_v3_binds_authored_support_and_load(tmp_path: Path) -> None:
    step = tmp_path / "box.step"; _write_box(step)
    prepared = prepare_step_analysis(
        step,
        mesh_size_mm=20.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, 0.0, 1000.0),
        support_surface_keys=("Y_MIN",),
        load_surface_keys=("Z_MAX",),
    )
    review = prepared["review"]
    assert review.schema == "AsterMaxPreSolveReviewV3"
    assert review.support_surface_keys == ("Y_MIN",)
    assert review.load_surface_keys == ("Z_MAX",)
    assert review.support_named_selection_sha256 != review.load_named_selection_sha256
    assert review.support_binding_sha256 == prepared["support_binding"].binding_sha256
    assert review.load_binding_sha256 == prepared["load_binding"].binding_sha256


def test_overlapping_support_load_named_scope_blocks_review(tmp_path: Path) -> None:
    step = tmp_path / "box.step"; _write_box(step)
    with pytest.raises(PreSolveReviewError, match="overlap"):
        prepare_step_analysis(
            step,
            mesh_size_mm=20.0,
            resultant_n=(1000.0, 0.0, 0.0),
            support_surface_keys=("X_MIN", "Y_MIN"),
            load_surface_keys=("Y_MIN",),
        )


def test_solve_uses_reviewed_non_x_named_scope_bindings(tmp_path: Path) -> None:
    step = tmp_path / "box.step"; _write_box(step)
    prepared = prepare_step_analysis(
        step,
        mesh_size_mm=20.0,
        resultant_n=(0.0, 0.0, 1000.0),
        support_surface_keys=("Y_MIN",),
        load_surface_keys=("Z_MAX",),
    )
    accepted = accept_model_preparation(prepared["review"])
    summary = solve_prepared_analysis(prepared, accepted, tmp_path / "result")
    assert summary["scope_contract"]["support_surface_keys"] == ["Y_MIN"]
    assert summary["scope_contract"]["load_surface_keys"] == ["Z_MAX"]
    assert summary["scope_contract"]["support_binding_sha256"] == prepared["support_binding"].binding_sha256
    assert summary["scope_contract"]["load_binding_sha256"] == prepared["load_binding"].binding_sha256
    assert summary["claims"] == {"converged": False, "industrial_validation": False, "ansys_equivalence": False}
