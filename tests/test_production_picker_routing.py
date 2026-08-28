from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from astermax.fea.cad_face_picker import build_cad_face_picker_catalog
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.native_cad_picker_ui import build_native_picker_assignment
from astermax.fea.persistent_geometry import list_face_signatures
from astermax.fea.production_picker_routing import (
    ProductionPickerRoutingError,
    prepare_picker_routed_model,
    solve_picker_routed_model,
    verify_picker_route,
)


def _write_sloped_prism(path: Path) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c5_3c_sloped_prism")
        p1 = gmsh.model.occ.addPoint(0.0, 0.0, 0.0)
        p2 = gmsh.model.occ.addPoint(40.0, 0.0, 0.0)
        p3 = gmsh.model.occ.addPoint(0.0, 0.0, 20.0)
        l1 = gmsh.model.occ.addLine(p1, p2)
        l2 = gmsh.model.occ.addLine(p2, p3)
        l3 = gmsh.model.occ.addLine(p3, p1)
        loop = gmsh.model.occ.addCurveLoop([l1, l2, l3])
        face = gmsh.model.occ.addPlaneSurface([loop])
        gmsh.model.occ.extrude([(2, face)], 0.0, 12.0, 0.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _sloped_signature(step: Path) -> str:
    candidates = []
    for _tag, signature in list_face_signatures(step):
        bbox = signature.bbox_mm
        spans = np.asarray((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), dtype=float)
        if np.count_nonzero(spans > 1.0) == 3:
            candidates.append(signature.sha256)
    assert len(candidates) == 1
    return candidates[0]


def _assignment(step: Path, mesh_size_mm: float = 12.0):
    inventory = mesh_step_tet10_with_face_ownership(step, mesh_size_mm)
    catalog = build_cad_face_picker_catalog(inventory)
    sloped_sha = _sloped_signature(step)
    load_face = next(face for face in catalog.faces if face.signature_sha256 == sloped_sha)
    support_face = next(face for face in catalog.faces if face.signature_sha256 != sloped_sha)
    assignment = build_native_picker_assignment(
        step,
        inventory,
        catalog,
        support_face_ids=(support_face.face_id,),
        load_face_ids=(load_face.face_id,),
    )
    return assignment, sloped_sha


def test_picker_route_preserves_sloped_face_to_production_sparse_solver(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    assignment, sloped_sha = _assignment(step)
    prepared = prepare_picker_routed_model(step, assignment, mesh_size_mm=12.0)
    route = verify_picker_route(prepared)
    assert assignment.load_binding.face_signature_sha256 == (sloped_sha,)
    assert route.load_binding_sha256 == assignment.load_binding.binding_sha256
    assert route.support_binding_sha256 == assignment.support_binding.binding_sha256
    assert "surface_keys" not in route.__dataclass_fields__

    solved = solve_picker_routed_model(
        prepared,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    evidence = solved["solve_evidence"]
    assert evidence.load_binding_sha256 == route.load_binding_sha256
    assert evidence.support_binding_sha256 == route.support_binding_sha256
    assert evidence.converged is False
    assert evidence.industrial_validation is False
    assert evidence.ansys_equivalence is False


def test_picker_route_is_deterministic_for_same_assignment(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    assignment, _ = _assignment(step)
    first = prepare_picker_routed_model(step, assignment, mesh_size_mm=12.0)
    second = prepare_picker_routed_model(step, assignment, mesh_size_mm=12.0)
    assert first["production_picker_route"].route_sha256 == second["production_picker_route"].route_sha256
    assert first["evidence"].support_binding_sha256 == second["evidence"].support_binding_sha256
    assert first["evidence"].load_binding_sha256 == second["evidence"].load_binding_sha256


def test_picker_route_fails_closed_if_step_changes_after_assignment(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    assignment, _ = _assignment(step)
    step.write_text(step.read_text(encoding="utf-8") + "\n/* changed */\n", encoding="utf-8")
    with pytest.raises(ProductionPickerRoutingError, match="PICKER_ROUTE_SUPPORT_STEP_STALE"):
        prepare_picker_routed_model(step, assignment, mesh_size_mm=12.0)


def test_picker_route_fails_closed_if_route_sha_is_tampered(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    assignment, _ = _assignment(step)
    prepared = prepare_picker_routed_model(step, assignment, mesh_size_mm=12.0)
    prepared["production_picker_route"] = replace(prepared["production_picker_route"], route_sha256="0" * 64)
    with pytest.raises(ProductionPickerRoutingError, match="PICKER_ROUTE_SHA_MISMATCH"):
        verify_picker_route(prepared)


def test_picker_route_fails_closed_if_binding_evidence_is_tampered(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    assignment, _ = _assignment(step)
    prepared = prepare_picker_routed_model(step, assignment, mesh_size_mm=12.0)
    evidence = prepared["evidence"]
    prepared["evidence"] = replace(evidence, load_binding_sha256="f" * 64)
    with pytest.raises(ProductionPickerRoutingError, match="PICKER_ROUTE_LOAD_BINDING_STALE"):
        verify_picker_route(prepared)
