from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Iterable


@dataclass(frozen=True)
class AnalyticalFemQoiV1:
    qoi_id: str
    analytical_value: float
    fem_value: float
    unit: str
    abs_error: float
    rel_error: float
    abs_limit: float
    rel_limit: float
    status: str
    evidence_sha256: str


@dataclass(frozen=True)
class AnalyticalFemVerificationMatrixV1:
    schema: str
    semantics: str
    source_step_sha256: str
    solve_evidence_sha256: str
    analytical_chain_sha256: str
    units_contract: tuple[tuple[str, str], ...]
    status: str
    blockers: tuple[str, ...]
    qois: tuple[AnalyticalFemQoiV1, ...]
    matrix_sha256: str
    industrial_validation: bool
    ansys_equivalence: bool


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _finite(name: str, value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"ANALYTICAL_FEM_NONFINITE:{name}")
    return result


def compare_scalar_qoi(*, qoi_id: str, analytical_value: float, fem_value: float, unit: str, abs_limit: float, rel_limit: float, scale_floor: float | None = None) -> AnalyticalFemQoiV1:
    if not qoi_id or not unit:
        raise ValueError("ANALYTICAL_FEM_QOI_ID_UNIT")
    analytical = _finite("analytical_value", analytical_value)
    fem = _finite("fem_value", fem_value)
    abs_tol = _finite("abs_limit", abs_limit)
    rel_tol = _finite("rel_limit", rel_limit)
    if abs_tol < 0.0 or rel_tol < 0.0:
        raise ValueError("ANALYTICAL_FEM_NEGATIVE_LIMIT")
    floor = abs(analytical) if scale_floor is None else abs(_finite("scale_floor", scale_floor))
    scale = max(abs(analytical), floor, 1.0e-30)
    abs_error = abs(fem - analytical)
    rel_error = abs_error / scale
    status = "PASS" if abs_error <= abs_tol and rel_error <= rel_tol else "FAIL"
    identity = {"schema":"AsterMaxAnalyticalFemQoiV1","qoi_id":str(qoi_id),"analytical_value":analytical,"fem_value":fem,"unit":str(unit),"abs_error":abs_error,"rel_error":rel_error,"abs_limit":abs_tol,"rel_limit":rel_tol,"scale_floor":floor,"status":status}
    return AnalyticalFemQoiV1(str(qoi_id), analytical, fem, str(unit), abs_error, rel_error, abs_tol, rel_tol, status, _sha(identity))


def build_analytical_fem_verification_matrix(qois: Iterable[AnalyticalFemQoiV1], *, source_step_sha256: str, solve_evidence_sha256: str, analytical_chain_sha256: str, length_unit: str = "mm", force_unit: str = "N", stress_unit: str = "MPa") -> AnalyticalFemVerificationMatrixV1:
    if not source_step_sha256 or not solve_evidence_sha256 or not analytical_chain_sha256:
        raise ValueError("ANALYTICAL_FEM_PROVENANCE_REQUIRED")
    units = (("length", str(length_unit)), ("force", str(force_unit)), ("stress", str(stress_unit)))
    if units != (("length", "mm"), ("force", "N"), ("stress", "MPa")):
        raise ValueError("ANALYTICAL_FEM_UNITS_CONTRACT")
    values = tuple(qois)
    if not values:
        raise ValueError("ANALYTICAL_FEM_QOIS_REQUIRED")
    ids = tuple(item.qoi_id for item in values)
    if len(set(ids)) != len(ids):
        raise ValueError("ANALYTICAL_FEM_DUPLICATE_QOI")
    blockers = tuple(f"QOI_FAILED:{item.qoi_id}" for item in values if item.status != "PASS")
    status = "CORROBORATED" if not blockers else "BLOCKED"
    identity = {"schema":"AsterMaxAnalyticalFemVerificationMatrixV1","semantics":"independent_analytical_witness_vs_exact_fem_qoi_fail_closed","source_step_sha256":str(source_step_sha256),"solve_evidence_sha256":str(solve_evidence_sha256),"analytical_chain_sha256":str(analytical_chain_sha256),"units_contract":[list(item) for item in units],"status":status,"blockers":list(blockers),"qois":[item.__dict__ for item in values],"industrial_validation":False,"ansys_equivalence":False}
    return AnalyticalFemVerificationMatrixV1("AsterMaxAnalyticalFemVerificationMatrixV1","independent_analytical_witness_vs_exact_fem_qoi_fail_closed",str(source_step_sha256),str(solve_evidence_sha256),str(analytical_chain_sha256),units,status,blockers,values,_sha(identity),False,False)


def axial_far_field_matrix(*, source_step_sha256: str, solve_evidence_sha256: str, analytical_chain_sha256: str, force_n: float, area_mm2: float, fem_sigma_x_mpa: float, fem_von_mises_mpa: float, fem_sigma_y_mpa: float, fem_sigma_z_mpa: float, fem_tau_xy_mpa: float, fem_tau_yz_mpa: float, fem_tau_xz_mpa: float, relative_limit: float = 0.02) -> AnalyticalFemVerificationMatrixV1:
    force = _finite("force_n", force_n)
    area = _finite("area_mm2", area_mm2)
    if area <= 0.0:
        raise ValueError("ANALYTICAL_FEM_AREA")
    rel = _finite("relative_limit", relative_limit)
    if rel <= 0.0:
        raise ValueError("ANALYTICAL_FEM_RELATIVE_LIMIT")
    nominal = force / area
    scale = abs(nominal)
    abs_limit = rel * scale
    observations = (("SIGMA_X_MEAN",nominal,fem_sigma_x_mpa),("VON_MISES_MEAN",abs(nominal),fem_von_mises_mpa),("SIGMA_Y_MEAN",0.0,fem_sigma_y_mpa),("SIGMA_Z_MEAN",0.0,fem_sigma_z_mpa),("TAU_XY_MEAN",0.0,fem_tau_xy_mpa),("TAU_YZ_MEAN",0.0,fem_tau_yz_mpa),("TAU_XZ_MEAN",0.0,fem_tau_xz_mpa))
    qois = tuple(compare_scalar_qoi(qoi_id=name, analytical_value=reference, fem_value=observed, unit="MPa", abs_limit=abs_limit, rel_limit=rel, scale_floor=scale) for name, reference, observed in observations)
    return build_analytical_fem_verification_matrix(qois, source_step_sha256=source_step_sha256, solve_evidence_sha256=solve_evidence_sha256, analytical_chain_sha256=analytical_chain_sha256)
