from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .tet10_jacobian import tet10_jacobian_matrix


@dataclass(frozen=True)
class Tet10JacobianAdaptivePolicy:
    max_depth: int = 5
    determinant_epsilon: float = 1.0e-12
    schema: str = "TET10_ADAPTIVE_BARYCENTRIC_CERTIFICATION_V1"

    def validate(self) -> None:
        if not isinstance(self.max_depth, int) or self.max_depth < 1:
            raise ValueError("max_depth must be an integer >= 1")
        if not np.isfinite(self.determinant_epsilon) or self.determinant_epsilon <= 0.0:
            raise ValueError("determinant_epsilon must be finite and positive")
        if self.schema != "TET10_ADAPTIVE_BARYCENTRIC_CERTIFICATION_V1":
            raise ValueError("unsupported adaptive TET10 Jacobian schema")


DEFAULT_TET10_JACOBIAN_ADAPTIVE_POLICY = Tet10JacobianAdaptivePolicy()


@dataclass(frozen=True)
class Tet10JacobianAdaptiveReport:
    schema: str
    status: str
    element_count: int
    evaluated_points: int
    nonpositive_sample_count: int
    minimum_determinant: float
    worst_element_index: int | None
    worst_natural_coordinates: tuple[float, float, float] | None
    maximum_depth_reached: int
    policy: dict
    evidence_boundary: str


def _unique_points(points: list[np.ndarray]) -> list[np.ndarray]:
    seen: set[tuple[float, float, float]] = set()
    unique: list[np.ndarray] = []
    for point in points:
        key = tuple(float(round(v, 15)) for v in point)
        if key not in seen:
            seen.add(key)
            unique.append(point)
    return unique


def _tetra_children(vertices: np.ndarray) -> list[np.ndarray]:
    """Split one reference tetrahedron into eight deterministic sub-tetrahedra."""
    a, b, c, d = vertices
    ab, ac, ad = (a + b) / 2.0, (a + c) / 2.0, (a + d) / 2.0
    bc, bd, cd = (b + c) / 2.0, (b + d) / 2.0, (c + d) / 2.0
    return [
        np.asarray([a, ab, ac, ad]),
        np.asarray([ab, b, bc, bd]),
        np.asarray([ac, bc, c, cd]),
        np.asarray([ad, bd, cd, d]),
        np.asarray([ab, ac, ad, bd]),
        np.asarray([ab, ac, bc, bd]),
        np.asarray([ac, ad, bd, cd]),
        np.asarray([ac, bc, bd, cd]),
    ]


def _sample_simplex(vertices: np.ndarray) -> list[np.ndarray]:
    centroid = np.mean(vertices, axis=0)
    midsides = [(vertices[i] + vertices[j]) / 2.0 for i in range(4) for j in range(i + 1, 4)]
    return _unique_points([*list(vertices), *midsides, centroid])


def tet10_adaptive_jacobian_report(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    policy: Tet10JacobianAdaptivePolicy = DEFAULT_TET10_JACOBIAN_ADAPTIVE_POLICY,
) -> Tet10JacobianAdaptiveReport:
    """Run a deterministic adaptive search for local TET10 Jacobian inversion.

    This strengthens the fixed lattice by recursively sampling suspicious regions.
    It remains a finite search and is therefore not a mathematical proof of global
    positivity for an arbitrary curved TET10.
    """
    policy.validate()
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must have finite shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10)")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contains an out-of-range node index")

    reference = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    minimum = np.inf
    worst_element: int | None = None
    worst_coords: tuple[float, float, float] | None = None
    nonpositive = 0
    evaluated = 0
    max_depth_reached = 0

    for element_index, conn in enumerate(elems):
        coords = nodes[conn]
        stack: list[tuple[np.ndarray, int]] = [(reference, 0)]
        cache: dict[tuple[float, float, float], float] = {}
        while stack:
            simplex, depth = stack.pop()
            max_depth_reached = max(max_depth_reached, depth)
            values: list[float] = []
            for point in _sample_simplex(simplex):
                key = tuple(float(round(v, 15)) for v in point)
                if key not in cache:
                    determinant = float(np.linalg.det(tet10_jacobian_matrix(coords, point)))
                    if not np.isfinite(determinant):
                        raise ValueError("non-finite TET10 Jacobian determinant")
                    cache[key] = determinant
                    evaluated += 1
                    if determinant <= policy.determinant_epsilon:
                        nonpositive += 1
                    if determinant < minimum:
                        minimum = determinant
                        worst_element = int(element_index)
                        worst_coords = tuple(float(v) for v in point)
                values.append(cache[key])

            local_min = min(values)
            if local_min <= policy.determinant_epsilon or depth >= policy.max_depth:
                continue

            # Always establish a two-level baseline, then spend work only in cells
            # whose local minimum is close to the current positive worst case.
            positive_floor = max(policy.determinant_epsilon, minimum)
            if depth < 2 or local_min <= 2.0 * positive_floor:
                stack.extend((child, depth + 1) for child in _tetra_children(simplex))

    if elems.shape[0] == 0:
        minimum = float("nan")
    status = "PASS" if nonpositive == 0 else "FAIL"
    return Tet10JacobianAdaptiveReport(
        schema="AsterMaxTet10JacobianAdaptiveReportV1",
        status=status,
        element_count=int(elems.shape[0]),
        evaluated_points=int(evaluated),
        nonpositive_sample_count=int(nonpositive),
        minimum_determinant=float(minimum),
        worst_element_index=worst_element,
        worst_natural_coordinates=worst_coords,
        maximum_depth_reached=int(max_depth_reached),
        policy=asdict(policy),
        evidence_boundary=(
            "ADAPTIVE_BARYCENTRIC_SEARCH_NOT_GLOBAL_POSITIVITY_PROOF_"
            "AND_DOES_NOT_ENABLE_CURVED_TET10_SOLVER"
        ),
    )


def require_tet10_adaptive_jacobian(report: Tet10JacobianAdaptiveReport) -> None:
    if report.status != "PASS":
        raise ValueError(
            "TET10 adaptive Jacobian gate failed: "
            f"min_det={report.minimum_determinant:.17g}, "
            f"element={report.worst_element_index}, natural={report.worst_natural_coordinates}"
        )
