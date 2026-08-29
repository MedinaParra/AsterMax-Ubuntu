from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from .quadratic_tri6_face_contour import (
    QuadraticTri6ContourSegmentV1,
    QuadraticTri6FaceContourV1,
    build_quadratic_tri6_face_contour,
)


_TET10_FACES: tuple[tuple[int, int, int, int, int, int], ...] = (
    (0, 1, 2, 4, 5, 6),
    (0, 1, 3, 4, 9, 7),
    (1, 2, 3, 5, 8, 9),
    (2, 0, 3, 6, 7, 8),
)


@dataclass(frozen=True)
class AdaptiveTet10SectionIterationV1:
    sampling_divisions: int
    segment_count: int
    ambiguous_cell_count: int
    max_plane_residual_mm: float
    max_chord_error_mm: float
    converged: bool
    contour_sha256: str


@dataclass(frozen=True)
class AdaptiveTet10SectionV1:
    schema: str
    semantics: str
    length_unit: str
    workspace_sha256: str
    solve_evidence_sha256: str
    geometry_sha256: str
    plane_sha256: str
    section_sha256: str
    target_error_mm: float
    topology_tolerance_mm: float
    converged: bool
    selected_sampling_divisions: int
    max_plane_residual_mm: float
    max_chord_error_mm: float
    connected_component_count: int
    open_component_count: int
    closed_component_count: int
    iterations: tuple[AdaptiveTet10SectionIterationV1, ...]
    contour: QuadraticTri6FaceContourV1


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _tri6_point(face_nodes: np.ndarray, r: float, s: float) -> np.ndarray:
    l1 = 1.0 - float(r) - float(s)
    l2 = float(r)
    l3 = float(s)
    shape = np.asarray(
        (
            l1 * (2.0 * l1 - 1.0),
            l2 * (2.0 * l2 - 1.0),
            l3 * (2.0 * l3 - 1.0),
            4.0 * l1 * l2,
            4.0 * l2 * l3,
            4.0 * l3 * l1,
        ),
        dtype=float,
    )
    return shape @ face_nodes


def _segment_chord_error_mm(
    segment: QuadraticTri6ContourSegmentV1,
    nodes: np.ndarray,
) -> float:
    face_nodes = nodes[list(segment.node_ids)]
    uv0 = np.asarray(segment.reference_points[0], dtype=float)
    uv1 = np.asarray(segment.reference_points[1], dtype=float)
    midpoint_uv = 0.5 * (uv0 + uv1)
    mapped_midpoint = _tri6_point(face_nodes, *midpoint_uv)
    chord_midpoint = 0.5 * (
        np.asarray(segment.points_mm[0], dtype=float)
        + np.asarray(segment.points_mm[1], dtype=float)
    )
    return float(np.linalg.norm(mapped_midpoint - chord_midpoint))


def _point_key(point: tuple[float, float, float], tolerance_mm: float) -> tuple[int, int, int]:
    return tuple(int(round(float(value) / tolerance_mm)) for value in point)


def _topology_counts(
    contour: QuadraticTri6FaceContourV1,
    topology_tolerance_mm: float,
) -> tuple[int, int, int]:
    if not contour.segments:
        return 0, 0, 0

    adjacency: dict[tuple[int, int, int], set[tuple[int, int, int]]] = {}
    for segment in contour.segments:
        a = _point_key(segment.points_mm[0], topology_tolerance_mm)
        b = _point_key(segment.points_mm[1], topology_tolerance_mm)
        if a == b:
            continue
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)

    visited: set[tuple[int, int, int]] = set()
    components = 0
    open_components = 0
    closed_components = 0
    for seed in sorted(adjacency):
        if seed in visited:
            continue
        components += 1
        stack = [seed]
        component: list[tuple[int, int, int]] = []
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            stack.extend(sorted(adjacency.get(node, ()), reverse=True))
        degrees = [len(adjacency[node]) for node in component]
        if component and all(degree == 2 for degree in degrees):
            closed_components += 1
        else:
            open_components += 1
    return components, open_components, closed_components


