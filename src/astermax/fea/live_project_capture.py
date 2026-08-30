from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from astermax.credibility import canonical_sha256
from .adaptive_hotspot_visualization import AdaptiveHotspotVisualizationV1
from .adaptive_stress_comparison import AdaptiveStressComparisonV1
from .project_authoring import append_verified_results_revision, verify_project_authoring_receipt
from .project_session_shell import open_verified_project_session
from .unified_project_model import open_unified_project, verify_unified_project


class LiveProjectCaptureError(ValueError):
    pass


@dataclass(frozen=True)
class LiveProjectCaptureReceiptV1:
    schema: str
    status: str
    project_path: str
    result_package_path: str
    source_step_sha256: str
    revision: int
    revision_sha256: str
    project_sha256: str
    session_sha256: str
    native_results_bound: bool
    project_tree_refresh_requested: bool
    solver_executed_by_capture: bool
    gmsh_executed_by_capture: bool
    physics_changed_by_capture: bool
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    receipt_sha256: str


class LiveProjectCaptureCoordinatorV1:
    """Bridge a verified live `.astermaxr` result into the active `.astermax` project.

    The coordinator owns no FEA physics. It only verifies project/result identity,
    appends a revision, restores the verified portable Results views, and requests
    a project-tree refresh. Solver and Gmsh execution belong upstream.
    """

    def __init__(
        self,
        *,
        hotspot_binder: Callable[[AdaptiveHotspotVisualizationV1], None],
        stress_binder: Callable[[AdaptiveStressComparisonV1], None],
        on_project_changed: Callable[[str], None] | None = None,
        recent_store_path: str | Path | None = None,
    ) -> None:
        self._hotspot_binder = hotspot_binder
        self._stress_binder = stress_binder
        self._on_project_changed = on_project_changed
        self._recent_store_path = recent_store_path
        self._active_project_path: str | None = None

    @property
    def active_project_path(self) -> str | None:
        return self._active_project_path

    def configure_project_refresh(self, callback: Callable[[str], None] | None) -> None:
        self._on_project_changed = callback

    def set_active_project(self, project_path: str | Path) -> str:
        path = Path(project_path).expanduser().resolve()
        project = open_unified_project(path)
        verify_unified_project(project, verify_revision_files=True)
        self._active_project_path = str(path)
        return self._active_project_path

    def clear_active_project(self) -> None:
        self._active_project_path = None

    def capture_verified_results(
        self,
        result_package_path: str | Path,
        *,
        label: str | None = None,
        allow_duplicate_package: bool = False,
    ) -> LiveProjectCaptureReceiptV1:
        if not self._active_project_path:
            raise LiveProjectCaptureError("LIVE_PROJECT_CAPTURE_NO_ACTIVE_PROJECT")

        project_before = open_unified_project(self._active_project_path)
        verify_unified_project(project_before, verify_revision_files=True)
        project, authoring_receipt = append_verified_results_revision(
            self._active_project_path,
            result_package_path,
            label=label,
            allow_duplicate_package=allow_duplicate_package,
        )
        verify_project_authoring_receipt(authoring_receipt)
        latest = project.revisions[-1]
        if latest.source_step_sha256 != project_before.source_step_sha256:
            raise LiveProjectCaptureError("LIVE_PROJECT_CAPTURE_STEP_IDENTITY_DRIFT")

        session, package, _binding = open_verified_project_session(
            result_package_path,
            hotspot_binder=self._hotspot_binder,
            stress_binder=self._stress_binder,
            recent_store_path=self._recent_store_path,
        )
        if session.package_sha256 != latest.result_package_sha256:
            raise LiveProjectCaptureError("LIVE_PROJECT_CAPTURE_SESSION_IDENTITY_MISMATCH")
        if package.source_step_sha256 != project.source_step_sha256:
            raise LiveProjectCaptureError("LIVE_PROJECT_CAPTURE_PACKAGE_STEP_MISMATCH")

        refreshed = False
        if self._on_project_changed is not None:
            self._on_project_changed(self._active_project_path)
            refreshed = True

        core = {
            "schema": "AsterMaxLiveProjectCaptureReceiptV1",
            "status": "CAPTURED_VERIFIED",
            "project_path": self._active_project_path,
            "result_package_path": str(Path(result_package_path).expanduser().resolve()),
            "source_step_sha256": project.source_step_sha256,
            "revision": latest.revision,
            "revision_sha256": latest.revision_sha256,
            "project_sha256": project.project_sha256,
            "session_sha256": session.session_sha256,
            "native_results_bound": True,
            "project_tree_refresh_requested": refreshed,
            "solver_executed_by_capture": False,
            "gmsh_executed_by_capture": False,
            "physics_changed_by_capture": False,
            "global_analysis_converged": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
        }
        return LiveProjectCaptureReceiptV1(**core, receipt_sha256=canonical_sha256(core))


def verify_live_project_capture_receipt(receipt: LiveProjectCaptureReceiptV1) -> None:
    if receipt.schema != "AsterMaxLiveProjectCaptureReceiptV1" or receipt.status != "CAPTURED_VERIFIED":
        raise LiveProjectCaptureError("LIVE_PROJECT_CAPTURE_RECEIPT_SCHEMA")
    if receipt.solver_executed_by_capture or receipt.gmsh_executed_by_capture or receipt.physics_changed_by_capture:
        raise LiveProjectCaptureError("LIVE_PROJECT_CAPTURE_EXECUTION_OVERCLAIM")
    if receipt.global_analysis_converged or receipt.industrial_validation or receipt.ansys_equivalence:
        raise LiveProjectCaptureError("LIVE_PROJECT_CAPTURE_VALIDATION_OVERCLAIM")
    core = receipt.__dict__.copy()
    core.pop("receipt_sha256")
    if canonical_sha256(core) != receipt.receipt_sha256:
        raise LiveProjectCaptureError("LIVE_PROJECT_CAPTURE_RECEIPT_TAMPERED")
