from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader

from astermax.solver.bridge import verify_artifact
from astermax.solver.contracts import ArtifactDigestV1, SolverResultV1
from astermax.solver.errors import SolverEvidenceError


@dataclass(frozen=True)
class RenderableResultField:
    label: str
    source_field_name: str
    array_name: str
    vtk_association: str
    source_evidence_class: str
    artifact_evidence_class: str
    derived_evidence_class: str
    unit: str | None


def load_verified_vtu(
    run_directory: Path,
    result: SolverResultV1,
):
    """Load exactly one verified VTU artifact referenced by a validated SolverResultV1."""
    root = run_directory.resolve()
    artifacts: dict[tuple[str, str, int], ArtifactDigestV1] = {}
    for field in result.fields:
        artifact = field.artifact
        verify_artifact(root, artifact)
        artifacts[(artifact.relative_path, artifact.sha256, artifact.byte_size)] = artifact

    if len(artifacts) != 1:
        raise SolverEvidenceError(
            "W2B viewport requires all displayed fields to share one verified VTU artifact"
        )
    artifact = next(iter(artifacts.values()))
    if not artifact.relative_path.lower().endswith(".vtu"):
        raise SolverEvidenceError("validated result artifact is not a VTU file")

    path = (root / artifact.relative_path).resolve()
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    grid = reader.GetOutput()
    if grid is None or grid.GetNumberOfPoints() <= 0 or grid.GetNumberOfCells() <= 0:
        raise SolverEvidenceError("verified VTU could not be loaded as a non-empty unstructured grid")
    return grid, artifact


def discover_renderable_fields(result: SolverResultV1, grid) -> list[RenderableResultField]:
    """Expose only provenance-declared scalar arrays suitable for deterministic rendering."""
    renderable: list[RenderableResultField] = []
    for field in result.fields:
        metadata = field.metadata
        if metadata.get("source_evidence_class") != "SOLVER_RESULT":
            raise SolverEvidenceError(f"field lacks solver source evidence: {field.name}")
        if metadata.get("artifact_evidence_class") != "DETERMINISTIC_CALCULATION":
            raise SolverEvidenceError(f"field lacks deterministic artifact evidence: {field.name}")
        if metadata.get("raw_values_preserved") is not True:
            raise SolverEvidenceError(f"field lacks raw-value preservation evidence: {field.name}")

        derived_names = metadata.get("derived_vtk_array_names")
        if not isinstance(derived_names, list):
            raise SolverEvidenceError(f"field derived-array inventory is invalid: {field.name}")
        if derived_names and metadata.get("derived_evidence_class") != "DETERMINISTIC_CALCULATION":
            raise SolverEvidenceError(f"field derived evidence class is invalid: {field.name}")

        for array_name in derived_names:
            if array_name.endswith("__TRANSLATION_MAGNITUDE"):
                array = grid.GetPointData().GetArray(array_name)
                association = "POINT"
                label = f"Displacement magnitude — {field.name} [DERIVED]"
            elif array_name.endswith("__VON_MISES_MAX"):
                array = grid.GetCellData().GetArray(array_name)
                association = "CELL"
                label = f"von Mises max — {field.name} [DERIVED]"
            else:
                continue
            if array is None or array.GetNumberOfComponents() != 1:
                raise SolverEvidenceError(f"declared render array is missing or not scalar: {array_name}")
            renderable.append(
                RenderableResultField(
                    label=label,
                    source_field_name=field.name,
                    array_name=array_name,
                    vtk_association=association,
                    source_evidence_class="SOLVER_RESULT",
                    artifact_evidence_class="DETERMINISTIC_CALCULATION",
                    derived_evidence_class="DETERMINISTIC_CALCULATION",
                    unit=field.unit,
                )
            )

    if not renderable:
        raise SolverEvidenceError("validated result contains no provenance-declared renderable scalar fields")
    return renderable
