from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math


class CodeAsterReferenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class UniaxialPrismReference:
    """Closed-form small-strain isotropic uniaxial reference in mm/N/MPa.

    This is a numerical-verification oracle, not a solver. It is intended for a
    Code_Aster patch/reference case whose boundary conditions reproduce a
    homogeneous axial stress state.
    """

    length_mm: float
    width_mm: float
    height_mm: float
    young_mpa: float
    poisson: float
    axial_force_n: float

    def validate(self) -> None:
        vals = (
            self.length_mm,
            self.width_mm,
            self.height_mm,
            self.young_mpa,
            self.poisson,
            self.axial_force_n,
        )
        if not all(math.isfinite(float(v)) for v in vals):
            raise CodeAsterReferenceError("REFERENCE_NONFINITE_INPUT")
        if min(self.length_mm, self.width_mm, self.height_mm) <= 0.0:
            raise CodeAsterReferenceError("REFERENCE_GEOMETRY_MUST_BE_POSITIVE")
        if self.young_mpa <= 0.0:
            raise CodeAsterReferenceError("REFERENCE_YOUNG_MUST_BE_POSITIVE")
        if not (-1.0 < self.poisson < 0.5):
            raise CodeAsterReferenceError("REFERENCE_POISSON_OUT_OF_RANGE")
        if self.axial_force_n == 0.0:
            raise CodeAsterReferenceError("REFERENCE_FORCE_MUST_BE_NONZERO")

    @property
    def area_mm2(self) -> float:
        self.validate()
        return self.width_mm * self.height_mm

    @property
    def axial_traction_mpa(self) -> float:
        return self.axial_force_n / self.area_mm2

    @property
    def axial_stress_mpa(self) -> float:
        return self.axial_traction_mpa

    @property
    def axial_strain(self) -> float:
        return self.axial_stress_mpa / self.young_mpa

    @property
    def end_displacement_mm(self) -> float:
        return self.axial_strain * self.length_mm

    @property
    def transverse_strain(self) -> float:
        return -self.poisson * self.axial_strain

    def evidence(self) -> dict[str, float | str | bool]:
        self.validate()
        payload: dict[str, float | str | bool] = {
            "reference_kind": "HOMOGENEOUS_UNIAXIAL_PRISM_SMALL_STRAIN",
            "units_length": "mm",
            "units_force": "N",
            "units_stress": "MPa",
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "area_mm2": self.area_mm2,
            "young_mpa": self.young_mpa,
            "poisson": self.poisson,
            "axial_force_n": self.axial_force_n,
            "axial_traction_mpa": self.axial_traction_mpa,
            "expected_axial_stress_mpa": self.axial_stress_mpa,
            "expected_axial_strain": self.axial_strain,
            "expected_end_displacement_mm": self.end_displacement_mm,
            "expected_transverse_strain": self.transverse_strain,
            "fea_solve_executed": False,
            "numerical_verification": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
        }
        digest_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload["reference_sha256"] = sha256(digest_payload).hexdigest()
        return payload


@dataclass(frozen=True)
class ReferenceObservation:
    end_displacement_mm: float
    support_reaction_x_n: float
    axial_stress_mpa: float
    result_med_sha256: str
    solve_evidence_sha256: str
    fea_solve_executed: bool

    def validate(self) -> None:
        if not self.fea_solve_executed:
            raise CodeAsterReferenceError("REFERENCE_OBSERVATION_REQUIRES_REAL_SOLVE_EVIDENCE")
        for value in (self.end_displacement_mm, self.support_reaction_x_n, self.axial_stress_mpa):
            if not math.isfinite(float(value)):
                raise CodeAsterReferenceError("REFERENCE_OBSERVATION_NONFINITE")
        for value, code in (
            (self.result_med_sha256, "REFERENCE_RESULT_MED_SHA256_INVALID"),
            (self.solve_evidence_sha256, "REFERENCE_SOLVE_EVIDENCE_SHA256_INVALID"),
        ):
            if len(value) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in value):
                raise CodeAsterReferenceError(code)


@dataclass(frozen=True)
class ReferenceVerification:
    displacement_relative_error: float
    reaction_relative_error: float
    stress_relative_error: float
    displacement_pass: bool
    reaction_pass: bool
    stress_pass: bool
    sign_pass: bool
    numerical_verification: bool
    results_verified: bool
    industrial_validation: bool = False
    ansys_equivalence: bool = False


def _relative_error(actual: float, expected: float) -> float:
    scale = max(abs(expected), 1.0e-15)
    return abs(actual - expected) / scale


def verify_uniaxial_reference(
    reference: UniaxialPrismReference,
    observation: ReferenceObservation,
    *,
    displacement_rtol: float = 0.02,
    reaction_rtol: float = 0.005,
    stress_rtol: float = 0.02,
) -> ReferenceVerification:
    """Numerically verify one genuine Code_Aster solve against closed form.

    Passing this function validates only this reference problem at the declared
    tolerances. It does not establish arbitrary-model accuracy, industrial
    validation, or equivalence with ANSYS.
    """
    reference.validate()
    observation.validate()
    for tol in (displacement_rtol, reaction_rtol, stress_rtol):
        if not math.isfinite(float(tol)) or tol <= 0.0 or tol >= 1.0:
            raise CodeAsterReferenceError("REFERENCE_TOLERANCE_INVALID")

    expected_u = reference.end_displacement_mm
    expected_reaction = -reference.axial_force_n
    expected_stress = reference.axial_stress_mpa

    du = _relative_error(observation.end_displacement_mm, expected_u)
    dr = _relative_error(observation.support_reaction_x_n, expected_reaction)
    ds = _relative_error(observation.axial_stress_mpa, expected_stress)
    sign_pass = (
        math.copysign(1.0, observation.end_displacement_mm) == math.copysign(1.0, expected_u)
        and math.copysign(1.0, observation.support_reaction_x_n) == math.copysign(1.0, expected_reaction)
        and math.copysign(1.0, observation.axial_stress_mpa) == math.copysign(1.0, expected_stress)
    )
    displacement_pass = du <= displacement_rtol
    reaction_pass = dr <= reaction_rtol
    stress_pass = ds <= stress_rtol
    verified = bool(sign_pass and displacement_pass and reaction_pass and stress_pass)
    return ReferenceVerification(
        displacement_relative_error=du,
        reaction_relative_error=dr,
        stress_relative_error=ds,
        displacement_pass=displacement_pass,
        reaction_pass=reaction_pass,
        stress_pass=stress_pass,
        sign_pass=sign_pass,
        numerical_verification=verified,
        results_verified=verified,
    )
