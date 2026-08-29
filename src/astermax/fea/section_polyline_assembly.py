from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from collections import defaultdict

import numpy as np

from .adaptive_tet10_section import AdaptiveTet10SectionV1


@dataclass(frozen=True)
class SectionPolylineV1:
    closed: bool
    points_mm: tuple[tuple[float, float, float], ...]
    contributing_element_ids: tuple[int, ...]
    unique_edge_count: int
    source_segment_count: int
    polyline_sha256: str


@dataclass(frozen=True)
class SectionPolylineAssemblyV1:
    schema: str
    semantics: str
    length_unit: str
    workspace_sha256: str
    solve_evidence_sha256: str
    geometry_sha256: str
    plane_sha256: str
    source_section_sha256: str
    assembly_sha256: str
    endpoint_tolerance_mm: float
    ready_for_results: bool
    topology_valid: bool
    unique_boundary_edge_count: int
    cancelled_internal_edge_count: int
    duplicate_exterior_edge_count: int
    nonmanifold_shared_face_count: int
    branch_node_count: int
    open_polyline_count: int
    closed_polyline_count: int
    cross_element_polyline_count: int
    max_endpoint_cluster_spread_mm: float
    polylines: tuple[SectionPolylineV1, ...]


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _canonical_point(point: np.ndarray) -> tuple[float, float, float]:
    return tuple(0.0 if float(value) == 0.0 else float(value) for value in point)


