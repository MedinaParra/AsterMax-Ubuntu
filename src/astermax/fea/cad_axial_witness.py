from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256
from .persistent_geometry import capture_face_selection, list_face_signatures
from .section_evidence import PlanarSectionProperties, planar_section_properties


class CadAxialWitnessError(ValueError):
    pass


@dataclass(frozen=True)
class CadAxialStressWitness:
    schema: str
    source_sha256: str
    selection_id: str
    selection_sha256: str
    section_sha256: str
    load_axis: int
    resultant_n: float
    area_mm2: float
    analytical_sigma_mpa: float
    method: str
    witness_sha256: str

    def canonical_without_hash(self) -> dict:
        payload = asdict(self)
        payload.pop("witness_sha256")
        return payload


def _candidate_end_face(step_path: str | Path, axis: int, end: str) -> int:
    if axis not in (0, 1, 2):
        raise CadAxialWitnessError("axis must be 0, 1 or 2")
    direction = str(end).upper()
    if direction not in {"MIN", "MAX"}:
        raise CadAxialWitnessError("end must be MIN or MAX")
    inventory = list_face_signatures(step_path)
    planes = [(tag, signature) for tag, signature in inventory if signature.surface_type.strip().lower() == "plane"]
    if not planes:
        raise CadAxialWitnessError("STEP_HAS_NO_PLANAR_END_FACE")
    coordinates = np.asarray([signature.center_mm[axis] for _, signature in planes], dtype=float)
    target = float(np.max(coordinates) if direction == "MAX" else np.min(coordinates))
    span = max(float(np.max(coordinates) - np.min(coordinates)), 1.0)
    tol = span * 1.0e-9
    matches = [(tag, signature) for tag, signature in planes if abs(signature.center_mm[axis] - target) <= tol]
    if len(matches) != 1:
        raise CadAxialWitnessError("AXIAL_END_FACE_AMBIGUOUS:" + ",".join(str(tag) for tag, _ in matches))
    return int(matches[0][0])


def derive_cad_axial_stress_witness(
    step_path: str | Path,
    resultant_n: float,
    *,
    axis: int = 0,
    end: str = "MAX",
    selection_id: str = "C3_2_AXIAL_LOAD_SECTION",
) -> tuple[CadAxialStressWitness, PlanarSectionProperties]:
    force = float(resultant_n)
    if not np.isfinite(force):
        raise CadAxialWitnessError("resultant_n must be finite")
    tag = _candidate_end_face(step_path, axis, end)
    selection = capture_face_selection(step_path, tag, selection_id)
    section = planar_section_properties(step_path, selection)
    normal = np.asarray(section.normal, dtype=float)
    if abs(float(normal[axis])) < 1.0 - 1.0e-8:
        raise CadAxialWitnessError("SELECTED_SECTION_NOT_NORMAL_TO_LOAD_AXIS")
    area = float(section.area_mm2)
    if not np.isfinite(area) or area <= 0.0:
        raise CadAxialWitnessError("CAD_SECTION_AREA_MUST_BE_POSITIVE")
    sigma = force / area
    payload = {
        "schema": "AsterMaxCadAxialStressWitnessV1",
        "source_sha256": section.source_sha256,
        "selection_id": selection.selection_id,
        "selection_sha256": selection.selection_sha256,
        "section_sha256": section.section_sha256,
        "load_axis": int(axis),
        "resultant_n": force,
        "area_mm2": area,
        "analytical_sigma_mpa": sigma,
        "method": "RESULTANT_N_DIVIDED_BY_OPENCASCADE_PLANAR_SECTION_AREA_FROM_EXACT_STEP",
    }
    return CadAxialStressWitness(**payload, witness_sha256=canonical_sha256(payload)), section


def cad_axial_stress_evidence(witness: CadAxialStressWitness) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"CAD_AXIAL_STRESS:{witness.witness_sha256[:24]}",
        kind="CAD_DERIVED_ANALYTICAL_STRESS",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.ANALYTICAL_WITNESS,
        description="Axial analytical stress F/A using area derived from the persistent planar section of the exact STEP source.",
        payload_sha256=witness.witness_sha256,
        metadata={
            "source_sha256": witness.source_sha256,
            "selection_id": witness.selection_id,
            "selection_sha256": witness.selection_sha256,
            "section_sha256": witness.section_sha256,
            "resultant_n": witness.resultant_n,
            "area_mm2": witness.area_mm2,
            "analytical_sigma_mpa": witness.analytical_sigma_mpa,
            "ansys_equivalence": False,
            "industrial_validation": False,
        },
    )
