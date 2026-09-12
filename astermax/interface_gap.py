"""Explicit spatial interface GAP field for AsterMax verification cases.

The GAP field is applied to a copy of the analysis geometry, never to the source CAD
coordinates. A positive gap moves a slave node along the declared master normal and
therefore represents an initially open interface. Units are mm.
"""

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Mapping, Sequence


class InterfaceGapError(ValueError):
    """Raised when an explicit interface GAP field is invalid."""


@dataclass(frozen=True)
class InterfaceGapResult:
    nodes: tuple[tuple[float, float, float], ...]
    gap_by_slave_mm: tuple[tuple[int, float], ...]
    max_gap_mm: float
    mean_gap_mm: float
    gapped_slave_count: int


def _unit(vector: Sequence[float]) -> tuple[float, float, float]:
    if len(vector) != 3:
        raise InterfaceGapError("master normal hint must contain three components")
    v = tuple(float(x) for x in vector)
    if not all(isfinite(x) for x in v):
        raise InterfaceGapError("master normal hint must be finite")
    norm = sqrt(sum(x*x for x in v))
    if norm <= 0.0:
        raise InterfaceGapError("master normal hint must be non-zero")
    return tuple(x/norm for x in v)


def apply_interface_gap_field(
    nodes: Sequence[Sequence[float]],
    slave_nodes: Sequence[int],
    master_normal_hint: Sequence[float],
    gap_by_slave_mm: Mapping[int, float],
) -> InterfaceGapResult:
    """Return analysis nodes with a non-negative initial GAP applied to slaves.

    Every slave must have an explicit gap entry. Positive GAP is OPEN along the
    normalized master normal; zero GAP leaves that node unchanged. The input node
    sequence is not mutated.
    """
    if not nodes or any(len(p) != 3 for p in nodes):
        raise InterfaceGapError("nodes must contain 3D coordinates")
    base = tuple(tuple(float(x) for x in p) for p in nodes)
    if any(not isfinite(x) for p in base for x in p):
        raise InterfaceGapError("node coordinates must be finite")
    slaves = tuple(sorted(set(int(i) for i in slave_nodes)))
    if not slaves:
        raise InterfaceGapError("at least one slave node is required")
    if any(i < 0 or i >= len(base) for i in slaves):
        raise InterfaceGapError("slave surface references an unknown node")
    keys = {int(i) for i in gap_by_slave_mm.keys()}
    if keys != set(slaves):
        raise InterfaceGapError("GAP field must define exactly every slave node")
    normal = _unit(master_normal_hint)
    values = []
    moved = [list(p) for p in base]
    for slave in slaves:
        gap = float(gap_by_slave_mm[slave])
        if not isfinite(gap) or gap < 0.0:
            raise InterfaceGapError("interface GAP must be finite and non-negative")
        values.append((slave, gap))
        for c in range(3):
            moved[slave][c] += gap * normal[c]
    gaps = [g for _, g in values]
    return InterfaceGapResult(
        nodes=tuple(tuple(p) for p in moved),
        gap_by_slave_mm=tuple(values),
        max_gap_mm=max(gaps),
        mean_gap_mm=sum(gaps)/len(gaps),
        gapped_slave_count=sum(g > 0.0 for g in gaps),
    )
