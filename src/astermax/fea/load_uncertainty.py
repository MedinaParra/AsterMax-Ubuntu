from __future__ import annotations

from dataclasses import asdict, dataclass
import itertools
import math
from typing import Any

from astermax.credibility import canonical_sha256
from .analytical_load_case import AnalyticalLoadCase, build_analytical_load_case, build_load_case_witnesses
from .circular_section import CircularSectionApplicability
from .section_evidence import PlanarSectionProperties


class LoadUncertaintyError(ValueError):
    pass


@dataclass(frozen=True)
class LoadUncertaintyBounds:
    axial_force_delta_n: float
    moment_u_delta_nmm: float
    moment_v_delta_nmm: float
    torque_delta_nmm: float

    def __post_init__(self) -> None:
        values = (
            self.axial_force_delta_n,
            self.moment_u_delta_nmm,
            self.moment_v_delta_nmm,
            self.torque_delta_nmm,
        )
        if not all(math.isfinite(float(x)) and float(x) >= 0.0 for x in values):
            raise LoadUncertaintyError("LOAD_UNCERTAINTY_DELTAS_MUST_BE_FINITE_NONNEGATIVE")


@dataclass(frozen=True)
class LoadUncertaintyEnvelope:
    schema: str
    nominal_load_case_sha256: str
    section_sha256: str
    vertex_count: int
    nominal_max_von_mises_mpa: float
    worst_case_max_von_mises_mpa: float
    amplification_factor: float
    critical_vertex_load_case_sha256: str
    critical_vertex_resultants: tuple[float, float, float, float]
    method: str
    uncertainty_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("uncertainty_sha256")
        return payload


def bounded_load_uncertainty_envelope(
    section: PlanarSectionProperties,
    applicability: CircularSectionApplicability,
    nominal: AnalyticalLoadCase,
    bounds: LoadUncertaintyBounds,
) -> LoadUncertaintyEnvelope:
    _, _, nominal_envelope = build_load_case_witnesses(section, applicability, nominal)
    deltas = (
        float(bounds.axial_force_delta_n),
        float(bounds.moment_u_delta_nmm),
        float(bounds.moment_v_delta_nmm),
        float(bounds.torque_delta_nmm),
    )
    center = (
        nominal.axial_force_n,
        nominal.moment_u_nmm,
        nominal.moment_v_nmm,
        nominal.torque_nmm,
    )

    worst_vm = -math.inf
    critical = None
    critical_values = None
    for signs in itertools.product((-1.0, 1.0), repeat=4):
        values = tuple(float(c) + float(s) * float(d) for c, s, d in zip(center, signs, deltas))
        suffix = "".join("P" if s > 0.0 else "M" for s in signs)
        vertex = build_analytical_load_case(
            load_case_id=f"{nominal.load_case_id}_U_{suffix}",
            selection_id=nominal.selection_id,
            section_sha256=nominal.section_sha256,
            axial_force_n=values[0],
            moment_u_nmm=values[1],
            moment_v_nmm=values[2],
            torque_nmm=values[3],
        )
        _, _, envelope = build_load_case_witnesses(section, applicability, vertex)
        if envelope.max_von_mises_mpa > worst_vm:
            worst_vm = envelope.max_von_mises_mpa
            critical = vertex
            critical_values = values

    if critical is None or critical_values is None or not math.isfinite(worst_vm):
        raise LoadUncertaintyError("LOAD_UNCERTAINTY_VERTEX_SWEEP_FAILED")

    nominal_vm = float(nominal_envelope.max_von_mises_mpa)
    amplification = worst_vm / max(nominal_vm, 1.0e-30)
    payload = {
        "schema": "AsterMaxLoadUncertaintyEnvelopeV1",
        "nominal_load_case_sha256": nominal.load_case_sha256,
        "section_sha256": section.section_sha256,
        "vertex_count": 16,
        "nominal_max_von_mises_mpa": nominal_vm,
        "worst_case_max_von_mises_mpa": worst_vm,
        "amplification_factor": amplification,
        "critical_vertex_load_case_sha256": critical.load_case_sha256,
        "critical_vertex_resultants": tuple(float(x) for x in critical_values),
        "method": "EXACT_CONVEX_LINEAR_LOAD_RESPONSE_HYPERRECTANGLE_VERTEX_ENUMERATION",
    }
    return LoadUncertaintyEnvelope(**payload, uncertainty_sha256=canonical_sha256(payload))
