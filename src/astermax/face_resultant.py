from __future__ import annotations

from dataclasses import dataclass
import numpy as np


class FaceResultantError(RuntimeError):
    pass


@dataclass(frozen=True)
class FaceResultantBinding:
    area_mm2: float
    requested_force_n: tuple[float, float, float]
    traction_n_per_mm2: tuple[float, float, float]
    recovered_force_n: tuple[float, float, float]
    residual_n: tuple[float, float, float]
    residual_norm_n: float
    representation: str = "UNIFORM_VECTOR_TRACTION_OVER_VERIFIED_TRIANGULATED_FACE"
    units: str = "mm/N/MPa"

    def as_evidence(self) -> dict[str, object]:
        return {
            "area_mm2": self.area_mm2,
            "requested_force_n": list(self.requested_force_n),
            "traction_n_per_mm2": list(self.traction_n_per_mm2),
            "recovered_force_n": list(self.recovered_force_n),
            "residual_n": list(self.residual_n),
            "residual_norm_n": self.residual_norm_n,
            "representation": self.representation,
            "units": self.units,
            "fea_solve_executed": False,
            "results_verified": False,
        }


def triangulated_face_area_mm2(nodes_mm: np.ndarray, triangles: np.ndarray) -> float:
    nodes = np.asarray(nodes_mm, dtype=float)
    tri = np.asarray(triangles, dtype=int)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or nodes.shape[0] < 3:
        raise FaceResultantError("FACE_RESULTANT_NODES_INVALID")
    if tri.ndim != 2 or tri.shape[1] != 3 or tri.shape[0] < 1:
        raise FaceResultantError("FACE_RESULTANT_TRIANGLES_INVALID")
    if not np.isfinite(nodes).all():
        raise FaceResultantError("FACE_RESULTANT_NODES_NONFINITE")
    if tri.min() < 0 or tri.max() >= nodes.shape[0]:
        raise FaceResultantError("FACE_RESULTANT_CONNECTIVITY_INVALID")

    p0 = nodes[tri[:, 0]]
    p1 = nodes[tri[:, 1]]
    p2 = nodes[tri[:, 2]]
    cross = np.cross(p1 - p0, p2 - p0)
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    if not np.isfinite(areas).all() or np.any(areas <= 0.0):
        raise FaceResultantError("FACE_RESULTANT_DEGENERATE_TRIANGLE")
    area = float(areas.sum())
    if not np.isfinite(area) or area <= 0.0:
        raise FaceResultantError("FACE_RESULTANT_AREA_INVALID")
    return area


def bind_force_resultant_to_uniform_traction(
    nodes_mm: np.ndarray,
    triangles: np.ndarray,
    force_n: tuple[float, float, float] | list[float] | np.ndarray,
    *,
    atol_n: float = 1.0e-10,
) -> FaceResultantBinding:
    area = triangulated_face_area_mm2(nodes_mm, triangles)
    force = np.asarray(force_n, dtype=float)
    if force.shape != (3,) or not np.isfinite(force).all():
        raise FaceResultantError("FACE_RESULTANT_FORCE_INVALID")
    if float(np.linalg.norm(force)) <= 0.0:
        raise FaceResultantError("FACE_RESULTANT_FORCE_ZERO")
    if not np.isfinite(atol_n) or atol_n < 0.0:
        raise FaceResultantError("FACE_RESULTANT_TOLERANCE_INVALID")

    traction = force / area
    recovered = traction * area
    residual = recovered - force
    residual_norm = float(np.linalg.norm(residual))
    scale = max(1.0, float(np.linalg.norm(force)))
    if residual_norm > atol_n * scale:
        raise FaceResultantError("FACE_RESULTANT_PRESERVATION_FAILED")

    return FaceResultantBinding(
        area_mm2=area,
        requested_force_n=tuple(float(v) for v in force),
        traction_n_per_mm2=tuple(float(v) for v in traction),
        recovered_force_n=tuple(float(v) for v in recovered),
        residual_n=tuple(float(v) for v in residual),
        residual_norm_n=residual_norm,
    )
