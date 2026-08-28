from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from .face_ownership import (
    ArbitraryNamedSelectionBinding,
    Tet10FaceOwnershipInventory,
    bind_named_selection_to_owned_faces,
    mesh_step_tet10_with_face_ownership,
)
from .gmsh_bridge import distribute_resultant_on_tri6, fixed_dofs_for_nodes, force_and_moment, unique_surface_nodes
from .named_selections import PersistentNamedSelection
from .solver import solve_linear_static_tet10
from .tet4 import IsotropicMaterial
from .tet_quality import build_tet10_corner_quality_snapshot, require_quality_crosscheck


class ArbitraryBcError(ValueError):
    pass


@dataclass(frozen=True)
class ArbitraryBcPreparation:
    schema: str
    source_step_sha256: str
    ownership_sha256: str
    support_named_selection_sha256: str
    load_named_selection_sha256: str
    support_binding_sha256: str
    load_binding_sha256: str
    support_face_signature_sha256: tuple[str, ...]
    load_face_signature_sha256: tuple[str, ...]
    support_tri6_count: int
    load_tri6_count: int
    node_count: int
    tet10_count: int
    tetra_quality_sha256: str
    tetra_quality_crosscheck_verified: bool
    preparation_sha256: str


@dataclass(frozen=True)
class ArbitraryBcSolveEvidence:
    schema: str
    preparation_sha256: str
    support_binding_sha256: str
    load_binding_sha256: str
    resultant_n: tuple[float, float, float]
    fixed_node_count: int
    force_residual_n: float
    moment_residual_nmm: float
    converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    solve_evidence_sha256: str


def prepare_arbitrary_bc_model(
    step_path: str | Path,
    *,
    mesh_size_mm: float,
    support_selection: PersistentNamedSelection,
    load_selection: PersistentNamedSelection,
) -> dict:
    """Prepare exact arbitrary CAD-face scopes for the production linear-static path.

    The support/load TRI6 arrays come only from persistent CAD-face ownership.
    Axis keys are intentionally absent from this contract.
    """
    inventory = mesh_step_tet10_with_face_ownership(step_path, mesh_size_mm)
    support_binding, support_triangles = bind_named_selection_to_owned_faces(
        step_path, support_selection, inventory, expected_role="SUPPORT"
    )
    load_binding, load_triangles = bind_named_selection_to_owned_faces(
        step_path, load_selection, inventory, expected_role="LOAD"
    )
    support_faces = set(support_binding.face_signature_sha256)
    load_faces = set(load_binding.face_signature_sha256)
    if support_faces & load_faces:
        raise ArbitraryBcError("ARBITRARY_SUPPORT_LOAD_FACE_OVERLAP")
    if support_binding.named_selection_sha256 == load_binding.named_selection_sha256:
        raise ArbitraryBcError("ARBITRARY_SUPPORT_LOAD_SELECTION_NOT_DISTINCT")

    quality = build_tet10_corner_quality_snapshot(inventory.nodes_mm, inventory.elements)
    require_quality_crosscheck(quality)

    core = {
        "schema": "AsterMaxArbitraryBcPreparationV1",
        "source_step_sha256": inventory.source_step_sha256,
        "ownership_sha256": inventory.ownership_sha256,
        "support_named_selection_sha256": support_binding.named_selection_sha256,
        "load_named_selection_sha256": load_binding.named_selection_sha256,
        "support_binding_sha256": support_binding.binding_sha256,
        "load_binding_sha256": load_binding.binding_sha256,
        "support_face_signature_sha256": list(support_binding.face_signature_sha256),
        "load_face_signature_sha256": list(load_binding.face_signature_sha256),
        "support_tri6_count": int(support_triangles.shape[0]),
        "load_tri6_count": int(load_triangles.shape[0]),
        "node_count": int(inventory.nodes_mm.shape[0]),
        "tet10_count": int(inventory.elements.shape[0]),
        "tetra_quality_sha256": quality.snapshot_sha256,
        "tetra_quality_crosscheck_verified": bool(quality.crosscheck_verified),
    }
    evidence = ArbitraryBcPreparation(**core, preparation_sha256=canonical_sha256(core))
    return {
        "inventory": inventory,
        "support_selection": support_selection,
        "load_selection": load_selection,
        "support_binding": support_binding,
        "load_binding": load_binding,
        "support_triangles": np.asarray(support_triangles, dtype=np.int64),
        "load_triangles": np.asarray(load_triangles, dtype=np.int64),
        "quality": quality,
        "evidence": evidence,
    }