def build_adaptive_tet10_section(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    plane_origin_mm: tuple[float, float, float],
    plane_normal: tuple[float, float, float],
    workspace_sha256: str,
    solve_evidence_sha256: str,
    target_error_mm: float = 1.0e-3,
    topology_tolerance_mm: float = 1.0e-7,
    initial_sampling_divisions: int = 8,
    max_sampling_divisions: int = 128,
    plane_tolerance_mm: float = 1.0e-10,
) -> AdaptiveTet10SectionV1:
    """Adapt TRI6 section resolution until a declared geometric error target is met.

    The convergence gate combines the mapped plane residual, a quadratic-face chord
    deviation estimate and ambiguous-cell count. Endpoint connectivity is measured
    in physical millimetres to expose open/closed section topology. This remains a
    geometry-only reconstruction contract: it does not interpolate FEA fields,
    integrate section resultants, or claim equivalence with commercial CAE tools.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    target = float(target_error_mm)
    topology_tolerance = float(topology_tolerance_mm)
    plane_tolerance = float(plane_tolerance_mm)
    initial = int(initial_sampling_divisions)
    maximum = int(max_sampling_divisions)

    if not math.isfinite(target) or target <= 0.0:
        raise ValueError("ADAPTIVE_TET10_SECTION_TARGET_ERROR")
    if not math.isfinite(topology_tolerance) or topology_tolerance <= 0.0:
        raise ValueError("ADAPTIVE_TET10_SECTION_TOPOLOGY_TOLERANCE")
    if not math.isfinite(plane_tolerance) or plane_tolerance <= 0.0:
        raise ValueError("ADAPTIVE_TET10_SECTION_PLANE_TOLERANCE")
    if initial < 2 or initial > 256 or maximum < initial or maximum > 256:
        raise ValueError("ADAPTIVE_TET10_SECTION_DIVISIONS")

    iterations: list[AdaptiveTet10SectionIterationV1] = []
    selected: QuadraticTri6FaceContourV1 | None = None
    selected_chord_error = math.inf
    divisions = initial

    while True:
        contour = build_quadratic_tri6_face_contour(
            nodes,
            elems,
            plane_origin_mm=plane_origin_mm,
            plane_normal=plane_normal,
            workspace_sha256=workspace_sha256,
            solve_evidence_sha256=solve_evidence_sha256,
            tolerance_mm=plane_tolerance,
            sampling_divisions=divisions,
        )
        chord_error = max(
            (_segment_chord_error_mm(segment, nodes) for segment in contour.segments),
            default=0.0,
        )
        converged = (
            contour.segment_count > 0
            and contour.ambiguous_cell_count == 0
            and contour.max_plane_residual_mm <= target
            and chord_error <= target
        )
        iterations.append(
            AdaptiveTet10SectionIterationV1(
                sampling_divisions=divisions,
                segment_count=contour.segment_count,
                ambiguous_cell_count=contour.ambiguous_cell_count,
                max_plane_residual_mm=contour.max_plane_residual_mm,
                max_chord_error_mm=chord_error,
                converged=converged,
                contour_sha256=contour.contour_sha256,
            )
        )
        selected = contour
        selected_chord_error = chord_error
        if converged or divisions >= maximum:
            break
        divisions = min(maximum, divisions * 2)

    assert selected is not None
    topology = _topology_counts(selected, topology_tolerance)
    final_converged = iterations[-1].converged
    identity = {
        "schema": "AsterMaxAdaptiveTet10SectionV1",
        "semantics": "adaptive_quadratic_tet10_section_geometry_only_error_bounded",
        "workspace_sha256": workspace_sha256,
        "solve_evidence_sha256": solve_evidence_sha256,
        "geometry_sha256": selected.geometry_sha256,
        "plane_sha256": selected.plane_sha256,
        "target_error_mm": target,
        "topology_tolerance_mm": topology_tolerance,
        "converged": final_converged,
        "selected_sampling_divisions": selected.sampling_divisions,
        "max_plane_residual_mm": selected.max_plane_residual_mm,
        "max_chord_error_mm": selected_chord_error,
        "topology": list(topology),
        "iterations": [iteration.__dict__ for iteration in iterations],
        "contour_sha256": selected.contour_sha256,
    }
    return AdaptiveTet10SectionV1(
        schema="AsterMaxAdaptiveTet10SectionV1",
        semantics="adaptive_quadratic_tet10_section_geometry_only_error_bounded",
        length_unit="mm",
        workspace_sha256=str(workspace_sha256),
        solve_evidence_sha256=str(solve_evidence_sha256),
        geometry_sha256=selected.geometry_sha256,
        plane_sha256=selected.plane_sha256,
        section_sha256=_sha256_json(identity),
        target_error_mm=target,
        topology_tolerance_mm=topology_tolerance,
        converged=final_converged,
        selected_sampling_divisions=selected.sampling_divisions,
        max_plane_residual_mm=selected.max_plane_residual_mm,
        max_chord_error_mm=selected_chord_error,
        connected_component_count=topology[0],
        open_component_count=topology[1],
        closed_component_count=topology[2],
        iterations=tuple(iterations),
        contour=selected,
    )
