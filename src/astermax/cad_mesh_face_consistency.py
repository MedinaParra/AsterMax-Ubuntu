from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .face_resultant import triangulated_face_area_mm2


class CadMeshFaceConsistencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class CadMeshFaceConsistency:
    cad_face_id: str
    mesh_group: str
    cad_area_mm2: float
    mesh_area_mm2: float
    relative_area_error: float
    triangle_count: int
    verified: bool = True


def verify_cad_face_mesh_surface(*, cad_face_id: str, cad_area_mm2: float, mesh_group: str, mesh_nodes_mm: np.ndarray, mesh_triangles: np.ndarray, relative_area_tolerance: float = 5.0e-3) -> CadMeshFaceConsistency:
    face_id = str(cad_face_id).strip()
    group = str(mesh_group).strip()
    if not face_id:
        raise CadMeshFaceConsistencyError("CAD_FACE_ID_MISSING")
    if not group:
        raise CadMeshFaceConsistencyError("CAD_MESH_GROUP_MISSING")
    cad_area = float(cad_area_mm2)
    tolerance = float(relative_area_tolerance)
    if not np.isfinite(cad_area) or cad_area <= 0.0:
        raise CadMeshFaceConsistencyError("CAD_AREA_INVALID")
    if not np.isfinite(tolerance) or tolerance < 0.0 or tolerance >= 1.0:
        raise CadMeshFaceConsistencyError("CAD_MESH_AREA_TOLERANCE_INVALID")
    triangles = np.asarray(mesh_triangles, dtype=int)
    if triangles.ndim != 2 or triangles.shape[1] != 3 or triangles.shape[0] < 1:
        raise CadMeshFaceConsistencyError("CAD_MESH_TRIANGLES_INVALID")
    canonical = np.sort(triangles, axis=1)
    if np.unique(canonical, axis=0).shape[0] != canonical.shape[0]:
        raise CadMeshFaceConsistencyError("CAD_MESH_DUPLICATE_TRIANGLE")
    mesh_area = triangulated_face_area_mm2(mesh_nodes_mm, triangles)
    relative_error = abs(mesh_area - cad_area) / cad_area
    if relative_error > tolerance:
        raise CadMeshFaceConsistencyError("CAD_MESH_AREA_MISMATCH")
    return CadMeshFaceConsistency(face_id, group, cad_area, mesh_area, relative_error, int(triangles.shape[0]))
