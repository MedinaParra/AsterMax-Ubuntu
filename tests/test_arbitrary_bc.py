from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from astermax.fea.arbitrary_bc import ArbitraryBcError, prepare_arbitrary_bc_model, solve_arbitrary_bc_model
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.persistent_geometry import list_face_signatures


def _write_sloped_prism(path: Path) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c5_2b_sloped_prism")
        p1 = gmsh.model.occ.addPoint(0.0, 0.0, 0.0)
        p2 = gmsh.model.occ.addPoint(40.0, 0.0, 0.0)
        p3 = gmsh.model.occ.addPoint(0.0, 0.0, 20.0)
        l1 = gmsh.model.occ.addLine(p1, p2)
        l2 = gmsh.model.occ.addLine(p2, p3)
        l3 = gmsh.model.occ.addLine(p3, p1)
        loop = gmsh.model.occ.addCurveLoop([l1, l2, l3])
        face = gmsh.model.occ.addPlaneSurface([loop])
        gmsh.model.occ.extrude([(2, face)], 0.0, 12.0, 0.0)
        gmsh.model.occ.synchronize(); gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _scope_tags(step: Path) -> tuple[int, int]:
    signatures = list_face_signatures(step)
    sloped = []
    y_min = []
    for tag, signature in signatures:
        bbox = np.asarray(signature.bbox_mm, dtype=float)
        spans = bbox[3:] - bbox[:3]
        if np.count_nonzero(spans > 1.0) == 3:
            sloped.append(tag)
        if spans[1] < 1.0e-3 and abs(signature.center_mm[1]) < 1.0e-3:
            y_min.append(tag)
    assert len(sloped) == 1 and len(y_min) == 1
    return y_min[0], sloped[0]


def test_sloped_cad_face_is_exact_load_scope_consumed_by_sparse_solver(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    support_tag, sloped_tag = _scope_tags(step)
    support = capture_named_selection(step, (support_tag,), "Fixture", "SUPPORT")
    load = capture_named_selection(step, (sloped_tag,), "Sloped Pressure Resultant", "LOAD")
    prepared = prepare_arbitrary_bc_model(step, mesh_size_mm=12.0, support_selection=support, load_selection=load)

    evidence = prepared["evidence"]
    assert evidence.load_face_signature_sha256 == (load.faces[0].signature_sha256,)
    assert evidence.support_face_signature_sha256 == (support.faces[0].signature_sha256,)
    assert evidence.load_binding_sha256 == prepared["load_binding"].binding_sha256
    assert evidence.load_tri6_count == prepared["load_triangles"].shape[0] > 0
    assert evidence.tetra_quality_crosscheck_verified is True

    solved = solve_arbitrary_bc_model(
        prepared,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    solve_evidence = solved["solve_evidence"]
    assert solve_evidence.load_binding_sha256 == prepared["load_binding"].binding_sha256
    assert solve_evidence.support_binding_sha256 == prepared["support_binding"].binding_sha256
    assert solve_evidence.fixed_node_count > 0
    assert solve_evidence.force_residual_n < 1.0e-5
    assert solve_evidence.moment_residual_nmm < 1.0e-3
    assert solve_evidence.converged is False
    assert solve_evidence.industrial_validation is False
    assert solve_evidence.ansys_equivalence is False


def test_overlapping_arbitrary_support_and_load_fail_closed(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    support_tag, _ = _scope_tags(step)
    support = capture_named_selection(step, (support_tag,), "Fixture", "SUPPORT")
    same_face_load = capture_named_selection(step, (support_tag,), "Load", "LOAD")
    with pytest.raises(ArbitraryBcError, match="OVERLAP"):
        prepare_arbitrary_bc_model(step, mesh_size_mm=12.0, support_selection=support, load_selection=same_face_load)


def test_tampered_binding_blocks_solve(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    support_tag, sloped_tag = _scope_tags(step)
    support = capture_named_selection(step, (support_tag,), "Fixture", "SUPPORT")
    load = capture_named_selection(step, (sloped_tag,), "Load", "LOAD")
    prepared = prepare_arbitrary_bc_model(step, mesh_size_mm=12.0, support_selection=support, load_selection=load)
    prepared["support_binding"] = replace(prepared["support_binding"], binding_sha256="0" * 64)
    with pytest.raises(ArbitraryBcError, match="BINDING_STALE"):
        solve_arbitrary_bc_model(prepared, young_modulus_mpa=200000.0, poisson_ratio=0.30, resultant_n=(0.0, -1000.0, 0.0))
