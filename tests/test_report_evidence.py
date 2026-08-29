from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from astermax.fea.report_evidence import (
    verify_report_grade_svg_evidence,
    write_report_grade_svg_evidence,
)
from astermax.fea.results_workspace import build_professional_results_workspace
from astermax.fea.solver import Tet10LinearStaticResult


def _fixture() -> tuple[np.ndarray, np.ndarray, Tet10LinearStaticResult]:
    nodes = np.asarray([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 10.0],
        [5.0, 0.0, 0.0],
        [5.0, 5.0, 0.0],
        [0.0, 5.0, 0.0],
        [0.0, 0.0, 5.0],
        [0.0, 5.0, 5.0],
        [5.0, 0.0, 5.0],
    ], dtype=float)
    elements = np.arange(10, dtype=np.int64).reshape((1, 10))
    displacement = np.zeros_like(nodes)
    displacement[:, 0] = np.linspace(0.0, 0.9, nodes.shape[0])
    stress = np.zeros((1, 4, 6), dtype=float)
    vm = np.asarray([[11.0, 22.0, 33.0, 44.0]], dtype=float)
    return nodes, elements, Tet10LinearStaticResult(displacement, np.zeros_like(nodes), stress, vm)


def _workspace(nodes, elements, result, sha: str = "a" * 64):
    return build_professional_results_workspace(
        nodes,
        elements,
        result,
        solve_evidence_sha256=sha,
        deformation_scale=10.0,
    )


def test_report_grade_svg_is_deterministic_and_provenance_bound(tmp_path: Path) -> None:
    nodes, elements, result = _fixture()
    workspace = _workspace(nodes, elements, result)
    first_path = tmp_path / "first.svg"
    second_path = tmp_path / "second.svg"
    first = write_report_grade_svg_evidence(first_path, workspace, nodes, elements, result, field="U_MAG")
    second = write_report_grade_svg_evidence(second_path, workspace, nodes, elements, result, field="U_MAG")
    verify_report_grade_svg_evidence(first_path, first)
    verify_report_grade_svg_evidence(second_path, second)
    assert first.render_view_sha256 == second.render_view_sha256
    assert first.svg_sha256 == second.svg_sha256
    assert first.workspace_sha256 == workspace.workspace_sha256
    assert first.solve_evidence_sha256 == workspace.solve_evidence_sha256
    assert first.value_min == pytest.approx(0.0)
    assert first.value_max == pytest.approx(0.9)
    text = first_path.read_text(encoding="utf-8")
    assert workspace.workspace_sha256 in text
    assert workspace.solve_evidence_sha256 in text
    assert "converged = false" in text
    assert "industrial validation = false" in text
    assert "ANSYS equivalence = false" in text


def test_report_grade_von_mises_preserves_four_ip_element_max(tmp_path: Path) -> None:
    nodes, elements, result = _fixture()
    workspace = _workspace(nodes, elements, result, "b" * 64)
    manifest = write_report_grade_svg_evidence(
        tmp_path / "vm.svg",
        workspace,
        nodes,
        elements,
        result,
        field="VON_MISES_IP_MAX",
        deformation_scale=0.0,
    )
    assert manifest.value_min == pytest.approx(44.0)
    assert manifest.value_max == pytest.approx(44.0)
    assert manifest.stress_representation == "FOUR_INTEGRATION_POINTS_PRESERVED_ELEMENT_MAX_ONLY_NO_NODAL_SMOOTHING"
    assert 'data-value="44"' in (tmp_path / "vm.svg").read_text(encoding="utf-8")


def test_report_grade_evidence_changes_when_solve_provenance_changes(tmp_path: Path) -> None:
    nodes, elements, result = _fixture()
    first = write_report_grade_svg_evidence(tmp_path / "a.svg", _workspace(nodes, elements, result, "a" * 64), nodes, elements, result)
    second = write_report_grade_svg_evidence(tmp_path / "b.svg", _workspace(nodes, elements, result, "b" * 64), nodes, elements, result)
    assert first.render_view_sha256 != second.render_view_sha256
    assert first.svg_sha256 != second.svg_sha256


def test_report_grade_evidence_fails_closed_on_tamper_and_false_claim(tmp_path: Path) -> None:
    nodes, elements, result = _fixture()
    workspace = _workspace(nodes, elements, result)
    path = tmp_path / "result.svg"
    manifest = write_report_grade_svg_evidence(path, workspace, nodes, elements, result)
    path.write_text(path.read_text(encoding="utf-8") + "<!-- tamper -->\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SVG_TAMPERED"):
        verify_report_grade_svg_evidence(path, manifest)
    with pytest.raises(ValueError, match="FALSE_CLAIM_REFUSED"):
        write_report_grade_svg_evidence(tmp_path / "bad.svg", workspace, nodes, elements, result, industrial_validation_claim=True)
    clean = write_report_grade_svg_evidence(tmp_path / "clean.svg", workspace, nodes, elements, result)
    with pytest.raises(ValueError, match="FALSE_CLAIM_REFUSED"):
        verify_report_grade_svg_evidence(tmp_path / "clean.svg", replace(clean, ansys_equivalence=True))


def test_report_grade_evidence_rejects_invalid_sha_and_small_canvas(tmp_path: Path) -> None:
    nodes, elements, result = _fixture()
    workspace = _workspace(nodes, elements, result)
    with pytest.raises(ValueError, match="CANVAS_TOO_SMALL"):
        write_report_grade_svg_evidence(tmp_path / "small.svg", workspace, nodes, elements, result, width_px=320, height_px=200)
    bad_workspace = replace(workspace, solve_evidence_sha256="not-a-sha")
    with pytest.raises(ValueError, match="SOLVE_SHA_INVALID"):
        write_report_grade_svg_evidence(tmp_path / "badsha.svg", bad_workspace, nodes, elements, result)
