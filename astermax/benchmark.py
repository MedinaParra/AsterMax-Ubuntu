"""Verification oracles for small, auditable AsterMax benchmarks.

These helpers do not replace 3D FEA.  They provide closed-form reference values
and explicit error metrics that a harness can compare against a numerical model.
All quantities use the AsterMax mm-N-MPa convention.
"""

from dataclasses import dataclass
import math
from typing import Iterable, Sequence


@dataclass(frozen=True)
class AxialBarReference:
    length_mm: float
    area_mm2: float
    young_mpa: float
    force_n: float
    displacement_mm: float
    stress_mpa: float


def axial_bar_reference(*, length_mm: float, area_mm2: float, young_mpa: float, force_n: float) -> AxialBarReference:
    """Return the Saint-Venant 1D axial-bar reference u=FL/(EA), sigma=F/A."""
    values = (length_mm, area_mm2, young_mpa, force_n)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("axial benchmark inputs must be finite")
    if length_mm <= 0.0 or area_mm2 <= 0.0 or young_mpa <= 0.0:
        raise ValueError("length, area and Young's modulus must be positive")
    return AxialBarReference(
        length_mm=length_mm,
        area_mm2=area_mm2,
        young_mpa=young_mpa,
        force_n=force_n,
        displacement_mm=force_n * length_mm / (young_mpa * area_mm2),
        stress_mpa=force_n / area_mm2,
    )


def relative_error(value: float, reference: float) -> float:
    """Absolute relative error; rejects a zero/non-finite reference explicitly."""
    if not math.isfinite(value) or not math.isfinite(reference):
        raise ValueError("error inputs must be finite")
    if reference == 0.0:
        raise ValueError("relative error requires a non-zero reference")
    return abs(value - reference) / abs(reference)


def mean_surface_displacement_x(displacements: Sequence[float], node_indices: Iterable[int]) -> float:
    """Average x displacement for a unique set of zero-based mesh node indices."""
    nodes = sorted(set(node_indices))
    if not nodes:
        raise ValueError("surface node set must not be empty")
    if len(displacements) % 3:
        raise ValueError("displacement vector length must be a multiple of three")
    node_count = len(displacements) // 3
    if nodes[0] < 0 or nodes[-1] >= node_count:
        raise ValueError("surface node index is outside the displacement vector")
    values = [displacements[3 * node] for node in nodes]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("surface displacement contains non-finite values")
    return sum(values) / len(values)
