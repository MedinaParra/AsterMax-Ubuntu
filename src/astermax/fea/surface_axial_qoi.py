from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from astermax.credibility import (
    ClaimDefinition,
    ClaimRequirement,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)
from .tet10 import tet10_shape_functions
from .tet10_surface_stress import (
    Tet10SurfaceParent,
    Tet10SurfaceStressSample,
    evaluate_tet10_stress_at_natural_point,
    resolve_tri6_parent_tet10,
    tri6_point_to_tet10_natural,
)
from .tet4 import IsotropicMaterial, von_mises


SURFACE_TRI6_INTERIOR_RULE = (
    (1.0 / 3.0, 1.0 / 3.0),
    (1.0 / 6.0, 1.0 / 6.0),
    (2.0 / 3.0, 1.0 / 6.0),
    (1.0 / 6.0, 2.0 / 3.0),
)


@dataclass(frozen=True)
class FilletSurfaceAxialStressMeasurement:
    schema: str
    measurement_id: str
    mesh_sha256: str
    transition_selection_sha256: str
    tri6_face_count: int
    sample_points_per_face: int
    sample_count: int
    qoi_id: str
    measurement_operator: str
    minimum_axial_normal_stress_mpa: float
    maximum_axial_normal_stress_mpa: float
    mean_axial_normal_stress_mpa: float
    maximum_sample_sha256: str
    maximum_point_mm: tuple[float, float, float]
    maximum_parent_element_index: int
    no_nodal_stress_recovery: bool
    no_stress_smoothing: bool
    no_integration_point_stress_extrapolation: bool
    continuous_surface_peak_claim: bool
    measurement_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("measurement_sha256")
        return payload


def _evaluate_with_parent(
    nodes: np.ndarray,
    elements: np.ndarray,
    displacement: np.ndarray,
    material: IsotropicMaterial,
    parent: Tet10SurfaceParent,
    rs: tuple[float, float],
) -> Tet10SurfaceStressSample:
    natural = tri6_point_to_tet10_natural(parent, rs)
    conn = elements[parent.element_index]
    strain, stress, det_j = evaluate_tet10_stress_at_natural_point(
        nodes[conn], displacement[conn], material, natural
    )
    x = tet10_shape_functions(natural) @ nodes[conn]
    payload = {
        "schema": "AsterMaxTet10SurfaceStressSampleV1",
        "element_index": parent.element_index,
        "tri6_nodes": parent.tri6_nodes,
        "tri6_natural_coordinates": tuple(float(v) for v in rs),
        "tet10_natural_coordinates": tuple(float(v) for v in natural),
        "physical_point_mm": tuple(float(v) for v in x),
        "det_jacobian": float(det_j),
        "strain": tuple(float(v) for v in strain),
        "stress_mpa": tuple(float(v) for v in stress),
        "axial_normal_stress_mpa": float(stress[0]),
        "von_mises_mpa": float(von_mises(stress)),
        "parent_mapping_sha256": parent.mapping_sha256,
    }
    return Tet10SurfaceStressSample(**payload, sample_sha256=canonical_sha256(payload))


def measure_fillet_surface_axial_stress(
    *,
    measurement_id: str,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    displacement_mm: np.ndarray,
    material: IsotropicMaterial,
    transition_tri6: np.ndarray,
    mesh_sha256: str,
    transition_selection_sha256: str,
) -> tuple[FilletSurfaceAxialStressMeasurement, tuple[Tet10SurfaceStressSample, ...]]:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    disp = np.asarray(displacement_mm, dtype=float)
    faces = np.asarray(transition_tri6, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or disp.shape != nodes.shape:
        raise ValueError("nodes/displacement shape mismatch")
    if elems.ndim != 2 or elems.shape[1] != 10 or faces.ndim != 2 or faces.shape[1] != 6 or faces.shape[0] == 0:
        raise ValueError("invalid TET10 or TRI6 arrays")

    samples: list[Tet10SurfaceStressSample] = []
    for face in faces:
        parent = resolve_tri6_parent_tet10(elems, face)
        for rs in SURFACE_TRI6_INTERIOR_RULE:
            samples.append(_evaluate_with_parent(nodes, elems, disp, material, parent, rs))
    values = np.asarray([sample.axial_normal_stress_mpa for sample in samples], dtype=float)
    if values.size != faces.shape[0] * len(SURFACE_TRI6_INTERIOR_RULE) or not np.all(np.isfinite(values)):
        raise RuntimeError("surface axial stress measurement produced invalid sample set")
    max_index = int(np.argmax(values))
    peak = samples[max_index]
    payload = {
        "schema": "AsterMaxFilletSurfaceAxialStressMeasurementV1",
        "measurement_id": str(measurement_id),
        "mesh_sha256": str(mesh_sha256),
        "transition_selection_sha256": str(transition_selection_sha256),
        "tri6_face_count": int(faces.shape[0]),
        "sample_points_per_face": len(SURFACE_TRI6_INTERIOR_RULE),
        "sample_count": len(samples),
        "qoi_id": "SURFACE_SAMPLED_MAX_AXIAL_NORMAL_STRESS_MPA",
        "measurement_operator": "MAX_DIRECT_TET10_SIGMA_X_AT_FROZEN_4_INTERIOR_POINTS_PER_TRANSITION_TRI6",
        "minimum_axial_normal_stress_mpa": float(np.min(values)),
        "maximum_axial_normal_stress_mpa": float(np.max(values)),
        "mean_axial_normal_stress_mpa": float(np.mean(values)),
        "maximum_sample_sha256": peak.sample_sha256,
        "maximum_point_mm": peak.physical_point_mm,
        "maximum_parent_element_index": peak.element_index,
        "no_nodal_stress_recovery": True,
        "no_stress_smoothing": True,
        "no_integration_point_stress_extrapolation": True,
        "continuous_surface_peak_claim": False,
    }
    return (
        FilletSurfaceAxialStressMeasurement(**payload, measurement_sha256=canonical_sha256(payload)),
        tuple(samples),
    )


def fillet_surface_axial_stress_measurement_evidence(measurement: FilletSurfaceAxialStressMeasurement) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SURFACE_AXIAL_QOI:{measurement.measurement_sha256[:16]}",
        kind="PHYSICAL_FILLET_SURFACE_AXIAL_STRESS_MEASUREMENT",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Direct sampled axial-normal stress QOI on the persistent CAD fillet surface; discrete sampled maximum only.",
        payload_sha256=measurement.measurement_sha256,
        metadata=measurement.canonical_without_hash(),
    )


def physical_fillet_surface_axial_qoi_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_PHYSICAL_FILLET_SURFACE_AXIAL_QOI_COMPUTED",
        context_id=context_id,
        statement="A direct sampled axial-normal stress QOI was computed on the persistent CAD fillet surface for the declared physical load case.",
        requirements=(
            ClaimRequirement("TET10_SURFACE_STRESS_AFFINE_VERIFICATION", allowed_sources=(EvidenceSource.DOCUMENT, EvidenceSource.DETERMINISTIC_CHECK)),
            ClaimRequirement("PHYSICAL_LOAD_EQUILIBRIUM", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("PHYSICAL_FILLET_SURFACE_AXIAL_STRESS_MEASUREMENT", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
        ),
    )
