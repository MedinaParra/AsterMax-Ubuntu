from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from astermax.credibility import canonical_sha256
from .arbitrary_bc import ArbitraryBcSolveEvidence
from .results_workspace import (
    AsterMaxProfessionalResultsWorkspaceV1,
    build_professional_results_workspace,
)
from .results_workspace_ui import ResultsRenderPayloadV1, build_results_render_payload
from .solver import Tet10LinearStaticResult


@dataclass(frozen=True)
class AsterMaxProductionResultsBundleV1:
    schema: str
    solve_evidence_sha256: str
    workspace_sha256: str
    displacement_field: str
    stress_field: str
    displacement_value_min_mm: float
    displacement_value_max_mm: float
    von_mises_value_min_mpa: float
    von_mises_value_max_mpa: float
    stress_representation: str
    converged_claim: bool
    industrial_validation_claim: bool
    ansys_equivalence_claim: bool
    bundle_sha256: str


class ProductionResultsError(ValueError):
    pass


def build_production_results_bundle(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
    solve_evidence: ArbitraryBcSolveEvidence,
    *,
    deformation_scale: float = 1.0,
) -> tuple[
    AsterMaxProductionResultsBundleV1,
    AsterMaxProfessionalResultsWorkspaceV1,
    ResultsRenderPayloadV1,
    ResultsRenderPayloadV1,
]:
    """Build the exact production postprocess contract from one verified solve.

    No stress extrapolation, nodal averaging, smoothing, convergence claim,
    industrial-validation claim, or ANSYS-equivalence claim is introduced here.
    The only stress contour currently admitted is the explicit per-element
    maximum of the four TET10 integration-point von Mises values.
    """
    if not isinstance(solve_evidence, ArbitraryBcSolveEvidence):
        raise ProductionResultsError("PRODUCTION_RESULTS_SOLVE_EVIDENCE_REQUIRED")
    if solve_evidence.converged or solve_evidence.industrial_validation or solve_evidence.ansys_equivalence:
        raise ProductionResultsError("PRODUCTION_RESULTS_FALSE_CLAIM_REFUSED")
    if len(solve_evidence.solve_evidence_sha256) != 64:
        raise ProductionResultsError("PRODUCTION_RESULTS_SOLVE_SHA_INVALID")

    workspace = build_professional_results_workspace(
        nodes_mm,
        elements,
        result,
        solve_evidence_sha256=solve_evidence.solve_evidence_sha256,
        deformation_scale=float(deformation_scale),
        converged_claim=False,
        industrial_validation_claim=False,
        ansys_equivalence_claim=False,
    )
    displacement = build_results_render_payload(
        workspace,
        nodes_mm,
        elements,
        result,
        field="U_MAG",
        deformation_scale=float(deformation_scale),
    )
    stress = build_results_render_payload(
        workspace,
        nodes_mm,
        elements,
        result,
        field="VON_MISES_IP_MAX",
        deformation_scale=float(deformation_scale),
    )

    for payload in (displacement, stress):
        if payload.workspace_sha256 != workspace.workspace_sha256:
            raise ProductionResultsError("PRODUCTION_RESULTS_WORKSPACE_STALE")
        if payload.solve_evidence_sha256 != solve_evidence.solve_evidence_sha256:
            raise ProductionResultsError("PRODUCTION_RESULTS_SOLVE_PROVENANCE_STALE")

    core = {
        "schema": "AsterMaxProductionResultsBundleV1",
        "solve_evidence_sha256": solve_evidence.solve_evidence_sha256,
        "workspace_sha256": workspace.workspace_sha256,
        "displacement_field": displacement.field,
        "stress_field": stress.field,
        "displacement_value_min_mm": displacement.value_min,
        "displacement_value_max_mm": displacement.value_max,
        "von_mises_value_min_mpa": stress.value_min,
        "von_mises_value_max_mpa": stress.value_max,
        "stress_representation": workspace.stress_representation,
        "converged_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
    }
    bundle = AsterMaxProductionResultsBundleV1(**core, bundle_sha256=canonical_sha256(core))
    return bundle, workspace, displacement, stress


def production_results_metadata(bundle: AsterMaxProductionResultsBundleV1) -> dict:
    if not isinstance(bundle, AsterMaxProductionResultsBundleV1):
        raise ProductionResultsError("PRODUCTION_RESULTS_BUNDLE_REQUIRED")
    payload = asdict(bundle)
    core = dict(payload)
    claimed_sha = core.pop("bundle_sha256")
    if canonical_sha256(core) != claimed_sha:
        raise ProductionResultsError("PRODUCTION_RESULTS_BUNDLE_SHA_MISMATCH")
    return payload
