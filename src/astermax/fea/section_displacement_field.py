from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from .section_polyline_assembly import SectionPolylineAssemblyV1


@dataclass(frozen=True)
class SectionDisplacementSampleV1:
    polyline_index: int
    point_index: int
    point_mm: tuple[float, float, float]
    element_id: int
    natural_coordinates: tuple[float, float, float]
    displacement_mm: tuple[float, float, float]
    displacement_magnitude_mm: float
    geometry_residual_mm: float


@dataclass(frozen=True)
class SectionDisplacementFieldV1:
    schema: str
    semantics: str
    length_unit: str
    workspace_sha256: str
    solve_evidence_sha256: str
    geometry_sha256: str
    assembly_sha256: str
    nodal_field_sha256: str
    field_sha256: str
    status: str
    blockers: tuple[str, ...]
    sample_count: int
    max_geometry_residual_mm: float
    max_cross_element_disagreement_mm: float
    min_displacement_magnitude_mm: float
    max_displacement_magnitude_mm: float
    samples: tuple[SectionDisplacementSampleV1, ...]


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _tet10_shape(rst: np.ndarray) -> np.ndarray:
    r, s, t = (float(value) for value in rst)
    l1 = 1.0 - r - s - t
    l2 = r
    l3 = s
    l4 = t
    return np.asarray(
        (
            l1 * (2.0 * l1 - 1.0),
            l2 * (2.0 * l2 - 1.0),
            l3 * (2.0 * l3 - 1.0),
            l4 * (2.0 * l4 - 1.0),
            4.0 * l1 * l2,
            4.0 * l2 * l3,
            4.0 * l3 * l1,
            4.0 * l1 * l4,
            4.0 * l3 * l4,
            4.0 * l2 * l4,
        ),
        dtype=float,
    )


def _tet10_shape_derivatives(rst: np.ndarray) -> np.ndarray:
    r, s, t = (float(value) for value in rst)
    l1 = 1.0 - r - s - t
    l2 = r
    l3 = s
    l4 = t
    # Rows are derivatives with respect to r,s,t; columns are TET10 shape functions.
    return np.asarray(
        (
            (
                -(4.0 * l1 - 1.0), 4.0 * l2 - 1.0, 0.0, 0.0,
                4.0 * (l1 - l2), 4.0 * l3, -4.0 * l3,
                -4.0 * l4, 0.0, 4.0 * l4,
            ),
            (
                -(4.0 * l1 - 1.0), 0.0, 4.0 * l3 - 1.0, 0.0,
                -4.0 * l2, 4.0 * l2, 4.0 * (l1 - l3),
                -4.0 * l4, 4.0 * l4, 0.0,
            ),
            (
                -(4.0 * l1 - 1.0), 0.0, 0.0, 4.0 * l4 - 1.0,
                -4.0 * l2, 0.0, -4.0 * l3,
                4.0 * (l1 - l4), 4.0 * l3, 4.0 * l2,
            ),
        ),
        dtype=float,
    )


def _initial_natural_coordinates(corner_nodes: np.ndarray, point_mm: np.ndarray) -> np.ndarray:
    matrix = np.column_stack(
        (corner_nodes[1] - corner_nodes[0], corner_nodes[2] - corner_nodes[0], corner_nodes[3] - corner_nodes[0])
    )
    try:
        return np.linalg.solve(matrix, point_mm - corner_nodes[0])
    except np.linalg.LinAlgError as exc:
        raise ValueError("SECTION_DISPLACEMENT_DEGENERATE_ELEMENT") from exc


def _invert_tet10_point(
    element_nodes_mm: np.ndarray,
    point_mm: np.ndarray,
    *,
    geometry_tolerance_mm: float,
    natural_tolerance: float,
    max_iterations: int,
) -> tuple[np.ndarray, float] | None:
    rst = _initial_natural_coordinates(element_nodes_mm[:4], point_mm)
    for _ in range(max_iterations):
        shape = _tet10_shape(rst)
        mapped = shape @ element_nodes_mm
        residual = mapped - point_mm
        residual_norm = float(np.linalg.norm(residual))
        if residual_norm <= geometry_tolerance_mm:
            break
        derivatives = _tet10_shape_derivatives(rst)
        jacobian = derivatives @ element_nodes_mm
        try:
            delta = np.linalg.solve(jacobian.T, residual)
        except np.linalg.LinAlgError:
            return None
        rst = rst - delta
        if not np.all(np.isfinite(rst)):
            return None
    shape = _tet10_shape(rst)
    mapped = shape @ element_nodes_mm
    residual_norm = float(np.linalg.norm(mapped - point_mm))
    bary = np.asarray((1.0 - float(np.sum(rst)), rst[0], rst[1], rst[2]), dtype=float)
    if residual_norm > geometry_tolerance_mm:
        return None
    if float(np.min(bary)) < -natural_tolerance or float(np.max(bary)) > 1.0 + natural_tolerance:
        return None
    return rst, residual_norm


