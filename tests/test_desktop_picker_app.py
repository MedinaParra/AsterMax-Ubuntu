from pathlib import Path

import numpy as np
import pytest

from astermax.desktop_picker_app import (
    desktop_input_contract,
    prepare_desktop_picker_model,
    solve_desktop_picker_model,
    verify_desktop_live_results,
    verify_desktop_picker_model,
)
from astermax.fea.cad_face_picker import build_cad_face_picker_catalog
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.native_cad_picker_ui import build_native_picker_assignment
from astermax.fea.persistent_geometry import list_face_signatures


def _write_sloped_prism(path: Path) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c5_3e_desktop_sloped_prism")
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


def test_desktop_cutover_preserves_sloped_picker_provenance_through_native_results(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    assignment, sloped_sha = _assignment(step)
    contract = desktop_input_contract(
        step,
        mesh_size_mm=12.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    prepared = prepare_desktop_picker_model(contract, assignment)
    verify_desktop_picker_model(prepared, contract)
    review = prepared["desktop_picker_review"]
    route = prepared["production_picker_route"]
    assert review.load_face_signature_sha256 == (sloped_sha,)
    assert review.load_binding_sha256 == assignment.load_binding.binding_sha256
    assert route.load_binding_sha256 == assignment.load_binding.binding_sha256

    summary = solve_desktop_picker_model(prepared, contract, tmp_path / "results")
    verify_desktop_live_results(summary)
    assert summary["schema"] == "AsterMaxDesktopPickerResultV2"
    assert summary["scope_contract"]["authoring"] == "NATIVE_CAD_FACE_PICKER_PERSISTENT_SIGNATURE"
    assert summary["scope_contract"]["load_binding_sha256"] == assignment.load_binding.binding_sha256
    assert summary["solve_evidence"]["load_binding_sha256"] == assignment.load_binding.binding_sha256
    results = summary["production_results"]
    runtime = summary["_runtime_results"]
    assert results["solve_evidence_sha256"] == summary["solve_evidence"]["solve_evidence_sha256"]
    assert results["workspace_sha256"] == runtime["workspace"].workspace_sha256
    assert runtime["initial_payload"].workspace_sha256 == results["workspace_sha256"]
    assert runtime["initial_payload"].solve_evidence_sha256 == results["solve_evidence_sha256"]
    assert results["displacement_field"] == "U_MAG"
    assert results["stress_field"] == "VON_MISES_IP_MAX"
    assert results["stress_representation"] == "FOUR_TET10_INTEGRATION_POINTS_ELEMENT_MAX_NO_NODAL_SMOOTHING"
    assert Path(summary["artifacts"]["vtu"]).is_file()
    assert Path(summary["artifacts"]["viewer"]).is_file()
    assert Path(summary["artifacts"]["summary"]).is_file()
    persisted = Path(summary["artifacts"]["summary"]).read_text(encoding="utf-8")
    assert results["bundle_sha256"] in persisted
    assert results["workspace_sha256"] in persisted
    assert "_runtime_results" not in persisted
    assert summary["claims"] == {"converged": False, "industrial_validation": False, "ansys_equivalence": False}


def test_desktop_live_results_fail_closed_on_provenance_tamper(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    assignment, _ = _assignment(step)
    contract = desktop_input_contract(
        step,
        mesh_size_mm=12.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    summary = solve_desktop_picker_model(
        prepare_desktop_picker_model(contract, assignment), contract, tmp_path / "results"
    )
    tampered = dict(summary)
    tampered["production_results"] = dict(summary["production_results"])
    tampered["production_results"]["workspace_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="DESKTOP_RESULTS_WORKSPACE_STALE"):
        verify_desktop_live_results(tampered)


def test_desktop_cutover_fails_closed_when_reviewed_inputs_change(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    assignment, _ = _assignment(step)
    contract = desktop_input_contract(
        step,
        mesh_size_mm=12.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    prepared = prepare_desktop_picker_model(contract, assignment)
    changed = dict(contract); changed["resultant_n"] = (0.0, -900.0, 0.0)
    with pytest.raises(ValueError, match="DESKTOP_PICKER_INPUTS_CHANGED_AFTER_REVIEW"):
        verify_desktop_picker_model(prepared, changed)


def test_desktop_contract_rejects_zero_resultant(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    with pytest.raises(ValueError, match="Resultant load must be non-zero"):
        desktop_input_contract(
            step,
            mesh_size_mm=12.0,
            young_modulus_mpa=200000.0,
            poisson_ratio=0.30,
            resultant_n=(0.0, 0.0, 0.0),
        )
