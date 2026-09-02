from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import meshio
import numpy as np

from .cae_scene_contract import CaeSceneContract, validate_cae_scene_contract
from .persistent_viewport import extract_tet10_surface
from .results_scene import normalized_scalar
from .code_aster_reference_run import GenuineReferenceSolveEvidence


class CodeAsterMedResultError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodeAsterNodalResultSet:
    nodes_mm: np.ndarray
    tet10: np.ndarray
    displacement_mm: np.ndarray
    von_mises_mpa: np.ndarray
    displacement_field_name: str
    von_mises_field_name: str
    result_med_sha256: str
    field_location: str = "NOEU"
    length_unit: str = "mm"
    stress_unit: str = "MPa"


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _unique_field(point_data: dict[str, np.ndarray], token: str, *, width: int | None) -> tuple[str, np.ndarray]:
    token_upper = token.upper()
    candidates: list[tuple[str, np.ndarray]] = []
    for name, raw in point_data.items():
        if token_upper not in str(name).upper():
            continue
        values = np.asarray(raw, dtype=float)
        if width is None:
            if values.ndim == 1 or (values.ndim == 2 and values.shape[1] == 1):
                candidates.append((str(name), values.reshape(-1)))
        elif values.ndim == 2 and values.shape[1] == width:
            candidates.append((str(name), values))
    if not candidates:
        raise CodeAsterMedResultError(f"CODE_ASTER_RESULT_FIELD_MISSING:{token}")
    if len(candidates) != 1:
        names = ",".join(sorted(name for name, _ in candidates))
        raise CodeAsterMedResultError(f"CODE_ASTER_RESULT_FIELD_AMBIGUOUS:{token}:{names}")
    return candidates[0]


def read_verified_code_aster_nodal_results(
    result_med: str | Path,
    evidence: GenuineReferenceSolveEvidence,
) -> CodeAsterNodalResultSet:
    """Read display-safe nodal fields only from a mechanically verified Code_Aster MED.

    C8.8 deliberately accepts only NOEU-compatible fields represented by meshio as
    point_data. ELNO and ELGA data stay cell_data and are not silently projected or
    relabelled as nodal values. The result file hash must match the genuine solve
    evidence and that solve must already have passed numerical verification.
    """
    path = Path(result_med).expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise CodeAsterMedResultError("CODE_ASTER_RESULT_MED_MISSING")
    if not evidence.fea_solve_executed or not evidence.numerical_verification or not evidence.results_verified:
        raise CodeAsterMedResultError("CODE_ASTER_RESULT_SOLVE_NOT_VERIFIED")
    digest = _sha(path)
    if digest.lower() != evidence.result_med_sha256.lower():
        raise CodeAsterMedResultError("CODE_ASTER_RESULT_MED_HASH_MISMATCH")

    try:
        mesh = meshio.read(path)
    except Exception as exc:
        raise CodeAsterMedResultError("CODE_ASTER_RESULT_MED_READ_FAILED") from exc

    nodes = np.asarray(mesh.points, dtype=float)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or len(nodes) < 4 or not np.isfinite(nodes).all():
        raise CodeAsterMedResultError("CODE_ASTER_RESULT_NODES_INVALID")

    tet_blocks = [np.asarray(block.data, dtype=int) for block in mesh.cells if block.type == "tetra10"]
    if not tet_blocks:
        raise CodeAsterMedResultError("CODE_ASTER_RESULT_TET10_MISSING")
    tet10 = np.vstack(tet_blocks)
    if tet10.ndim != 2 or tet10.shape[1] != 10 or tet10.min() < 0 or tet10.max() >= len(nodes):
        raise CodeAsterMedResultError("CODE_ASTER_RESULT_TET10_INVALID")

    point_data = {str(k): np.asarray(v) for k, v in mesh.point_data.items() if str(k) != "point_tags"}
    displacement_name, displacement = _unique_field(point_data, "DEPL", width=3)
    mises_name, mises = _unique_field(point_data, "SIEQ_NOEU", width=None)
    if displacement.shape != (len(nodes), 3) or not np.isfinite(displacement).all():
        raise CodeAsterMedResultError("CODE_ASTER_RESULT_DISPLACEMENT_INVALID")
    if mises.shape != (len(nodes),) or not np.isfinite(mises).all() or np.any(mises < -1.0e-10):
        raise CodeAsterMedResultError("CODE_ASTER_RESULT_VON_MISES_INVALID")

    return CodeAsterNodalResultSet(
        nodes_mm=nodes,
        tet10=tet10,
        displacement_mm=displacement,
        von_mises_mpa=np.maximum(mises, 0.0),
        displacement_field_name=displacement_name,
        von_mises_field_name=mises_name,
        result_med_sha256=digest,
    )


def build_code_aster_cae_scene(
    results: CodeAsterNodalResultSet,
    evidence: GenuineReferenceSolveEvidence,
    *,
    deformation_scale: float = 1.0,
) -> CaeSceneContract:
    """Build the renderer-neutral professional scene from verified Code_Aster NOEU data."""
    if not np.isfinite(deformation_scale) or deformation_scale < 0.0:
        raise CodeAsterMedResultError("CODE_ASTER_SCENE_DEFORMATION_SCALE_INVALID")
    if results.result_med_sha256.lower() != evidence.result_med_sha256.lower():
        raise CodeAsterMedResultError("CODE_ASTER_SCENE_PROVENANCE_MISMATCH")

    inventory = type("Inventory", (), {"nodes_mm": results.nodes_mm, "elements": results.tet10})()
    _, triangles = extract_tet10_surface(inventory)
    deformed = results.nodes_mm + float(deformation_scale) * results.displacement_mm
    disp_mag = np.linalg.norm(results.displacement_mm, axis=1)
    tri_vm = results.von_mises_mpa[np.asarray(triangles, dtype=int)].mean(axis=1)
    nodal_norm = normalized_scalar(results.von_mises_mpa)
    tri_norm = nodal_norm[np.asarray(triangles, dtype=int)].mean(axis=1)
    solve_evidence_sha = sha256(str(sorted(evidence.as_dict().items())).encode("utf-8")).hexdigest()

    scene = CaeSceneContract(
        undeformed_nodes_mm=np.asarray(results.nodes_mm, dtype=float).copy(),
        deformed_nodes_mm=np.asarray(deformed, dtype=float),
        surface_triangles=np.asarray(triangles, dtype=int).copy(),
        nodal_von_mises_mpa=np.asarray(results.von_mises_mpa, dtype=float).copy(),
        triangle_von_mises_mpa=np.asarray(tri_vm, dtype=float),
        triangle_scalar_normalized=np.asarray(tri_norm, dtype=float),
        displacement_magnitude_mm=np.asarray(disp_mag, dtype=float),
        scalar_min_mpa=float(np.min(results.von_mises_mpa)),
        scalar_max_mpa=float(np.max(results.von_mises_mpa)),
        deformation_scale=float(deformation_scale),
        length_unit="mm",
        stress_unit="MPa",
        stress_representation=f"CODE_ASTER_SIEQ_NOEU:{results.von_mises_field_name};DISPLAY_SURFACE=NODE_AVERAGE_ONLY",
        workspace_sha256=results.result_med_sha256,
        solve_evidence_sha256=solve_evidence_sha,
    )
    validate_cae_scene_contract(scene)
    return scene
