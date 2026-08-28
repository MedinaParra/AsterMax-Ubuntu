from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from astermax.fea.arbitrary_picker_review import (
    ArbitraryPickerReviewError,
    build_arbitrary_picker_review_snapshot,
)
from astermax.fea.cad_face_picker import build_cad_face_picker_catalog
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.native_cad_picker_ui import build_native_picker_assignment
from astermax.fea.persistent_geometry import list_face_signatures
from astermax.fea.production_picker_routing import prepare_picker_routed_model


def _write_sloped_prism(path: Path) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c5_3d_sloped_prism")
        p1 = gmsh.model.occ.addPoint(0.0, 0.0, 0.0)
        p2 = gmsh.model.occ.addPoint(40.0, 0.0, 0.0)
        p3 = gmsh.model.occ.addPoint(0.0, 0.0, 20.0)
        l1 = gmsh.model.occ.addLine(p1, p2); l2 = gmsh.model.occ.addLine(p2, p3); l3 = gmsh.model.occ.addLine(p3, p1)
        loop = gmsh.model.occ.addCurveLoop([l1, l2, l3])
        face = gmsh.model.occ.addPlaneSurface([loop])
        gmsh.model.occ.extrude([(2, face)], 0.0, 12.0, 0.0)
        gmsh.model.occ.synchronize(); gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _sloped_signature(step: Path) -> str:
    candidates = []
    for _tag, signature in list_face_signatures(step):
        b = signature.bbox_mm
        spans = np.asarray((b[3] - b[0], b[4] - b[1], b[5] - b[2]), dtype=float)
        if np.count_nonzero(spans > 1.0) == 3:
            candidates.append(signature.sha256)
    assert len(candidates) == 1
    return candidates[0]


def _prepared(step: Path):
    inventory = mesh_step_tet10_with_face_ownership(step, 12.0)
    catalog = build_cad_face_picker_catalog(inventory)
    sloped_sha = _sloped_signature(step)
    load_face = next(face for face in catalog.faces if face.signature_sha256 == sloped_sha)
    support_face = next(face for face in catalog.faces if face.signature_sha256 != sloped_sha)
    assignment = build_native_picker_assignment(
        step, inventory, catalog,
        support_face_ids=(support_face.face_id,), load_face_ids=(load_face.face_id,),
    )
    return prepare_picker_routed_model(step, assignment, mesh_size_mm=12.0), assignment, sloped_sha


def test_arbitrary_review_preserves_sloped_picker_provenance(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    prepared, assignment, sloped_sha = _prepared(step)
    snapshot = build_arbitrary_picker_review_snapshot(prepared)
    assert snapshot.load_face_signature_sha256 == (sloped_sha,)
    assert snapshot.load_binding_sha256 == assignment.load_binding.binding_sha256
    assert snapshot.support_binding_sha256 == assignment.support_binding.binding_sha256
    assert snapshot.load_tri6_count == assignment.load_binding.tri6_count
    assert snapshot.support_tri6_count == assignment.support_binding.tri6_count
    assert any(row["role"] == "LOAD" and row["face_signature_sha256"] == sloped_sha for row in snapshot.projected_faces)
    assert snapshot.mean_ratio_crosscheck_verified is True
    assert snapshot.converged is False
    assert snapshot.industrial_validation is False
    assert snapshot.ansys_equivalence is False


def test_arbitrary_review_snapshot_is_deterministic(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    prepared, _, _ = _prepared(step)
    first = build_arbitrary_picker_review_snapshot(prepared)
    second = build_arbitrary_picker_review_snapshot(prepared)
    assert first.snapshot_sha256 == second.snapshot_sha256
    assert first.projected_faces == second.projected_faces


def test_arbitrary_review_fails_closed_on_stale_ownership_evidence(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    prepared, _, _ = _prepared(step)
    prepared["evidence"] = replace(prepared["evidence"], ownership_sha256="0" * 64)
    with pytest.raises(ArbitraryPickerReviewError, match="PICKER_REVIEW_OWNERSHIP_STALE"):
        build_arbitrary_picker_review_snapshot(prepared)