def _verify_prepared(prepared: dict) -> tuple[Tet10FaceOwnershipInventory, ArbitraryNamedSelectionBinding, ArbitraryNamedSelectionBinding, np.ndarray, np.ndarray, ArbitraryBcPreparation]:
    inventory = prepared.get("inventory")
    support_binding = prepared.get("support_binding")
    load_binding = prepared.get("load_binding")
    support_triangles = np.asarray(prepared.get("support_triangles"), dtype=np.int64)
    load_triangles = np.asarray(prepared.get("load_triangles"), dtype=np.int64)
    evidence = prepared.get("evidence")
    if not isinstance(inventory, Tet10FaceOwnershipInventory):
        raise ArbitraryBcError("ARBITRARY_BC_INVENTORY_MISSING")
    if not isinstance(support_binding, ArbitraryNamedSelectionBinding) or not isinstance(load_binding, ArbitraryNamedSelectionBinding):
        raise ArbitraryBcError("ARBITRARY_BC_BINDING_MISSING")
    if not isinstance(evidence, ArbitraryBcPreparation):
        raise ArbitraryBcError("ARBITRARY_BC_EVIDENCE_MISSING")
    if support_binding.binding_sha256 != evidence.support_binding_sha256 or load_binding.binding_sha256 != evidence.load_binding_sha256:
        raise ArbitraryBcError("ARBITRARY_BC_BINDING_STALE")
    if inventory.ownership_sha256 != evidence.ownership_sha256:
        raise ArbitraryBcError("ARBITRARY_BC_OWNERSHIP_STALE")
    if support_triangles.ndim != 2 or support_triangles.shape[1] != 6 or load_triangles.ndim != 2 or load_triangles.shape[1] != 6:
        raise ArbitraryBcError("ARBITRARY_BC_TRI6_INVALID")
    if int(support_triangles.shape[0]) != evidence.support_tri6_count or int(load_triangles.shape[0]) != evidence.load_tri6_count:
        raise ArbitraryBcError("ARBITRARY_BC_TRI6_COUNT_STALE")
    return inventory, support_binding, load_binding, support_triangles, load_triangles, evidence


def solve_arbitrary_bc_model(
    prepared: dict,
    *,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
) -> dict:
    """Solve the exact arbitrary-face preparation through the production sparse TET10 solver."""
    inventory, support_binding, load_binding, support_triangles, load_triangles, evidence = _verify_prepared(prepared)
    material = IsotropicMaterial(float(young_modulus_mpa), float(poisson_ratio))
    resultant = np.asarray(resultant_n, dtype=float)
    if resultant.shape != (3,) or not np.all(np.isfinite(resultant)) or float(np.linalg.norm(resultant)) == 0.0:
        raise ArbitraryBcError("resultant_n must contain three finite components and be non-zero")

    fixed_nodes = unique_surface_nodes(support_triangles)
    fixed_dofs = fixed_dofs_for_nodes(fixed_nodes)
    loads = distribute_resultant_on_tri6(inventory.nodes_mm, load_triangles, resultant)
    applied_force, applied_moment = force_and_moment(inventory.nodes_mm, loads)
    result = solve_linear_static_tet10(inventory.nodes_mm, inventory.elements, material, loads, fixed_dofs)
    reaction_force, reaction_moment = force_and_moment(inventory.nodes_mm, result.reactions_n)
    force_residual = float(np.linalg.norm(reaction_force + applied_force))
    moment_residual = float(np.linalg.norm(reaction_moment + applied_moment))

    core = {
        "schema": "AsterMaxArbitraryBcSolveEvidenceV1",
        "preparation_sha256": evidence.preparation_sha256,
        "support_binding_sha256": support_binding.binding_sha256,
        "load_binding_sha256": load_binding.binding_sha256,
        "resultant_n": [float(v) for v in resultant],
        "fixed_node_count": int(fixed_nodes.size),
        "force_residual_n": force_residual,
        "moment_residual_nmm": moment_residual,
        "converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    solve_evidence = ArbitraryBcSolveEvidence(**core, solve_evidence_sha256=canonical_sha256(core))
    return {
        "result": result,
        "loads_n": loads,
        "fixed_nodes": fixed_nodes,
        "solve_evidence": solve_evidence,
    }
