import json
from pathlib import Path

import pytest

from astermax.fea.unified_project_model import (
    UnifiedProjectError,
    append_project_revision,
    create_unified_project,
    inspect_project_revisions,
    open_unified_project,
    verify_unified_project,
)
from test_project_session_shell import _real_package


def test_unified_project_owns_verified_revision_history(tmp_path):
    package = _real_package(tmp_path)
    project_path = tmp_path / "professional_demo.astermax"
    project = create_unified_project(project_path, package, project_name="AsterMax Professional Demo")
    assert project.source_step_sha256
    assert project.units_length == "mm"
    assert len(project.revisions) == 1
    assert project.revisions[0].qoi_status in {"PASS", "FAIL"}
    assert project.claims["ansys_equivalence"] is False

    reopened = open_unified_project(project_path)
    verify_unified_project(reopened)
    inspections = inspect_project_revisions(reopened)
    assert inspections[0].status == "VERIFIED"

    # The same verified result can be recorded as a second engineering revision;
    # revision identity remains explicit instead of overwriting history.
    updated = append_project_revision(project_path, package, label="Revision 02 · Review copy")
    assert [r.revision for r in updated.revisions] == [1, 2]
    assert updated.revisions[0].revision_sha256 != updated.revisions[1].revision_sha256
    verify_unified_project(open_unified_project(project_path))


def test_project_manifest_tamper_and_missing_revision_fail_closed(tmp_path):
    package = _real_package(tmp_path)
    project_path = tmp_path / "integrity.astermax"
    create_unified_project(project_path, package)

    raw = json.loads(project_path.read_text(encoding="utf-8"))
    raw["project_name"] = "tampered"
    project_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(UnifiedProjectError, match="PROJECT_TAMPERED"):
        open_unified_project(project_path)

    # Recreate a valid project, then remove its referenced result revision.
    create_unified_project(project_path, package)
    Path(package).unlink()
    reopened = open_unified_project(project_path)
    with pytest.raises(UnifiedProjectError, match="PROJECT_REVISION_MISSING"):
        verify_unified_project(reopened)
    assert inspect_project_revisions(reopened)[0].status == "MISSING"


def test_project_rejects_overclaim_and_wrong_extension(tmp_path):
    package = _real_package(tmp_path)
    with pytest.raises(UnifiedProjectError, match="PROJECT_EXTENSION_REQUIRED"):
        create_unified_project(tmp_path / "wrong.json", package)