def _cluster_endpoints(
    endpoints: list[np.ndarray], tolerance_mm: float
) -> tuple[list[int], list[tuple[float, float, float]], float]:
    """Cluster endpoints by true Euclidean distance using a deterministic hash grid."""
    if not endpoints:
        return [], [], 0.0

    parent = list(range(len(endpoints)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra == rb:
            return
        if ra < rb:
            parent[rb] = ra
        else:
            parent[ra] = rb

    order = sorted(
        range(len(endpoints)),
        key=lambda index: (_canonical_point(endpoints[index]), index),
    )
    grid: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for index in order:
        point = endpoints[index]
        cell = tuple(int(math.floor(float(value) / tolerance_mm)) for value in point)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other in grid.get((cell[0] + dx, cell[1] + dy, cell[2] + dz), ()):
                        if float(np.linalg.norm(point - endpoints[other])) <= tolerance_mm:
                            union(index, other)
        grid[cell].append(index)

    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(endpoints)):
        groups[find(index)].append(index)

    group_records: list[tuple[tuple[float, float, float], list[int], float]] = []
    max_spread = 0.0
    for members in groups.values():
        representative = min(_canonical_point(endpoints[index]) for index in members)
        spread = max(
            (float(np.linalg.norm(endpoints[a] - endpoints[b])) for a in members for b in members),
            default=0.0,
        )
        max_spread = max(max_spread, spread)
        group_records.append((representative, sorted(members), spread))
    group_records.sort(key=lambda item: item[0])

    assignment = [-1] * len(endpoints)
    representatives: list[tuple[float, float, float]] = []
    for cluster_id, (representative, members, _) in enumerate(group_records):
        representatives.append(representative)
        for member in members:
            assignment[member] = cluster_id
    return assignment, representatives, max_spread


def _walk_nonbranch_component(
    component: set[int],
    adjacency: dict[int, set[int]],
) -> tuple[list[int], bool]:
    endpoints = sorted(node for node in component if len(adjacency[node]) == 1)
    closed = not endpoints
    start = endpoints[0] if endpoints else min(component)
    path = [start]
    previous: int | None = None
    current = start
    while True:
        candidates = sorted(node for node in adjacency[current] if node != previous)
        if not candidates:
            break
        if closed and previous is not None and start in candidates and len(candidates) > 1:
            candidates = [node for node in candidates if node != start] + [start]
        nxt = candidates[0]
        path.append(nxt)
        previous, current = current, nxt
        if closed and current == start:
            break
        if not closed and len(adjacency[current]) == 1:
            break
        if len(path) > len(component) + 1:
            raise ValueError("SECTION_POLYLINE_TRAVERSAL")
    return path, closed


def assemble_section_polylines(
    section: AdaptiveTet10SectionV1,
    *,
    endpoint_tolerance_mm: float | None = None,
) -> SectionPolylineAssemblyV1:
    """Assemble an adaptive TET10 section into deterministic boundary polylines.

    Endpoints are clustered by Euclidean distance in physical millimetres. Segments
    contributed by both sides of the same shared TRI6 face are cancelled as internal
    mesh topology before graph assembly. Remaining boundary edges are deduplicated,
    ordered into open/closed polylines and checked for branch/non-manifold topology.

    The contract is geometry-only. It does not interpolate FEA fields, smooth stress,
    integrate section resultants, or claim ANSYS equivalence.
    """
    tolerance = (
        float(section.topology_tolerance_mm)
        if endpoint_tolerance_mm is None
        else float(endpoint_tolerance_mm)
    )
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("SECTION_POLYLINE_ENDPOINT_TOLERANCE")
    if not section.workspace_sha256 or not section.solve_evidence_sha256:
        raise ValueError("SECTION_POLYLINE_PROVENANCE")

    segments = section.contour.segments
    endpoints: list[np.ndarray] = []
    for segment in segments:
        endpoints.extend(
            (
                np.asarray(segment.points_mm[0], dtype=float),
                np.asarray(segment.points_mm[1], dtype=float),
            )
        )
    if endpoints and not all(point.shape == (3,) and np.all(np.isfinite(point)) for point in endpoints):
        raise ValueError("SECTION_POLYLINE_ENDPOINTS")

    assignment, representatives, max_spread = _cluster_endpoints(endpoints, tolerance)

    # Collect every geometric edge together with the element-face sources that
    # generated it. A physical interior TRI6 face appears once from each adjacent
    # TET10 and must cancel from the section boundary.
    edge_sources: dict[tuple[int, int], list[tuple[int, int, tuple[int, ...], int]]] = defaultdict(list)
    degenerate_source_count = 0
    for segment_index, segment in enumerate(segments):
        a = assignment[2 * segment_index]
        b = assignment[2 * segment_index + 1]
        if a == b:
            degenerate_source_count += 1
            continue
        edge = (a, b) if a < b else (b, a)
        edge_sources[edge].append(
            (
                int(segment.element_id),
                int(segment.face_id),
                tuple(sorted(int(node_id) for node_id in segment.node_ids)),
                int(segment_index),
            )
        )

    boundary_sources: dict[tuple[int, int], list[tuple[int, int, tuple[int, ...], int]]] = {}
    cancelled_internal_edges = 0
    duplicate_exterior_edges = 0
    nonmanifold_shared_faces: set[tuple[int, ...]] = set()

    for edge, sources in sorted(edge_sources.items()):
        by_face: dict[tuple[int, ...], list[tuple[int, int, tuple[int, ...], int]]] = defaultdict(list)
        for source in sources:
            by_face[source[2]].append(source)

        remaining: list[tuple[int, int, tuple[int, ...], int]] = []
        for face_key, face_sources in sorted(by_face.items()):
            distinct_elements = sorted({source[0] for source in face_sources})
            if len(distinct_elements) == 2:
                cancelled_internal_edges += 1
                continue
            if len(distinct_elements) > 2:
                nonmanifold_shared_faces.add(face_key)
                continue
            remaining.extend(face_sources)

        if remaining:
            if len(remaining) > 1:
                duplicate_exterior_edges += 1
            boundary_sources[edge] = remaining

    adjacency: dict[int, set[int]] = defaultdict(set)
    for a, b in boundary_sources:
        adjacency[a].add(b)
        adjacency[b].add(a)

    visited: set[int] = set()
    components: list[set[int]] = []
    for seed in sorted(adjacency):
        if seed in visited:
            continue
        component: set[int] = set()
        stack = [seed]
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            stack.extend(sorted(adjacency[node] - component, reverse=True))
        visited.update(component)
        components.append(component)

    branch_nodes = sum(1 for node in adjacency if len(adjacency[node]) > 2)
    polylines: list[SectionPolylineV1] = []
    assembled_edges: set[tuple[int, int]] = set()

    for component in components:
        if any(len(adjacency[node]) > 2 for node in component):
            continue
        endpoint_count = sum(1 for node in component if len(adjacency[node]) == 1)
        if endpoint_count not in (0, 2):
            continue
        path, closed = _walk_nonbranch_component(component, adjacency)
        edge_keys: list[tuple[int, int]] = []
        source_records: list[tuple[int, int, tuple[int, ...], int]] = []
        for a, b in zip(path, path[1:]):
            edge = (a, b) if a < b else (b, a)
            edge_keys.append(edge)
            source_records.extend(boundary_sources[edge])
            assembled_edges.add(edge)
        points = tuple(representatives[node] for node in path)
        element_ids = tuple(sorted({source[0] for source in source_records}))
        identity = {
            "closed": closed,
            "points_mm": [list(point) for point in points],
            "element_ids": list(element_ids),
            "edge_keys": [list(edge) for edge in edge_keys],
            "source_segment_indices": sorted(source[3] for source in source_records),
        }
        polylines.append(
            SectionPolylineV1(
                closed=closed,
                points_mm=points,
                contributing_element_ids=element_ids,
                unique_edge_count=len(edge_keys),
                source_segment_count=len(source_records),
                polyline_sha256=_sha256_json(identity),
            )
        )

    polylines.sort(key=lambda item: (not item.closed, item.points_mm, item.polyline_sha256))
    open_count = sum(not item.closed for item in polylines)
    closed_count = sum(item.closed for item in polylines)
    cross_element_count = sum(len(item.contributing_element_ids) > 1 for item in polylines)
    all_boundary_edges_assembled = assembled_edges == set(boundary_sources)
    topology_valid = (
        branch_nodes == 0
        and not nonmanifold_shared_faces
        and open_count == 0
        and closed_count > 0
        and all_boundary_edges_assembled
        and degenerate_source_count == 0
    )
    ready = bool(section.converged and topology_valid)

    identity = {
        "schema": "AsterMaxSectionPolylineAssemblyV1",
        "semantics": "adaptive_tet10_section_ordered_boundary_polylines_geometry_only",
        "workspace_sha256": section.workspace_sha256,
        "solve_evidence_sha256": section.solve_evidence_sha256,
        "geometry_sha256": section.geometry_sha256,
        "plane_sha256": section.plane_sha256,
        "source_section_sha256": section.section_sha256,
        "endpoint_tolerance_mm": tolerance,
        "source_converged": section.converged,
        "ready_for_results": ready,
        "topology_valid": topology_valid,
        "unique_boundary_edge_count": len(boundary_sources),
        "cancelled_internal_edge_count": cancelled_internal_edges,
        "duplicate_exterior_edge_count": duplicate_exterior_edges,
        "nonmanifold_shared_face_count": len(nonmanifold_shared_faces),
        "branch_node_count": branch_nodes,
        "open_polyline_count": open_count,
        "closed_polyline_count": closed_count,
        "max_endpoint_cluster_spread_mm": max_spread,
        "polylines": [item.__dict__ for item in polylines],
    }
    return SectionPolylineAssemblyV1(
        schema="AsterMaxSectionPolylineAssemblyV1",
        semantics="adaptive_tet10_section_ordered_boundary_polylines_geometry_only",
        length_unit="mm",
        workspace_sha256=section.workspace_sha256,
        solve_evidence_sha256=section.solve_evidence_sha256,
        geometry_sha256=section.geometry_sha256,
        plane_sha256=section.plane_sha256,
        source_section_sha256=section.section_sha256,
        assembly_sha256=_sha256_json(identity),
        endpoint_tolerance_mm=tolerance,
        ready_for_results=ready,
        topology_valid=topology_valid,
        unique_boundary_edge_count=len(boundary_sources),
        cancelled_internal_edge_count=cancelled_internal_edges,
        duplicate_exterior_edge_count=duplicate_exterior_edges,
        nonmanifold_shared_face_count=len(nonmanifold_shared_faces),
        branch_node_count=branch_nodes,
        open_polyline_count=open_count,
        closed_polyline_count=closed_count,
        cross_element_polyline_count=cross_element_count,
        max_endpoint_cluster_spread_mm=max_spread,
        polylines=tuple(polylines),
    )
