from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np


@dataclass(frozen=True)
class NativeVtuPreviewData:
    schema: str
    points_mm: np.ndarray
    displacement_mm: np.ndarray
    tet10_connectivity: np.ndarray
    von_mises_ip_max_mpa: np.ndarray
    source_sha256: str
    converged_claim: bool
    industrial_validation_claim: bool
    stress_is_nodal: bool


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _array(root: ET.Element, xpath: str, *, dtype=float) -> np.ndarray:
    node = root.find(xpath)
    if node is None or node.text is None:
        raise ValueError(f"missing VTU array at {xpath}")
    return np.fromstring(node.text, sep=" ", dtype=dtype)


def load_native_vtu_preview(path: str | Path, *, expected_sha256: str) -> NativeVtuPreviewData:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    actual_sha = sha256_file(source)
    if actual_sha.lower() != str(expected_sha256).lower():
        raise ValueError("VTU hash mismatch; native preview refuses tampered result data")

    root = ET.parse(source).getroot()
    piece = root.find("./UnstructuredGrid/Piece")
    if piece is None:
        raise ValueError("invalid VTU: missing UnstructuredGrid/Piece")
    point_count = int(piece.attrib.get("NumberOfPoints", "0"))
    cell_count = int(piece.attrib.get("NumberOfCells", "0"))

    points = _array(piece, "./Points/DataArray[@Name='Coordinates_mm']").reshape((-1, 3))
    displacement = _array(piece, "./PointData/DataArray[@Name='U_mm']").reshape((-1, 3))
    connectivity = _array(piece, "./Cells/DataArray[@Name='connectivity']", dtype=np.int64).reshape((-1, 10))
    cell_types = _array(piece, "./Cells/DataArray[@Name='types']", dtype=np.int64)
    von_mises = _array(piece, "./CellData/DataArray[@Name='VON_MISES_IP_MAX_MPa']")

    if points.shape != (point_count, 3) or displacement.shape != points.shape:
        raise ValueError("VTU point/displacement shape mismatch")
    if connectivity.shape != (cell_count, 10) or von_mises.shape != (cell_count,):
        raise ValueError("VTU TET10/cell result shape mismatch")
    if cell_types.shape != (cell_count,) or np.any(cell_types != 24):
        raise ValueError("native preview supports VTK_QUADRATIC_TETRA type 24 only")
    if connectivity.size and (np.any(connectivity < 0) or np.any(connectivity >= point_count)):
        raise ValueError("VTU connectivity contains out-of-range point index")
    if not all(np.all(np.isfinite(x)) for x in (points, displacement, von_mises)):
        raise ValueError("native preview refuses non-finite VTU geometry or result data")

    def field_flag(name: str) -> bool:
        arr = piece.find(f"./FieldData/DataArray[@Name='{name}']")
        if arr is None or arr.text is None:
            raise ValueError(f"missing VTU field flag {name}")
        return int(arr.text.strip()) == 1

    return NativeVtuPreviewData(
        schema="AsterMaxNativeVtuPreviewV1",
        points_mm=points,
        displacement_mm=displacement,
        tet10_connectivity=connectivity,
        von_mises_ip_max_mpa=von_mises,
        source_sha256=actual_sha,
        converged_claim=field_flag("ASTERMAX_CONVERGED_CLAIM"),
        industrial_validation_claim=field_flag("ASTERMAX_INDUSTRIAL_VALIDATION_CLAIM"),
        stress_is_nodal=field_flag("ASTERMAX_STRESS_IS_NODAL"),
    )


def projected_preview_geometry(
    data: NativeVtuPreviewData,
    *,
    deformation_scale: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return deterministic 2D projected corner geometry and per-cell scalar.

    This is a lightweight native engineering preview, not a full 3D CAE renderer.
    It uses the actual hash-verified VTU geometry/results and preserves element
    von-Mises values without inventing nodal stress smoothing.
    """
    if not np.isfinite(deformation_scale):
        raise ValueError("deformation_scale must be finite")
    xyz = data.points_mm + float(deformation_scale) * data.displacement_mm
    centered = xyz - np.mean(xyz, axis=0, keepdims=True)
    if xyz.shape[0] >= 3:
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        basis = vh[:2].T
        projected = centered @ basis
    else:
        projected = centered[:, :2]
    return projected, data.von_mises_ip_max_mpa.copy()


def assert_native_preview_claim_boundary(data: NativeVtuPreviewData) -> None:
    if data.converged_claim:
        raise ValueError("native preview input unexpectedly claims convergence")
    if data.industrial_validation_claim:
        raise ValueError("native preview input unexpectedly claims industrial validation")
    if data.stress_is_nodal:
        raise ValueError("native preview refuses VTU claiming nodal stress")
