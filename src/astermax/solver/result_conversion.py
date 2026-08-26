from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from astermax.solver.bridge import verify_artifact
from astermax.solver.contracts import (
    ArtifactDigestV1,
    FieldLocation,
    SolverRequestV1,
    SolverRunManifestV1,
    SolverTermination,
)
from astermax.solver.conversion_contracts import (
    ConversionFieldInventoryV1,
    ResultConversionManifestV1,
)
from astermax.solver.errors import SolverEvidenceError
from astermax.solver.med_result import CONVERTER_VERSION, read_code_aster_rmed
from astermax.solver.result_loader import ResultDescriptorV1, ResultFieldDescriptorV1
from astermax.solver.vtu_export import write_vtu

CONVERTER_ID = "astermax.med_to_vtu"


def _canonical_json_bytes(model: BaseModel) -> bytes:
    return (
        json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _artifact(root: Path, relative_path: str, media_type: str) -> ArtifactDigestV1:
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SolverEvidenceError(f"postprocess artifact escapes run directory: {relative_path}") from exc
    if not candidate.is_file():
        raise SolverEvidenceError(f"missing postprocess artifact: {relative_path}")
    data = candidate.read_bytes()
    return ArtifactDigestV1(
        relative_path=relative_path,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
        media_type=media_type,
    )


def _validated_manifest_sha256(root: Path, manifest: SolverRunManifestV1) -> str:
    if manifest.termination != SolverTermination.SUCCEEDED:
        raise SolverEvidenceError("cannot convert a non-successful solver run")
    manifest_path = root / "output" / "manifest.json"
    if not manifest_path.is_file():
        raise SolverEvidenceError("missing persisted solver manifest")
    persisted = SolverRunManifestV1.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if persisted != manifest:
        raise SolverEvidenceError("persisted solver manifest differs from validated manifest")
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def convert_rmed_result(
    run_directory: Path,
    request: SolverRequestV1,
    manifest: SolverRunManifestV1,
    *,
    source_relative_path: str,
    vtu_relative_path: str = "output/result.vtu",
) -> ResultConversionManifestV1:
    root = run_directory.resolve()
    manifest_sha256 = _validated_manifest_sha256(root, manifest)
    if manifest.run_id != request.run_id or manifest.request_id != request.request_id:
        raise SolverEvidenceError("solver manifest identity does not match conversion request")

    outputs_by_path = {artifact.relative_path: artifact for artifact in manifest.output_artifacts}
    source_artifact = outputs_by_path.get(source_relative_path)
    if source_artifact is None:
        raise SolverEvidenceError("requested RMED is not declared by solver manifest")
    verify_artifact(root, source_artifact)

    started_at = datetime.now(timezone.utc)
    med_result = read_code_aster_rmed(
        root / source_artifact.relative_path,
        expected_sha256=source_artifact.sha256,
    )
    vtu_path = (root / vtu_relative_path).resolve()
    try:
        vtu_path.relative_to(root)
    except ValueError as exc:
        raise SolverEvidenceError("VTU output escapes run directory") from exc

    export = write_vtu(med_result, vtu_path, relative_path=vtu_relative_path)
    vtu_artifact = _artifact(root, vtu_relative_path, "application/vnd.vtk.vtu+xml")

    descriptor_fields: list[ResultFieldDescriptorV1] = []
    field_inventory: list[ConversionFieldInventoryV1] = []
    for field in export.fields:
        if field.source_association == "NOE":
            location = FieldLocation.NODAL
        elif field.source_association.startswith("NOE."):
            location = FieldLocation.ELEMENT_NODAL
        else:
            raise SolverEvidenceError(
                f"unsupported converted field association: {field.source_association}"
            )
        metadata = {
            "source_association": field.source_association,
            "source_dataset_path": field.source_dataset_path,
            "source_raw_shape": list(field.raw_shape),
            "vtk_array_name": field.vtk_array_name,
            "vtk_scope": field.vtk_scope,
            "derived_vtk_array_names": list(field.derived_vtk_array_names),
            "evidence_class": "SOLVER_RESULT",
        }
        descriptor_fields.append(
            ResultFieldDescriptorV1(
                name=field.source_field_name,
                location=location,
                components=list(field.components),
                unit=field.unit,
                artifact_path=vtu_artifact.relative_path,
                artifact_sha256=vtu_artifact.sha256,
                artifact_byte_size=vtu_artifact.byte_size,
                metadata=metadata,
            )
        )
        field_inventory.append(
            ConversionFieldInventoryV1(
                source_field_name=field.source_field_name,
                source_association=field.source_association,
                source_dataset_path=field.source_dataset_path,
                components=list(field.components),
                unit=field.unit,
                raw_shape=list(field.raw_shape),
                vtk_array_name=field.vtk_array_name,
                vtk_scope=field.vtk_scope,
                derived_vtk_array_names=list(field.derived_vtk_array_names),
            )
        )

    descriptor = ResultDescriptorV1(
        fields=descriptor_fields,
        source_manifest_sha256=manifest_sha256,
        source_artifact_path=source_artifact.relative_path,
        source_artifact_sha256=source_artifact.sha256,
        converter_version=CONVERTER_VERSION,
        metadata={
            "source_med_version": list(med_result.med_version),
            "source_mesh_name": med_result.mesh_name,
            "point_count": export.point_count,
            "cell_count": export.cell_count,
            "raw_values_preserved": True,
        },
    )
    descriptor_path = root / "output" / "result_descriptor.json"
    descriptor_path.write_bytes(_canonical_json_bytes(descriptor))
    descriptor_artifact = _artifact(root, "output/result_descriptor.json", "application/json")

    conversion_manifest = ResultConversionManifestV1(
        run_id=request.run_id,
        request_id=request.request_id,
        converter_id=CONVERTER_ID,
        converter_version=CONVERTER_VERSION,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        source_run_manifest_sha256=manifest_sha256,
        source_artifact=source_artifact,
        output_artifacts=[vtu_artifact, descriptor_artifact],
        fields=field_inventory,
        metadata={
            "value_preservation": (
                "raw arrays serialized with 17 significant digits; exact IEEE-754 "
                "round-trip is required by deterministic tests"
            ),
        },
    )
    conversion_path = root / "output" / "conversion_manifest.json"
    conversion_path.write_bytes(_canonical_json_bytes(conversion_manifest))
    return conversion_manifest