def build_section_displacement_field(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    nodal_displacements_mm: np.ndarray,
    assembly: SectionPolylineAssemblyV1,
    *,
    workspace_sha256: str,
    solve_evidence_sha256: str,
    geometry_tolerance_mm: float = 1.0e-8,
    natural_tolerance: float = 1.0e-8,
    cross_element_tolerance_mm: float = 1.0e-8,
    max_iterations: int = 20,
) -> SectionDisplacementFieldV1:
    """Evaluate the solved nodal displacement field on verified TET10 section polylines.

    Every section point is inverted through the isoparametric TET10 geometry and the
    displacement is evaluated with the same quadratic shape functions. Points that
    can be represented by multiple contributing elements must agree within the stated
    physical tolerance. This contract does not recover stress, smooth/extrapolate
    fields, integrate section resultants, or claim equivalence with ANSYS.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    displacements = np.asarray(nodal_displacements_mm, dtype=float)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("SECTION_DISPLACEMENT_NODES")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("SECTION_DISPLACEMENT_TET10")
    if elems.size and (int(np.min(elems)) < 0 or int(np.max(elems)) >= nodes.shape[0]):
        raise ValueError("SECTION_DISPLACEMENT_CONNECTIVITY")
    if displacements.shape != nodes.shape or not np.all(np.isfinite(displacements)):
        raise ValueError("SECTION_DISPLACEMENT_FIELD")
    if not workspace_sha256 or not solve_evidence_sha256:
        raise ValueError("SECTION_DISPLACEMENT_PROVENANCE")
    if assembly.workspace_sha256 != str(workspace_sha256) or assembly.solve_evidence_sha256 != str(solve_evidence_sha256):
        raise ValueError("SECTION_DISPLACEMENT_STALE_SECTION")
    if not assembly.ready_for_results or not assembly.topology_valid:
        raise ValueError("SECTION_DISPLACEMENT_SECTION_NOT_READY")

    geometry_tolerance = float(geometry_tolerance_mm)
    natural_tol = float(natural_tolerance)
    cross_tolerance = float(cross_element_tolerance_mm)
    iterations = int(max_iterations)
    if not math.isfinite(geometry_tolerance) or geometry_tolerance <= 0.0:
        raise ValueError("SECTION_DISPLACEMENT_GEOMETRY_TOLERANCE")
    if not math.isfinite(natural_tol) or natural_tol <= 0.0:
        raise ValueError("SECTION_DISPLACEMENT_NATURAL_TOLERANCE")
    if not math.isfinite(cross_tolerance) or cross_tolerance <= 0.0:
        raise ValueError("SECTION_DISPLACEMENT_CROSS_ELEMENT_TOLERANCE")
    if iterations < 1 or iterations > 100:
        raise ValueError("SECTION_DISPLACEMENT_ITERATIONS")

    geometry_identity = {
        "nodes_mm": [[float(value) for value in row] for row in nodes],
        "elements": [[int(value) for value in row] for row in elems],
    }
    geometry_sha = _sha256_json(geometry_identity)
    if geometry_sha != assembly.geometry_sha256:
        raise ValueError("SECTION_DISPLACEMENT_GEOMETRY_MISMATCH")

    nodal_field_sha = _sha256_json(
        {
            "solve_evidence_sha256": str(solve_evidence_sha256),
            "nodal_displacements_mm": [[float(value) for value in row] for row in displacements],
        }
    )

    samples: list[SectionDisplacementSampleV1] = []
    max_geometry_residual = 0.0
    max_cross_disagreement = 0.0
    blockers: list[str] = []

    for polyline_index, polyline in enumerate(assembly.polylines):
        candidate_element_ids = tuple(int(value) for value in polyline.contributing_element_ids)
        for point_index, point in enumerate(polyline.points_mm):
            target = np.asarray(point, dtype=float)
            candidates: list[tuple[int, np.ndarray, float, np.ndarray]] = []
            for element_id in candidate_element_ids:
                if element_id < 0 or element_id >= elems.shape[0]:
                    continue
                node_ids = elems[element_id]
                inverse = _invert_tet10_point(
                    nodes[node_ids], target,
                    geometry_tolerance_mm=geometry_tolerance,
                    natural_tolerance=natural_tol,
                    max_iterations=iterations,
                )
                if inverse is None:
                    continue
                rst, residual = inverse
                displacement = _tet10_shape(rst) @ displacements[node_ids]
                candidates.append((element_id, rst, residual, displacement))

            if not candidates:
                blockers.append(f"POINT_NOT_IN_CONTRIBUTING_TET10:{polyline_index}:{point_index}")
                continue

            candidates.sort(key=lambda item: (item[2], item[0]))
            reference_displacement = candidates[0][3]
            disagreement = max(
                (float(np.linalg.norm(item[3] - reference_displacement)) for item in candidates),
                default=0.0,
            )
            max_cross_disagreement = max(max_cross_disagreement, disagreement)
            if disagreement > cross_tolerance:
                blockers.append(f"CROSS_ELEMENT_FIELD_DISCONTINUITY:{polyline_index}:{point_index}")
                continue

            element_id, rst, residual, displacement = candidates[0]
            max_geometry_residual = max(max_geometry_residual, float(residual))
            magnitude = float(np.linalg.norm(displacement))
            samples.append(
                SectionDisplacementSampleV1(
                    polyline_index=int(polyline_index),
                    point_index=int(point_index),
                    point_mm=tuple(float(value) for value in target),
                    element_id=int(element_id),
                    natural_coordinates=tuple(float(value) for value in rst),
                    displacement_mm=tuple(float(value) for value in displacement),
                    displacement_magnitude_mm=magnitude,
                    geometry_residual_mm=float(residual),
                )
            )

    expected_samples = sum(len(polyline.points_mm) for polyline in assembly.polylines)
    if len(samples) != expected_samples and not blockers:
        blockers.append("SECTION_DISPLACEMENT_SAMPLE_COUNT")
    status = "READY" if not blockers else "BLOCKED"
    if blockers:
        samples = []

    magnitudes = [sample.displacement_magnitude_mm for sample in samples]
    identity = {
        "schema": "AsterMaxSectionDisplacementFieldV1",
        "semantics": "verified_isoparametric_tet10_displacement_on_results_section",
        "workspace_sha256": str(workspace_sha256),
        "solve_evidence_sha256": str(solve_evidence_sha256),
        "geometry_sha256": geometry_sha,
        "assembly_sha256": assembly.assembly_sha256,
        "nodal_field_sha256": nodal_field_sha,
        "status": status,
        "blockers": blockers,
        "geometry_tolerance_mm": geometry_tolerance,
        "natural_tolerance": natural_tol,
        "cross_element_tolerance_mm": cross_tolerance,
        "samples": [sample.__dict__ for sample in samples],
    }
    return SectionDisplacementFieldV1(
        schema="AsterMaxSectionDisplacementFieldV1",
        semantics="verified_isoparametric_tet10_displacement_on_results_section",
        length_unit="mm",
        workspace_sha256=str(workspace_sha256),
        solve_evidence_sha256=str(solve_evidence_sha256),
        geometry_sha256=geometry_sha,
        assembly_sha256=assembly.assembly_sha256,
        nodal_field_sha256=nodal_field_sha,
        field_sha256=_sha256_json(identity),
        status=status,
        blockers=tuple(blockers),
        sample_count=len(samples),
        max_geometry_residual_mm=max_geometry_residual,
        max_cross_element_disagreement_mm=max_cross_disagreement,
        min_displacement_magnitude_mm=min(magnitudes) if magnitudes else 0.0,
        max_displacement_magnitude_mm=max(magnitudes) if magnitudes else 0.0,
        samples=tuple(samples),
    )
