from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .tet10_jacobian import tet10_jacobian_matrix


@dataclass(frozen=True)
class Tet10JacobianReferencePolicy:
    subdivisions: int = 10
    determinant_epsilon: float = 1.0e-12
    schema: str = "TET10_BARYCENTRIC_LATTICE_REFERENCE_V1"

    def validate(self) -> None:
        if not isinstance(self.subdivisions, int) or self.subdivisions < 2:
            raise ValueError("subdivisions must be an integer >= 2")
        if not np.isfinite(self.determinant_epsilon) or self.determinant_epsilon <= 0.0:
            raise ValueError("determinant_epsilon must be finite and positive")
        if self.schema != "TET10_BARYCENTRIC_LATTICE_REFERENCE_V1":
            raise ValueError("unsupported TET10 Jacobian reference schema")


DEFAULT_TET10_JACOBIAN_REFERENCE_POLICY = Tet10JacobianReferencePolicy()


@dataclass(frozen=True)
class Tet10JacobianReferenceReport:
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


def barycentric_lattice_points(subdivisions: int) -> np.ndarray:
    if not isinstance(subdivisions, int) or subdivisions < 2:
        raise ValueError("subdivisions must be an integer >= 2")
    points: list[tuple[float, float, float]] = []
    n = float(subdivisions)
    for i in range(subdivisions + 1):
        for j in range(subdivisions + 1 - i):
            for k in range(subdivisions + 1 - i - j):
                points.append((i / n, j / n, k / n))
    return np.asarray(points, dtype=float)


def tet10_reference_jacobian_report(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    policy: Tet10JacobianReferencePolicy = DEFAULT_TET10_JACOBIAN_REFERENCE_POLICY,
) -> Tet10JacobianReferenceReport:
    """Scan det(J) on a declared dense barycentric lattice.

    This is a stronger deterministic reference scan than the 15-point gate, but it
    remains a finite sample set and therefore is deliberately not described as a
    mathematical proof of global positivity for an arbitrary curved TET10.
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

    points = barycentric_lattice_points(policy.subdivisions)
    minimum = np.inf
    worst_element: int | None = None
    worst_sample: int | None = None
    nonpositive = 0
    for element_index, conn in enumerate(elems):
        coords = nodes[conn]
        for sample_index, point in enumerate(points):
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
        worst_coords = tuple(float(v) for v in points[worst_sample])
    return Tet10JacobianReferenceReport(
        schema="AsterMaxTet10JacobianReferenceReportV1",
        status=status,
        element_count=int(elems.shape[0]),
        sample_count_per_element=int(points.shape[0]),
        nonpositive_sample_count=int(nonpositive),
        minimum_determinant=float(minimum),
        worst_element_index=worst_element,
        worst_sample_index=worst_sample,
        worst_natural_coordinates=worst_coords,
        policy=asdict(policy),
        evidence_boundary=(
            "DENSE_BARYCENTRIC_REFERENCE_SCAN_NOT_GLOBAL_POSITIVITY_PROOF_"
            "AND_DOES_NOT_ENABLE_CURVED_TET10_SOLVER"
        ),
    )


def require_tet10_reference_jacobian(report: Tet10JacobianReferenceReport) -> None:
    if report.status != "PASS":
        raise ValueError(
            "TET10 dense Jacobian reference gate failed: "
            f"min_det={report.minimum_determinant:.17g}, "
            f"element={report.worst_element_index}, sample={report.worst_sample_index}, "
            f"natural={report.worst_natural_coordinates}"
        )
