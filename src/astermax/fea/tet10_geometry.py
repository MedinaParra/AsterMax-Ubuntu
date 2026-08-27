from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class Tet10GeometryScopeError(RuntimeError):
    """Raised when TET10 geometry is outside the currently verified solver scope."""


@dataclass(frozen=True)
class Tet10GeometryScopePolicy:
    relative_midpoint_tolerance: float = 1.0e-10
    absolute_floor_mm: float = 1.0e-12

    def validate(self) -> None:
        if not np.isfinite(self.relative_midpoint_tolerance) or self.relative_midpoint_tolerance <= 0.0:
            raise ValueError("relative_midpoint_tolerance must be finite and positive")
        if not np.isfinite(self.absolute_floor_mm) or self.absolute_floor_mm <= 0.0:
            raise ValueError("absolute_floor_mm must be finite and positive")

    def to_dict(self) -> dict[str, float]:
        self.validate()
        return {
            "relative_midpoint_tolerance": float(self.relative_midpoint_tolerance),
            "absolute_floor_mm": float(self.absolute_floor_mm),
        }


DEFAULT_TET10_GEOMETRY_SCOPE_POLICY = Tet10GeometryScopePolicy()


@dataclass(frozen=True)
class Tet10GeometryScopeReport:
    element_count: int
    non_straight_sided_elements: int
    max_midpoint_deviation_mm: float
    max_relative_midpoint_deviation: float
    worst_element_index: int
    status: str
    solver_scope: str
    policy: dict[str, float]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def _expected_midside_coordinates(coords: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            0.5 * (coords[:, 0] + coords[:, 1]),
            0.5 * (coords[:, 1] + coords[:, 2]),
            0.5 * (coords[:, 2] + coords[:, 0]),
            0.5 * (coords[:, 0] + coords[:, 3]),
            0.5 * (coords[:, 2] + coords[:, 3]),
            0.5 * (coords[:, 1] + coords[:, 3]),
        ]
    ).transpose(1, 0, 2)


def tet10_geometry_scope(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    policy: Tet10GeometryScopePolicy = DEFAULT_TET10_GEOMETRY_SCOPE_POLICY,
) -> Tet10GeometryScopeReport:
    """Measure whether TET10 midside nodes remain inside the verified straight-sided scope."""
    policy.validate()
    nodes = np.asarray(nodes_mm, dtype=float)
    conn = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if conn.ndim != 2 or conn.shape[1] != 10:
        raise ValueError("TET10 elements must have shape (m, 10)")
    if conn.size and (np.any(conn < 0) or np.any(conn >= nodes.shape[0])):
        raise ValueError("elements contains an out-of-range node index")
    if conn.shape[0] == 0:
        raise Tet10GeometryScopeError("mesh contains no TET10 elements")

    coords = nodes[conn]
    expected = _expected_midside_coordinates(coords)
    deviation = np.linalg.norm(coords[:, 4:] - expected, axis=2)
    max_dev_by_element = np.max(deviation, axis=1)
    corner_extent = np.linalg.norm(
        coords[:, :4].max(axis=1) - coords[:, :4].min(axis=1), axis=1
    )
    scale = np.maximum(corner_extent, policy.absolute_floor_mm)
    relative = max_dev_by_element / scale
    tolerance_mm = np.maximum(
        scale * policy.relative_midpoint_tolerance,
        policy.absolute_floor_mm,
    )
    outside = max_dev_by_element > tolerance_mm
    worst = int(np.argmax(relative))
    count = int(np.count_nonzero(outside))
    return Tet10GeometryScopeReport(
        element_count=int(conn.shape[0]),
        non_straight_sided_elements=count,
        max_midpoint_deviation_mm=float(np.max(max_dev_by_element)),
        max_relative_midpoint_deviation=float(np.max(relative)),
        worst_element_index=worst,
        status="FAIL" if count else "PASS",
        solver_scope="STRAIGHT_SIDED_TET10_FOUR_POINT_VERIFICATION",
        policy=policy.to_dict(),
    )


def require_tet10_geometry_scope(report: Tet10GeometryScopeReport) -> None:
    if report.status != "PASS":
        raise Tet10GeometryScopeError(
            "TET10 geometry preflight failed before assembly: "
            f"non_straight_sided={report.non_straight_sided_elements}, "
            f"max_midpoint_deviation_mm={report.max_midpoint_deviation_mm:.6g}, "
            f"max_relative_midpoint_deviation={report.max_relative_midpoint_deviation:.6g}, "
            f"worst_element={report.worst_element_index}; "
            "curved TET10 remains outside the verified solver scope"
        )
