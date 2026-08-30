from dataclasses import replace

import pytest

from astermax.fea.project_authoring import (
    ProjectAuthoringError,
    append_verified_results_revision,
    create_project_from_verified_results,
    verify_project_authoring_receipt,
)
from astermax.fea.unified_project_model import open_unified_project, verify_unified_project
from test_project_session_shell import _real_package


def test_verified_results_can_author_project_and_append_revision(tmp_path):
    package = _real_package(tmp_path)
    project_path = tmp_path / "authoring_demo.astermax"

    project, created = create_project_from_verified_results(
        project_path,
        package,
        project_name="AsterMax Authoring Demo",
    )
    verify_project_authoring_receipt(created)
    assert project.project_name == "AsterMax Authoring Demo"
    assert len(project.revisions) == 1
    assert created.action == "CREATE_PROJECT_FROM_VERIFIED_RESULTS"
    assert created.solver_executed is False
    assert created.gmsh_executed is False
    assert created.ansys_equivalence is False

    # A deliberate engineering revision may reference the same verified result
    # package with a distinct revision label. The revision identity and project
    # SHA still change, preserving append-only history rather than overwriting.
    updated, appended = append_verified_results_revision(
        project_path,
        package,
        label="Revision 02 · Engineering review checkpoint",
        allow_duplicate_package=True,
    )
    verify_project_authoring_receipt(appended)
    assert len(updated.revisions) == 2
    assert updated.revisions[0].revision_sha256 != updated.revisions[1].revision_sha256
    assert appended.revision_count == 2
    assert appended.project_sha256 != created.project_sha256
    verify_unified_project(open_unified_project(project_path), verify_revision_files=True)


def test_authoring_rejects_accidental_duplicate_and_existing_project(tmp_path):
    package = _real_package(tmp_path)
    project_path = tmp_path / "authoring_integrity.astermax"
    create_project_from_verified_results(project_path, package)

    with pytest.raises(ProjectAuthoringError, match="PROJECT_AUTHORING_PROJECT_ALREADY_EXISTS"):
        create_project_from_verified_results(project_path, package)
    with pytest.raises(ProjectAuthoringError, match="PROJECT_AUTHORING_DUPLICATE_RESULTS_REVISION"):
        append_verified_results_revision(project_path, package)


def test_authoring_receipt_truth_boundary_is_fail_closed(tmp_path):
    package = _real_package(tmp_path)
    project_path = tmp_path / "authoring_truth.astermax"
    _project, receipt = create_project_from_verified_results(project_path, package)

    with pytest.raises(ProjectAuthoringError, match="PROJECT_AUTHORING_VALIDATION_OVERCLAIM"):
        verify_project_authoring_receipt(replace(receipt, ansys_equivalence=True))
    with pytest.raises(ProjectAuthoringError, match="PROJECT_AUTHORING_RECEIPT_TAMPERED"):
        verify_project_authoring_receipt(replace(receipt, project_sha256="0" * 64))
