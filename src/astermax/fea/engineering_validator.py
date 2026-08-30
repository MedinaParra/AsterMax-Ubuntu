from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

from .tet_quality import TetQualitySnapshot


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _field(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


@dataclass(frozen=True)
class EngineeringValidationCriteriaV1:
    minimum_tet_mean_ratio: float
    maximum_force_residual_n: float
    maximum_moment_residual_nmm: float


@dataclass(frozen=True)
class EngineeringValidationV1:
    schema: str
    status: str
    quality_snapshot_sha256: str
    solve_evidence_sha256: str
    mesh_quality_pass: bool
    force_equilibrium_pass: bool
    moment_equilibrium_pass: bool
    observed_minimum_tet_mean_ratio: float
    observed_force_residual_n: float
    observed_moment_residual_nmm: float
    criteria: EngineeringValidationCriteriaV1
    blockers: tuple[str, ...]
    claims: dict[str, bool]
    validation_sha256: str


def _validated_criteria(criteria: EngineeringValidationCriteriaV1) -> EngineeringValidationCriteriaV1:
    q = float(criteria.minimum_tet_mean_ratio)
    force = float(criteria.maximum_force_residual_n)
    moment = float(criteria.maximum_moment_residual_nmm)
    if not (math.isfinite(q) and 0.0 < q <= 1.0):
        raise ValueError("ENGINEERING_VALIDATOR_QUALITY_CRITERION")
    if not (math.isfinite(force) and force >= 0.0):
        raise ValueError("ENGINEERING_VALIDATOR_FORCE_CRITERION")
    if not (math.isfinite(moment) and moment >= 0.0):
        raise ValueError("ENGINEERING_VALIDATOR_MOMENT_CRITERION")
    return EngineeringValidationCriteriaV1(q, force, moment)


def validate_mesh_and_equilibrium(
    quality: TetQualitySnapshot,
    solve_evidence: Any,
    criteria: EngineeringValidationCriteriaV1,
) -> EngineeringValidationV1:
    """Independently classify existing mesh/solve evidence without changing physics.

    The acceptance thresholds are caller-supplied engineering criteria. This function
    deliberately does not infer convergence, industrial validity or ANSYS equivalence.
    """
    c = _validated_criteria(criteria)
    if quality.schema != "AsterMaxTetMeanRatioQualityV1":
        raise ValueError("ENGINEERING_VALIDATOR_QUALITY_SCHEMA")
    if quality.ansys_metric_equivalence:
        raise ValueError("ENGINEERING_VALIDATOR_ANSYS_METRIC_OVERCLAIM")
    if not quality.crosscheck_verified:
        raise ValueError("ENGINEERING_VALIDATOR_QUALITY_CROSSCHECK_REQUIRED")

    force = _field(solve_evidence, "force_residual_n")
    moment = _field(solve_evidence, "moment_residual_nmm")
    solve_sha = _field(solve_evidence, "solve_evidence_sha256")
    if force is None or moment is None or not isinstance(solve_sha, str) or len(solve_sha) != 64:
        raise ValueError("ENGINEERING_VALIDATOR_SOLVE_EVIDENCE_REQUIRED")
    force = float(force)
    moment = float(moment)
    if not math.isfinite(force) or not math.isfinite(moment):
        raise ValueError("ENGINEERING_VALIDATOR_NONFINITE_RESIDUAL")
    if force < 0.0 or moment < 0.0:
        raise ValueError("ENGINEERING_VALIDATOR_NEGATIVE_RESIDUAL")

    mesh_pass = bool(float(quality.minimum) >= c.minimum_tet_mean_ratio)
    force_pass = bool(force <= c.maximum_force_residual_n)
    moment_pass = bool(moment <= c.maximum_moment_residual_nmm)
    blockers: list[str] = []
    if not mesh_pass:
        blockers.append("MESH_QUALITY_BELOW_EXPLICIT_CRITERION")
    if not force_pass:
        blockers.append("FORCE_RESIDUAL_ABOVE_EXPLICIT_CRITERION")
    if not moment_pass:
        blockers.append("MOMENT_RESIDUAL_ABOVE_EXPLICIT_CRITERION")

    status = "PASS" if not blockers else "FAIL"
    claims = {
        "converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    core = {
        "schema": "AsterMaxEngineeringValidationV1",
        "status": status,
        "quality_snapshot_sha256": quality.snapshot_sha256,
        "solve_evidence_sha256": solve_sha,
        "mesh_quality_pass": mesh_pass,
        "force_equilibrium_pass": force_pass,
        "moment_equilibrium_pass": moment_pass,
        "observed_minimum_tet_mean_ratio": float(quality.minimum),
        "observed_force_residual_n": force,
        "observed_moment_residual_nmm": moment,
        "criteria": {
            "minimum_tet_mean_ratio": c.minimum_tet_mean_ratio,
            "maximum_force_residual_n": c.maximum_force_residual_n,
            "maximum_moment_residual_nmm": c.maximum_moment_residual_nmm,
        },
        "blockers": blockers,
        "claims": claims,
    }
    return EngineeringValidationV1(
        schema=core["schema"],
        status=status,
        quality_snapshot_sha256=quality.snapshot_sha256,
        solve_evidence_sha256=solve_sha,
        mesh_quality_pass=mesh_pass,
        force_equilibrium_pass=force_pass,
        moment_equilibrium_pass=moment_pass,
        observed_minimum_tet_mean_ratio=float(quality.minimum),
        observed_force_residual_n=force,
        observed_moment_residual_nmm=moment,
        criteria=c,
        blockers=tuple(blockers),
        claims=claims,
        validation_sha256=_sha(core),
    )


def verify_validation_contract(report: EngineeringValidationV1) -> None:
    if report.schema != "AsterMaxEngineeringValidationV1":
        raise ValueError("ENGINEERING_VALIDATOR_SCHEMA")
    expected = "PASS" if not report.blockers else "FAIL"
    if report.status != expected:
        raise ValueError("ENGINEERING_VALIDATOR_STATUS_STALE")
    if report.claims != {
        "converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }:
        raise ValueError("ENGINEERING_VALIDATOR_CLAIM_BOUNDARY")
