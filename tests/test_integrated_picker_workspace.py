from pathlib import Path

import numpy as np
import pytest

from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.integrated_picker_workspace import (
    IntegratedPickerWorkspaceError,
    build_integrated_picker_catalog,
    commit_integrated_picker_assignment,
    verify_integrated_picker_snapshot,
)
from astermax.fea.native_cad_picker_ui import build_native_picker_assignment
from astermax.fea.persistent_geometry import list_face_signatures


def _write_sloped_prism(path: Path) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c60_g1_integrated_picker")
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


def test_integrated_workspace_commits_real_sloped_picker_to_adaptive_preparation(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    snapshot, inventory, catalog = build_integrated_picker_catalog(
        step,
        mesh_size_mm=12.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    sloped_sha = _sloped_signature(step)
    load_face = next(face for face in catalog.faces if face.signature_sha256 == sloped_sha)
    support_face = next(face for face in catalog.faces if face.signature_sha256 != sloped_sha)
    assignment = build_native_picker_assignment(
        step, inventory, catalog,
        support_face_ids=(support_face.face_id,),
        load_face_ids=(load_face.face_id,),
    )
    committed = commit_integrated_picker_assignment(
        step, snapshot, inventory, catalog, assignment,
        mesh_size_mm=12.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    assert committed.load_face_ids == (load_face.face_id,)
    assert committed.evidence.load_face_signature_sha256 == (sloped_sha,)
    assert committed.prepared["load_binding"].face_signature_sha256 == (sloped_sha,)
    assert committed.evidence.global_analysis_converged is False
    assert committed.evidence.industrial_validation is False
    assert committed.evidence.ansys_equivalence is False


def test_integrated_workspace_fails_closed_if_material_or_load_changes_after_picker_build(tmp_path: Path) -> None:
    step = tmp_path / "stale.step"; _write_sloped_prism(step)
    snapshot, _inventory, _catalog = build_integrated_picker_catalog(
        step,
        mesh_size_mm=12.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    with pytest.raises(IntegratedPickerWorkspaceError, match="INTEGRATED_PICKER_CONTEXT_STALE"):
        verify_integrated_picker_snapshot(
            snapshot, step,
            mesh_size_mm=12.0,
            young_modulus_mpa=210000.0,
            poisson_ratio=0.30,
            resultant_n=(0.0, -1000.0, 0.0),
        )
    with pytest.raises(IntegratedPickerWorkspaceError, match="INTEGRATED_PICKER_CONTEXT_STALE"):
        verify_integrated_picker_snapshot(
            snapshot, step,
            mesh_size_mm=12.0,
            young_modulus_mpa=200000.0,
            poisson_ratio=0.30,
            resultant_n=(0.0, -1200.0, 0.0),
        )


def test_integrated_workspace_fails_closed_if_step_bytes_change(tmp_path: Path) -> None:
    step = tmp_path / "changed.step"; _write_sloped_prism(step)
    snapshot, _inventory, _catalog = build_integrated_picker_catalog(
        step,
        mesh_size_mm=12.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    step.write_bytes(step.read_bytes() + b"\n/* changed after picker */\n")
    with pytest.raises(IntegratedPickerWorkspaceError, match="INTEGRATED_PICKER_CONTEXT_STALE"):
        verify_integrated_picker_snapshot(
            snapshot, step,
            mesh_size_mm=12.0,
            young_modulus_mpa=200000.0,
            poisson_ratio=0.30,
            resultant_n=(0.0, -1000.0, 0.0),
        )
