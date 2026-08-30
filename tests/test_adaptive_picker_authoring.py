from pathlib import Path

import numpy as np
import pytest

from astermax.fea.adaptive_picker_authoring import (
    AdaptivePickerAuthoringError,
    build_adaptive_picker_catalog,
    prepare_adaptive_model_from_picker,
    verify_adaptive_picker_authoring,
)
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.native_adaptive_analysis import (
    execute_native_adaptive_analysis,
    prepare_native_adaptive_analysis,
    verify_native_adaptive_analysis_receipt,
)
from astermax.fea.persistent_geometry import list_face_signatures
from astermax.fea.pre_solve_review import accept_model_preparation


def _write_sloped_prism(path: Path) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55y_sloped_picker_adaptive")
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
    matches = []
    for _tag, signature in list_face_signatures(step):
        bbox = signature.bbox_mm
        spans = np.asarray((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), dtype=float)
        if np.count_nonzero(spans > 1.0) == 3:
            matches.append(signature.sha256)
    assert len(matches) == 1
    return matches[0]


def _picker_prepared(tmp_path: Path):
    step = tmp_path / "sloped_picker_adaptive.step"
    _write_sloped_prism(step)
    inventory, catalog = build_adaptive_picker_catalog(step, mesh_size_mm=12.0)
    sloped_sha = _sloped_signature(step)
    load_face = next(face for face in catalog.faces if face.signature_sha256 == sloped_sha)
    support_face = min(
        (face for face in catalog.faces if face.signature_sha256 != sloped_sha),
        key=lambda face: face.center_mm[0],
    )
    prepared, evidence = prepare_adaptive_model_from_picker(
        step,
        inventory,
        catalog,
        support_face_ids=(support_face.face_id,),
        load_face_ids=(load_face.face_id,),
        mesh_size_mm=12.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    return step, prepared, evidence, sloped_sha


def test_arbitrary_sloped_picker_signatures_reach_native_adaptive_baseline_and_refined_solve(tmp_path: Path) -> None:
    _step, prepared, evidence, sloped_sha = _picker_prepared(tmp_path)
    verify_adaptive_picker_authoring(prepared, evidence)
    assert evidence.load_face_signature_sha256 == (sloped_sha,)
    assert prepared["load_binding"].face_signature_sha256 == (sloped_sha,)
    assert evidence.minimum_det_jacobian_mm3 > 0.0

    acceptance = accept_model_preparation(prepared["review"])
    context = prepare_native_adaptive_analysis(
        prepared,
        acceptance,
        approver="C5.5y Harness Gate 1",
        approved=True,
        refined_size_factor=0.60,
        maximum_relative_qoi_change=10.0,
        maximum_candidates=2,
        influence_radius_factor=1.5,
    )
    bound = []
    receipt = execute_native_adaptive_analysis(
        prepared,
        acceptance,
        context,
        refinement_approver="C5.5y Harness Gate 2",
        refinement_approved=True,
        output_dir=tmp_path / "results",
        hotspot_binder=lambda view: bound.append(("hotspot", view.visualization_sha256)),
        stress_binder=lambda view: bound.append(("stress", view.comparison_sha256)),
    )
    verify_native_adaptive_analysis_receipt(receipt)
    assert receipt.status == "VERIFIED_ADAPTIVE_RESULTS_READY"
    assert receipt.baseline_mesh_sha256 != receipt.refined_mesh_sha256
    assert receipt.baseline_solve_evidence_sha256 != receipt.refined_solve_evidence_sha256
    assert receipt.global_analysis_converged is False
    assert receipt.industrial_validation is False
    assert receipt.ansys_equivalence is False
    assert [name for name, _sha in bound] == ["hotspot", "stress"]


def test_picker_authoring_rejects_overlap_stale_step_and_tampered_evidence(tmp_path: Path) -> None:
    step = tmp_path / "sloped_picker_negative.step"
    _write_sloped_prism(step)
    inventory, catalog = build_adaptive_picker_catalog(step, mesh_size_mm=12.0)
    face_id = catalog.faces[0].face_id
    with pytest.raises(AdaptivePickerAuthoringError, match="SUPPORT_LOAD_OVERLAP"):
        prepare_adaptive_model_from_picker(
            step, inventory, catalog,
            support_face_ids=(face_id,), load_face_ids=(face_id,),
            mesh_size_mm=12.0, young_modulus_mpa=200000.0, poisson_ratio=0.30,
            resultant_n=(0.0, -1000.0, 0.0),
        )

    _step, prepared, evidence, _sloped = _picker_prepared(tmp_path / "fresh")
    object.__setattr__(evidence, "ansys_equivalence", True)
    with pytest.raises(AdaptivePickerAuthoringError, match="OVERCLAIM"):
        verify_adaptive_picker_authoring(prepared, evidence)
