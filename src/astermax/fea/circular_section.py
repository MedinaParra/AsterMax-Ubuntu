from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256
from .gmsh_bridge import _gmsh
from .persistent_geometry import (
    PersistentFaceSelection,
    PersistentGeometryError,
    _assert_source,
    _import,
    _resolve_current,
    _step,
)
from .section_evidence import PlanarSectionProperties, planar_section_properties


@dataclass(frozen=True)
class CircularSectionApplicability:
    schema: str
    selection_id: str
    source_sha256: str
    section_sha256: str
    face_signature_sha256: str
    radius_mm: float
    area_mm2: float
    polar_j_mm4: float
    boundary_curve_count: int
    boundary_curve_types: tuple[str, ...]
    inertia_isotropy_relative_residual: float
    product_inertia_relative_residual: float
    circular_polar_identity_relative_residual: float
    method: str
    applicability_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("applicability_sha256")
        return payload


def _relative(a: float, b: float) -> float:
    return abs(float(a) - float(b)) / max(abs(float(a)), abs(float(b)), 1.0e-30)


def prove_solid_circular_section(
    step_path: str | Path,
    selection: PersistentFaceSelection,
    *,
    relative_tolerance: float = 1.0e-8,
) -> CircularSectionApplicability:
    tolerance = float(relative_tolerance)
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("relative_tolerance must be finite and positive")

    section: PlanarSectionProperties = planar_section_properties(step_path, selection)
    source = _step(step_path)
    _assert_source(source, selection)

    gmsh = _gmsh(); gmsh.initialize()
    try:
        diagonal = _import(gmsh, source, "astermax_circular_section")
        resolution = _resolve_current(gmsh, selection, diagonal)
        surface_type = str(gmsh.model.getType(2, int(resolution.resolved_tag))).strip().lower()
        if surface_type != "plane":
            raise PersistentGeometryError(f"CIRCULAR_SECTION_OUT_OF_DOMAIN_SURFACE:{surface_type}")

        boundary = gmsh.model.getBoundary(
            [(2, int(resolution.resolved_tag))],
            combined=True,
            oriented=False,
            recursive=False,
        )
        curves = tuple((int(dim), int(tag)) for dim, tag in boundary if int(dim) == 1)
        curve_types = tuple(str(gmsh.model.getType(1, tag)).strip() for _, tag in curves)
        if len(curves) != 1 or len(curve_types) != 1 or curve_types[0].lower() != "circle":
            raise PersistentGeometryError(
                "CIRCULAR_SECTION_OUT_OF_DOMAIN_BOUNDARY:"
                f"count={len(curves)}:types={','.join(curve_types) or 'NONE'}"
            )
    finally:
        gmsh.finalize()

    area = float(section.area_mm2)
    j = float(section.polar_i_n_mm4)
    if not math.isfinite(area) or not math.isfinite(j) or area <= 0.0 or j <= 0.0:
        raise PersistentGeometryError("CIRCULAR_SECTION_INVALID_CAD_INTEGRALS")

    radius = math.sqrt(area / math.pi)
    expected_j = area * area / (2.0 * math.pi)
    mean_i = 0.5 * (abs(section.i_u_mm4) + abs(section.i_v_mm4))
    isotropy = _relative(section.i_u_mm4, section.i_v_mm4)
    product = abs(float(section.i_uv_mm4)) / max(mean_i, 1.0e-30)
    polar_identity = _relative(j, expected_j)

    if isotropy > tolerance:
        raise PersistentGeometryError(f"CIRCULAR_SECTION_INERTIA_ISOTROPY_FAILED:{isotropy:.17g}")
    if product > tolerance:
        raise PersistentGeometryError(f"CIRCULAR_SECTION_PRODUCT_INERTIA_FAILED:{product:.17g}")
    if polar_identity > tolerance:
        raise PersistentGeometryError(
            f"CIRCULAR_SECTION_POLAR_IDENTITY_FAILED:{polar_identity:.17g}"
        )

    payload = {
        "schema": "AsterMaxCircularSectionApplicabilityV1",
        "selection_id": selection.selection_id,
        "source_sha256": selection.source_sha256,
        "section_sha256": section.section_sha256,
        "face_signature_sha256": section.face_signature_sha256,
        "radius_mm": radius,
        "area_mm2": area,
        "polar_j_mm4": j,
        "boundary_curve_count": len(curves),
        "boundary_curve_types": curve_types,
        "inertia_isotropy_relative_residual": isotropy,
        "product_inertia_relative_residual": product,
        "circular_polar_identity_relative_residual": polar_identity,
        "method": "STEP_FACE_SINGLE_CIRCLE_BOUNDARY_PLUS_CAD_INERTIA_IDENTITIES",
    }
    return CircularSectionApplicability(
        **payload,
        applicability_sha256=canonical_sha256(payload),
    )


def circular_section_applicability_evidence(
    applicability: CircularSectionApplicability,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"CIRCULAR_SECTION:{applicability.selection_id}",
        kind="CIRCULAR_SECTION_APPLICABILITY",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Exact persistent planar CAD face is a simple solid circular section within "
            "the declared Saint-Venant circular torsion witness domain."
        ),
        payload_sha256=applicability.applicability_sha256,
        metadata={
            "selection_id": applicability.selection_id,
            "source_sha256": applicability.source_sha256,
            "section_sha256": applicability.section_sha256,
            "radius_mm": applicability.radius_mm,
            "polar_j_mm4": applicability.polar_j_mm4,
            "boundary_curve_types": list(applicability.boundary_curve_types),
            "method": applicability.method,
        },
    )
