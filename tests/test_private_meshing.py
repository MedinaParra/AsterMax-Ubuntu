from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from astermax.solver.private_meshing import (
    MeshSizingV1,
    PrivateStepMeshRequestV1,
    generate_private_meshing_pack,
    render_gmsh_python_job,
    validate_private_step,
)


def _request(path: Path, *, sha256: str | None = None) -> PrivateStepMeshRequestV1:
    digest = sha256 or hashlib.sha256(path.read_bytes()).hexdigest()
    return PrivateStepMeshRequestV1(
        step_path=str(path),
        step_sha256=digest,
        interface_plane_x_mm=-951.0,
        sizing=MeshSizingV1(
            global_size_mm=12.0,
            interface_size_mm=4.0,
            interface_refine_distance_mm=30.0,
            element_order=2,
        ),
    )


def _embedded_cfg(script: str) -> dict:
    tree = ast.parse(script)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "CFG" for target in node.targets):
            continue
        call = node.value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "json"
            and call.func.attr == "loads"
            and len(call.args) == 1
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
        ):
            return json.loads(call.args[0].value)
    raise AssertionError("generated script does not contain a statically auditable CFG payload")


def test_private_step_hash_must_match(tmp_path: Path) -> None:
    step = tmp_path / "private.step"
    step.write_bytes(b"PRIVATE STEP FIXTURE")
    request = _request(step, sha256="0" * 64)
    with pytest.raises(ValueError, match="STEP SHA-256 mismatch"):
        validate_private_step(request)


def test_interface_size_cannot_exceed_global_size() -> None:
    with pytest.raises(ValidationError):
        MeshSizingV1(
            global_size_mm=4.0,
            interface_size_mm=8.0,
            interface_refine_distance_mm=20.0,
        )


def test_rendered_job_is_fail_closed_and_never_scales_or_heals(tmp_path: Path) -> None:
    step = tmp_path / "private.step"
    step.write_bytes(b"PRIVATE STEP FIXTURE")
    script = render_gmsh_python_job(_request(step))

    assert "expected_solid_count" in script
    assert "segment volume signature mismatch" in script
    assert "authenticated hub posterior interface plane not found" in script
    assert "gmsh.model.occ.getMass" in script
    assert "HUB_POSTERIOR_INTERFACE" in script
    assert "SEGMENT_POSTERIOR_INTERFACE" in script
    assert "gmsh.model.mesh.generate(3)" in script
    assert "gmsh.model.mesh.setOrder(2)" in script
    assert "EXPLORATORY_NOT_FOR_ACCEPTANCE" in script
    assert "authentic_solver_authorized" in script
    assert "gmsh.model.occ.fragment" not in script
    assert "gmsh.model.occ.fuse" not in script
    assert "OCCScaling" not in script


def test_pack_generation_preserves_hash_and_quarantine(tmp_path: Path) -> None:
    step = tmp_path / "private.step"
    step.write_bytes(b"PRIVATE STEP FIXTURE")
    request = _request(step)
    output = tmp_path / "pack"

    pack = generate_private_meshing_pack(request, output)

    assert pack.source_step_sha256 == request.step_sha256
    assert pack.authentic_solver_authorized is False
    assert pack.exploratory_result_class == "EXPLORATORY_NOT_FOR_ACCEPTANCE"
    assert (output / "mesh_private_step.py").is_file()
    assert (output / "mesh_request.json").is_file()
    assert (output / "meshing_pack_manifest.json").is_file()
    assert not (output / pack.output_mesh_name).exists()


def test_generated_job_does_not_embed_private_step_bytes(tmp_path: Path) -> None:
    step = tmp_path / "private.step"
    private_bytes = b"CONFIDENTIAL_GEOMETRY_BYTES_SHOULD_NEVER_BE_IN_SCRIPT"
    step.write_bytes(private_bytes)
    script = render_gmsh_python_job(_request(step))

    assert private_bytes.decode() not in script
    cfg = _embedded_cfg(script)
    assert cfg["step_path"] == str(step)
    assert cfg["step_sha256"] == hashlib.sha256(private_bytes).hexdigest()


def test_coordinate_units_are_explicitly_mm(tmp_path: Path) -> None:
    step = tmp_path / "private.step"
    step.write_bytes(b"PRIVATE STEP FIXTURE")
    request = _request(step)
    assert request.coordinate_unit == "mm"
    script = render_gmsh_python_job(request)
    assert _embedded_cfg(script)["coordinate_unit"] == "mm"
