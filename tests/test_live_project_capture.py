from dataclasses import replace
import inspect

import pytest

from astermax.fea.live_project_capture import (
    LiveProjectCaptureCoordinatorV1,
    LiveProjectCaptureError,
    verify_live_project_capture_receipt,
)
from astermax.fea.project_authoring import ProjectAuthoringError, create_project_from_verified_results
from astermax.fea.project_session_shell import install_project_session_tab
from astermax.fea.unified_project_model import open_unified_project, verify_unified_project
from test_project_session_shell import _real_package


def _coordinator(bound, refreshed, recent):
    return LiveProjectCaptureCoordinatorV1(
        hotspot_binder=lambda view: bound.append(("hotspot", view.visualization_sha256)),
        stress_binder=lambda view: bound.append(("stress", view.comparison_sha256)),
        on_project_changed=lambda path: refreshed.append(path),
        recent_store_path=recent,
    )


def test_verified_live_capture_appends_active_project_and_restores_results_without_new_solve(tmp_path, monkeypatch):
    package_path = _real_package(tmp_path)
    project_path = tmp_path / "live_capture.astermax"
    project, _receipt = create_project_from_verified_results(project_path, package_path, project_name="Live Capture Harness")
    assert len(project.revisions) == 1

    bound = []
    refreshed = []
    coordinator = _coordinator(bound, refreshed, tmp_path / "recent.json")
    coordinator.set_active_project(project_path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("live project capture must not invoke solver or gmsh")

    import astermax.fea.gmsh_bridge as gmsh_bridge
    import astermax.fea.solver as solver
    monkeypatch.setattr(gmsh_bridge, "_gmsh", forbidden)
    monkeypatch.setattr(solver, "solve_linear_static_tet10", forbidden)

    receipt = coordinator.capture_verified_results(
        package_path,
        label="Revision 02 · Harness verified capture checkpoint",
        allow_duplicate_package=True,
    )
    verify_live_project_capture_receipt(receipt)
    reopened = open_unified_project(project_path)
    verify_unified_project(reopened)

    assert receipt.status == "CAPTURED_VERIFIED"
    assert receipt.revision == 2
    assert len(reopened.revisions) == 2
    assert receipt.project_sha256 == reopened.project_sha256
    assert receipt.native_results_bound is True
    assert receipt.project_tree_refresh_requested is True
    assert receipt.solver_executed_by_capture is False
    assert receipt.gmsh_executed_by_capture is False
    assert receipt.physics_changed_by_capture is False
    assert receipt.ansys_equivalence is False
    assert [name for name, _sha in bound] == ["hotspot", "stress"]
    assert refreshed == [str(project_path.resolve())]


def test_capture_requires_active_project_and_duplicate_is_not_silent(tmp_path):
    package_path = _real_package(tmp_path)
    project_path = tmp_path / "guarded.astermax"
    create_project_from_verified_results(project_path, package_path)
    coordinator = _coordinator([], [], tmp_path / "recent.json")

    with pytest.raises(LiveProjectCaptureError, match="NO_ACTIVE_PROJECT"):
        coordinator.capture_verified_results(package_path)

    coordinator.set_active_project(project_path)
    with pytest.raises(ProjectAuthoringError, match="DUPLICATE_RESULTS_REVISION"):
        coordinator.capture_verified_results(package_path)


def test_capture_receipt_tamper_and_overclaim_fail_closed(tmp_path):
    package_path = _real_package(tmp_path)
    project_path = tmp_path / "receipt.astermax"
    create_project_from_verified_results(project_path, package_path)
    coordinator = _coordinator([], [], tmp_path / "recent.json")
    coordinator.set_active_project(project_path)
    receipt = coordinator.capture_verified_results(
        package_path,
        label="Revision 02 · Explicit duplicate checkpoint",
        allow_duplicate_package=True,
    )

    with pytest.raises(LiveProjectCaptureError, match="RECEIPT_TAMPERED"):
        verify_live_project_capture_receipt(replace(receipt, revision=99))
    with pytest.raises(LiveProjectCaptureError, match="VALIDATION_OVERCLAIM"):
        verify_live_project_capture_receipt(replace(receipt, ansys_equivalence=True))


def test_shipping_projects_shell_exposes_capture_bridge_without_breaking_return_contract():
    source = inspect.getsource(install_project_session_tab)
    assert 'setattr(notebook, "_astermax_live_project_capture", capture_coordinator)' in source
    assert "on_active_project_changed=capture_coordinator.set_active_project" in source
    assert "return open_path, refresh" in source
    assert "capture_verified_results(" not in source, "opening an old Results package must not silently append it"
