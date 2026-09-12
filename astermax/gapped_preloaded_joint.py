"""Explicit GAP + bolt pretension + updated surface friction coupling.

This module keeps source CAD coordinates immutable, applies an explicit non-negative
interface GAP field to a copy of the analysis geometry, and then solves the existing
preloaded node-to-TRI3 Coulomb contact formulation. Units: mm, N, MPa.

The purpose is verification and traceability: GAP is an explicit engineering input,
not an implicit geometry edit or a post-processing label.
"""

from dataclasses import dataclass
from typing import Mapping, Sequence

from .bolt_pretension import BoltPretensionConnector
from .interface_gap import InterfaceGapError, InterfaceGapResult, apply_interface_gap_field
from .preloaded_surface_joint import (
    PreloadedSurfaceJointError,
    PreloadedSurfaceJointResult,
    solve_preloaded_surface_joint_from_stiffness,
)


class GappedPreloadedJointError(ValueError):
    """Raised when GAP application or the coupled joint solve is invalid."""


@dataclass(frozen=True)
class GappedPreloadedJointResult:
    source_nodes: tuple[tuple[float, float, float], ...]
    gap: InterfaceGapResult
    joint: PreloadedSurfaceJointResult


def solve_gapped_preloaded_joint_from_stiffness(
    nodes: Sequence[Sequence[float]],
    structural_stiffness: Sequence[Sequence[float]],
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    connectors: Sequence[BoltPretensionConnector],
    *,
    gap_by_slave_mm: Mapping[int, float],
    slave_nodes: Sequence[int],
    master_triangles: Sequence[Sequence[int]],
    master_normal_hint: Sequence[float],
    **contact_kwargs,
) -> GappedPreloadedJointResult:
    """Apply explicit GAP to analysis geometry and solve the preloaded joint.

    ``nodes`` are treated as immutable source/CAD coordinates. Every slave node must
    have one explicit GAP value, including zero. The same slave/master semantics are
    then passed to the already harnessed updated frictional contact solver.
    """
    source = tuple(tuple(float(x) for x in p) for p in nodes)
    try:
        gap = apply_interface_gap_field(
            source, slave_nodes, master_normal_hint, gap_by_slave_mm
        )
    except InterfaceGapError as exc:
        raise GappedPreloadedJointError(str(exc)) from exc

    try:
        joint = solve_preloaded_surface_joint_from_stiffness(
            gap.nodes,
            structural_stiffness,
            constraints,
            loads,
            connectors,
            slave_nodes=slave_nodes,
            master_triangles=master_triangles,
            master_normal_hint=master_normal_hint,
            **contact_kwargs,
        )
    except PreloadedSurfaceJointError as exc:
        raise GappedPreloadedJointError(str(exc)) from exc

    return GappedPreloadedJointResult(source_nodes=source, gap=gap, joint=joint)
