from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from astermax.solver.exploratory_gap_closure import (
    ExploratoryGapClosureRequestV1,
    ExploratoryMaterialV1,
    equivalent_clamp_traction_mpa,
    generate_gap_closure_pack,
    load_verified_mesh_evidence,
    render_code_aster_comm,
)
from astermax.solver.private_meshing import (
    MeshSizingV1,
    PrivateStepMeshRequestV1,
    render_gmsh_python_job,
)


REQUIRED_GROUPS = [
    "HUB",
    "SEGMENTS",
    "HUB_POSTERIOR_INTERFACE",
    "SEGMENT_POSTERIOR_INTERFACE",
    "HUB_INNER_BORE",
    "SEGMENT_OUTER_CLAMP",
]


def _material(name: str, e: float) -> ExploratoryMaterialV1:
    return ExploratoryMaterialV1(
        designation=name,
        elastic_modulus_mpa=e,
        poisson_ratio=0.29,
    )


def _fixture(tmp_path: Path, *, groups: list[str] | None = None):
    mesh = tmp_path / "private.med"
    mesh.write_bytes(b"PRIVATE MED FIXTURE")
    mesh_sha = hashlib.sha256(mesh.read_bytes()).hexdigest()
    evidence = tmp_path / "mesh_execution_evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "PrivateMeshExecutionEvidenceV1",
                "result_class": "EXPLORATORY_NOT_FOR_ACCEPTANCE",
                "authentic_solver_authorized": False,
                "mesh_sha256": mesh_sha,
                "coordinate_unit": "mm",
                "physical_groups": groups or REQUIRED_GROUPS,
                "segment_outer_clamp_area_mm2": 100000.0,
            }
        ),
        encoding="utf-8",
    )
    request = ExploratoryGapClosureRequestV1(
        case_id="EXP-002",
        mesh_path=str(mesh),
        mesh_sha256=mesh_sha,
        mesh_evidence_path=str(evidence),
        gap_mm=0.25,
        hub_material=_material("SAE 3310 exploratory", 205000.0),
        segment_material=_material("boron steel exploratory", 210000.0),
        preload_per_bolt_kn=198.7,
        bolt_count=30,
        friction_coefficient=0.15,
        increments=20,
    )
    return mesh, evidence, request


def test_equivalent_clamp_traction_preserves_resultant() -> None:
    traction, total_kn = equivalent_clamp_traction_mpa(
        preload_per_bolt_kn=200.0,
        bolt_count=30,
        clamp_area_mm2=120000.0,
    )
    assert total_kn == pytest.approx(6000.0)
    assert traction == pytest.approx(50.0)
    assert traction * 120000.0 / 1000.0 == pytest.approx(total_kn)


def test_mesh_sha_mismatch_fails_closed(tmp_path: Path) -> None:
    mesh, _, request = _fixture(tmp_path)
    mesh.write_bytes(b"TAMPERED MED")
    with pytest.raises(ValueError, match="MED SHA-256 mismatch"):
        load_verified_mesh_evidence(request)


def test_missing_solver_surface_group_fails_closed(tmp_path: Path) -> None:
    groups = [name for name in REQUIRED_GROUPS if name != "HUB_INNER_BORE"]
    _, _, request = _fixture(tmp_path, groups=groups)
    with pytest.raises(ValueError, match="required physical groups missing"):
        load_verified_mesh_evidence(request)


def test_exploratory_request_cannot_authorize_authentic_evidence(tmp_path: Path) -> None:
    _, _, request = _fixture(tmp_path)
    payload = request.model_dump()
    payload["authentic_solver_authorized"] = True
    with pytest.raises(ValidationError):
        ExploratoryGapClosureRequestV1.model_validate(payload)


def test_comm_contains_nonlinear_contact_but_no_operational_torque(tmp_path: Path) -> None:
    _, _, request = _fixture(tmp_path)
    text = render_code_aster_comm(request, clamp_traction_mpa=42.0)
    assert "EXPLORATORY_NOT_FOR_ACCEPTANCE" in text
    assert "DEFI_CONTACT" in text
    assert "FORMULATION='CONTINUE'" in text
    assert "FROTTEMENT='COULOMB'" in text
    assert "HUB_POSTERIOR_INTERFACE" in text
    assert "SEGMENT_POSTERIOR_INTERFACE" in text
    assert "HUB_INNER_BORE" in text
    assert "SEGMENT_OUTER_CLAMP" in text
    assert "STAT_NON_LINE" in text
    assert "FONC_MULT=RAMPE" in text
    assert "CONT_NOEU" in text
    assert "SIGM_ELNO" in text
    assert "MOMENT" not in text
    assert "FORCE_NODALE" not in text


def test_generated_pack_keeps_quarantine_and_hashes_files(tmp_path: Path) -> None:
    _, _, request = _fixture(tmp_path)
    out = tmp_path / "pack"
    pack = generate_gap_closure_pack(request, out)
    assert pack.authentic_solver_authorized is False
    assert pack.result_class == "EXPLORATORY_NOT_FOR_ACCEPTANCE"
    assert pack.total_equivalent_clamp_force_kn == pytest.approx(5961.0)
    assert pack.clamp_traction_mpa == pytest.approx(59.61)
    assert len(pack.quarantine_reasons) >= 5
    assert (out / "EXP-002_gap_closure.comm").is_file()
    assert (out / "EXP-002_gap_closure.export").is_file()
    assert (out / "gap_closure_pack_manifest.json").is_file()
    assert not (out / pack.output_rmed_name).exists()


def test_w2j_meshing_job_adds_geometric_support_and_clamp_groups(tmp_path: Path) -> None:
    step = tmp_path / "private.step"
    step.write_bytes(b"PRIVATE STEP FIXTURE")
    request = PrivateStepMeshRequestV1(
        step_path=str(step),
        step_sha256=hashlib.sha256(step.read_bytes()).hexdigest(),
        interface_plane_x_mm=-951.0,
        sizing=MeshSizingV1(
            global_size_mm=12.0,
            interface_size_mm=4.0,
            interface_refine_distance_mm=30.0,
            element_order=2,
        ),
    )
    script = render_gmsh_python_job(request)
    assert "HUB_INNER_BORE" in script
    assert "SEGMENT_OUTER_CLAMP" in script
    assert "centered_x_cylinder_radius" in script
    assert "segment_outer_clamp_area_mm2" in script
    assert "gmsh.model.getType" in script
    assert "gmsh.model.occ.fuse" not in script
    assert "gmsh.model.occ.fragment" not in script
