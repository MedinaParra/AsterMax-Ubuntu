from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

# Gmsh TET10 order:
# vertices 0,1,2,3 then edges 01,12,20,03,23,13.
_EDGE_NODES = ((0, 1), (1, 2), (2, 0), (0, 3), (2, 3), (1, 3))
_D_L = np.asarray(
    [
        [-1.0, -1.0, -1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ],
    dtype=float,
)

# Deliberately declared, versioned sample set. This is a sampled Jacobian gate,
# not a proof of global positivity everywhere inside a curved quadratic tetrahedron.
TET10_JACOBIAN_SAMPLE_POINTS_V1 = np.asarray(
    [
        # vertices
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        # edge midpoints
        [0.5, 0.0, 0.0],
        [0.5, 0.5, 0.0],
        [0.0, 0.5, 0.0],
        [0.0, 0.0, 0.5],
        [0.0, 0.5, 0.5],
        [0.5, 0.0, 0.5],
        # face centroids
        [1.0 / 3.0, 1.0 / 3.0, 0.0],
        [1.0 / 3.0, 0.0, 1.0 / 3.0],
        [0.0, 1.0 / 3.0, 1.0 / 3.0],
        [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0],
        # volume centroid
        [0.25, 0.25, 0.25],
    ],
    dtype=float,
)


@dataclass(frozen=True)
class Tet10JacobianPolicy:
    determinant_epsilon: float = 1.0e-12
    sample_schema: str = "TET10_JACOBIAN_SAMPLE_POINTS_V1"

    def validate(self) -> None:
        if not np.isfinite(self.determinant_epsilon) or self.determinant_epsilon <= 0.0:
            raise ValueError("determinant_epsilon must be finite and positive")
        if self.sample_schema != "TET10_JACOBIAN_SAMPLE_POINTS_V1":
            raise ValueError("unsupported TET10 Jacobian sample schema")


DEFAULT_TET10_JACOBIAN_POLICY = Tet10JacobianPolicy()


@dataclass(frozen=True)
class Tet10JacobianReport:
    schema: str
    status: str
    element_count: int
    sample_count_per_element: int
    nonpositive_sample_count: int
    minimum_determinant: float
    worst_element_index: int | None
    worst_sample_index: int | None
    worst_natural_coordinates: tuple[float, float, float] | None
    policy: dict
    evidence_boundary: str


def tet10_shape_function_gradients(natural_coordinates: np.ndarray) -> np.ndarray:
    """Return dN/d(r,s,t) for a Gmsh-order quadratic tetrahedron."""
    rst = np.asarray(natural_coordinates, dtype=float)
    if rst.shape != (3,) or not np.all(np.isfinite(rst)):
        raise ValueError("natural_coordinates must contain three finite values")
    r, s, t = (float(value) for value in rst)
    barycentric = np.asarray([1.0 - r - s - t, r, s, t], dtype=float)
    if np.any(barycentric < -1.0e-12) or np.any(barycentric > 1.0 + 1.0e-12):
        raise ValueError("natural_coordinates must lie inside the reference tetrahedron")

    gradients = [(4.0 * barycentric[i] - 1.0) * _D_L[i] for i in range(4)]
    gradients.extend(
        4.0 * (barycentric[j] * _D_L[i] + barycentric[i] * _D_L[j])
        for i, j in _EDGE_NODES
    )
    return np.asarray(gradients, dtype=float)


def tet10_jacobian_matrix(coords_mm: np.ndarray, natural_coordinates: np.ndarray) -> np.ndarray:
    coords = np.asarray(coords_mm, dtype=float)
    if coords.shape != (10, 3) or not np.all(np.isfinite(coords)):
        raise ValueError("TET10 coordinates must have shape (10, 3) and be finite")
    gradients = tet10_shape_function_gradients(natural_coordinates)
    # x(r,s,t) = sum_i N_i x_i, so J[a,b] = dx_a / dxi_b.
    return coords.T @ gradients


def tet10_sampled_jacobian_report(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    policy: Tet10JacobianPolicy = DEFAULT_TET10_JACOBIAN_POLICY,
) -> Tet10JacobianReport:
    policy.validate()
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must have finite shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10)")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contains an out-of-range node index")

    minimum = np.inf
    worst_element: int | None = None
    worst_sample: int | None = None
    nonpositive = 0
    for element_index, conn in enumerate(elems):
        coords = nodes[conn]
        for sample_index, point in enumerate(TET10_JACOBIAN_SAMPLE_POINTS_V1):
            determinant = float(np.linalg.det(tet10_jacobian_matrix(coords, point)))
            if not np.isfinite(determinant):
                raise ValueError("non-finite TET10 Jacobian determinant")
            if determinant <= policy.determinant_epsilon:
                nonpositive += 1
            if determinant < minimum:
                minimum = determinant
                worst_element = int(element_index)
                worst_sample = int(sample_index)

    if elems.shape[0] == 0:
        minimum = float("nan")
    status = "PASS" if nonpositive == 0 else "FAIL"
    worst_coords = None
    if worst_sample is not None:
        worst_coords = tuple(float(v) for v in TET10_JACOBIAN_SAMPLE_POINTS_V1[worst_sample])
    return Tet10JacobianReport(
        schema="AsterMaxTet10SampledJacobianReportV1",
        status=status,
        element_count=int(elems.shape[0]),
        sample_count_per_element=int(TET10_JACOBIAN_SAMPLE_POINTS_V1.shape[0]),
        nonpositive_sample_count=int(nonpositive),
        minimum_determinant=float(minimum),
        worst_element_index=worst_element,
        worst_sample_index=worst_sample,
        worst_natural_coordinates=worst_coords,
        policy=asdict(policy),
        evidence_boundary=(
            "SAMPLED_ISOPARAMETRIC_JACOBIAN_ONLY_NOT_GLOBAL_POSITIVITY_PROOF_"
            "AND_DOES_NOT_ENABLE_CURVED_TET10_SOLVER"
        ),
    )


def require_tet10_sampled_jacobian(report: Tet10JacobianReport) -> None:
    if report.status != "PASS":
        raise ValueError(
            "TET10 sampled isoparametric Jacobian gate failed: "
            f"min_det={report.minimum_determinant:.17g}, "
            f"element={report.worst_element_index}, sample={report.worst_sample_index}, "
            f"natural={report.worst_natural_coordinates}"
        )
