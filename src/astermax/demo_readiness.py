from __future__ import annotations

from dataclasses import dataclass

from .cae_scene_contract import CaeSceneContract, validate_cae_scene_contract
from .code_aster_capabilities import CapabilityStatus, capability_by_id
from .windows_capability_outline import selection_contract


@dataclass(frozen=True)
class DemoStage:
    id: str
    label: str
    ready: bool
    evidence_required: str
    note: str


@dataclass(frozen=True)
class ProfessionalDemoReadiness:
    capability_id: str
    capability_status: CapabilityStatus
    gui_available: bool
    solver_claim_allowed: bool
    result_workspace_available: bool
    stages: tuple[DemoStage, ...]

    @property
    def complete_verified_chain(self) -> bool:
        return all(stage.ready for stage in self.stages)


def build_professional_demo_readiness(
    *,
    scene: CaeSceneContract | None = None,
    cad_step_mm_ready: bool = True,
    tet10_mesh_ready: bool = True,
    boundary_conditions_ready: bool = True,
    runtime_qualified: bool = False,
    genuine_solve_verified: bool = False,
) -> ProfessionalDemoReadiness:
    """Build one fail-closed readiness contract for the Windows technical demo.

    UI availability is deliberately distinct from solver verification. A verified
    result scene may only unlock postprocessing after the genuine solve gate has
    passed; a synthetic or legacy scene cannot upgrade solver credibility.
    """
    capability = capability_by_id("structural.linear_static_3d")
    selection = selection_contract(capability.id)

    scene_verified = False
    if scene is not None:
        validate_cae_scene_contract(scene)
        scene_verified = bool(genuine_solve_verified)

    stages = (
        DemoStage("cad", "CAD / STEP [mm]", bool(cad_step_mm_ready), "STEP import with mm contract", "Geometry preparation"),
        DemoStage("mesh", "Quadratic tetrahedral mesh", bool(tet10_mesh_ready), "TET10/TRI6 semantic mesh", "Solver-oriented meshing"),
        DemoStage("bc", "Boundary conditions", bool(boundary_conditions_ready), "Persistent CAD-face BC/load bindings", "Model preparation"),
        DemoStage("runtime", "Qualified Code_Aster runtime", bool(runtime_qualified), "Immutable runtime fingerprint", "Execution provenance"),
        DemoStage("solve", "Genuine FEA solve", bool(genuine_solve_verified), ".mess OK + fresh MED + mechanical oracle", "No process-double evidence accepted"),
        DemoStage("results", "Professional result workspace", scene_verified, "Verified MED-derived CAE scene", "SIEQ/DEPL/probes/clip/legend"),
    )

    return ProfessionalDemoReadiness(
        capability_id=capability.id,
        capability_status=capability.status,
        gui_available=selection.enabled,
        solver_claim_allowed=capability.solver_claim_allowed and genuine_solve_verified,
        result_workspace_available=scene_verified,
        stages=stages,
    )


def demo_readiness_evidence() -> dict[str, object]:
    readiness = build_professional_demo_readiness()
    return {
        "contract": "ASTERMAX_PROFESSIONAL_DEMO_READINESS_V1",
        "capability_id": readiness.capability_id,
        "capability_status": readiness.capability_status.value,
        "gui_available": readiness.gui_available,
        "solver_claim_allowed": readiness.solver_claim_allowed,
        "result_workspace_available": readiness.result_workspace_available,
        "stage_ready": {stage.id: stage.ready for stage in readiness.stages},
        "complete_verified_chain": readiness.complete_verified_chain,
        "fea_solve_executed": False,
        "numerical_verification": False,
        "results_verified": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
