from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from astermax.credibility import canonical_sha256
from .analytical_witness import LinearNormalStressWitness, build_linear_normal_stress_witness
from .circular_section import CircularSectionApplicability
from .circular_torsion import CircularTorsionWitness, build_circular_torsion_witness
from .section_evidence import PlanarSectionProperties
from .stress_envelope import CircularCombinedStressEnvelope, circular_combined_stress_envelope


class AnalyticalLoadCaseError(ValueError):
    pass


@dataclass(frozen=True)
class AnalyticalLoadCase:
    schema: str
    load_case_id: str
    selection_id: str
    section_sha256: str
    axial_force_n: float
    moment_u_nmm: float
    moment_v_nmm: float
    torque_nmm: float
    load_case_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("load_case_sha256")
        return payload


def build_analytical_load_case(
    *,
    load_case_id: str,
    selection_id: str,
    section_sha256: str,
    axial_force_n: float,
    moment_u_nmm: float,
    moment_v_nmm: float,
    torque_nmm: float,
) -> AnalyticalLoadCase:
    clean_id = str(load_case_id).strip()
    clean_selection = str(selection_id).strip()
    clean_sha = str(section_sha256).strip().lower()
    values = tuple(float(x) for x in (axial_force_n, moment_u_nmm, moment_v_nmm, torque_nmm))
    if not clean_id or not clean_selection:
        raise AnalyticalLoadCaseError("LOAD_CASE_IDENTIFIERS_MUST_BE_NONEMPTY")
    if len(clean_sha) != 64 or any(c not in "0123456789abcdef" for c in clean_sha):
        raise AnalyticalLoadCaseError("LOAD_CASE_SECTION_SHA_INVALID")
    if not all(math.isfinite(x) for x in values):
        raise AnalyticalLoadCaseError("LOAD_CASE_VALUES_MUST_BE_FINITE")

    payload = {
        "schema": "AsterMaxAnalyticalLoadCaseV1",
        "load_case_id": clean_id,
        "selection_id": clean_selection,
        "section_sha256": clean_sha,
        "axial_force_n": values[0],
        "moment_u_nmm": values[1],
        "moment_v_nmm": values[2],
        "torque_nmm": values[3],
    }
    return AnalyticalLoadCase(**payload, load_case_sha256=canonical_sha256(payload))


def build_load_case_witnesses(
    section: PlanarSectionProperties,
    applicability: CircularSectionApplicability,
    load_case: AnalyticalLoadCase,
) -> tuple[LinearNormalStressWitness, CircularTorsionWitness, CircularCombinedStressEnvelope]:
    if load_case.selection_id != section.selection_id or load_case.selection_id != applicability.selection_id:
        raise AnalyticalLoadCaseError("LOAD_CASE_SELECTION_MISMATCH")
    if load_case.section_sha256 != section.section_sha256:
        raise AnalyticalLoadCaseError("LOAD_CASE_SECTION_SHA_MISMATCH")
    if applicability.section_sha256 != section.section_sha256:
        raise AnalyticalLoadCaseError("LOAD_CASE_APPLICABILITY_SHA_MISMATCH")

    normal = build_linear_normal_stress_witness(
        section,
        axial_force_n=load_case.axial_force_n,
        moment_u_nmm=load_case.moment_u_nmm,
        moment_v_nmm=load_case.moment_v_nmm,
    )
    torsion = build_circular_torsion_witness(
        section,
        applicability,
        torque_nmm=load_case.torque_nmm,
    )
    envelope = circular_combined_stress_envelope(normal, torsion)
    return normal, torsion, envelope
