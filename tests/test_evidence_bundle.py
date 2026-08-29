from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from astermax.fea.evidence_bundle import (
    verify_professional_evidence_bundle,
    write_professional_evidence_bundle,
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


def _workspace(nodes, elements, result, solve_sha: str = "a" * 64):
    return build_professional_results_workspace(
        nodes,
        elements,
        result,
        solve_evidence_sha256=solve_sha,
        deformation_scale=10.0,
    )


def test_professional_evidence_bundle_is_deterministic_and_complete(tmp_path: Path) -> None:
    nodes, elements, result = _fixture()
    workspace = _workspace(nodes, elements, result)
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = write_professional_evidence_bundle(first_dir, workspace, nodes, elements, result)
    second = write_professional_evidence_bundle(second_dir, workspace, nodes, elements, result)
    verify_professional_evidence_bundle(first_dir, first)
    verify_professional_evidence_bundle(second_dir, second)

    assert first.manifest_sha256 == second.manifest_sha256
    assert first.index_html_sha256 == second.index_html_sha256
    assert first.displacement_svg.svg_sha256 == second.displacement_svg.svg_sha256
    assert first.von_mises_svg.svg_sha256 == second.von_mises_svg.svg_sha256
    assert first.workspace_sha256 == workspace.workspace_sha256
    assert first.solve_evidence_sha256 == workspace.solve_evidence_sha256
    assert first.displacement_svg.value_max == pytest.approx(0.9)
    assert first.von_mises_svg.value_max == pytest.approx(44.0)
    assert {p.name for p in first_dir.iterdir()} == {"displacement.svg", "von_mises.svg", "index.html", "manifest.json"}

    html = (first_dir / "index.html").read_text(encoding="utf-8")
    assert workspace.workspace_sha256 in html
    assert workspace.solve_evidence_sha256 in html
    assert "converged=false" in html
    assert "industrial_validation=false" in html
    assert "ANSYS_equivalence=false" in html
    assert "No nodal stress smoothing" in html


def test_professional_evidence_bundle_changes_with_solve_identity(tmp_path: Path) -> None:
    nodes, elements, result = _fixture()
    first = write_professional_evidence_bundle(tmp_path / "a", _workspace(nodes, elements, result, "a" * 64), nodes, elements, result)
    second = write_professional_evidence_bundle(tmp_path / "b", _workspace(nodes, elements, result, "b" * 64), nodes, elements, result)
    assert first.manifest_sha256 != second.manifest_sha256
    assert first.index_html_sha256 != second.index_html_sha256


def test_professional_evidence_bundle_detects_file_tamper(tmp_path: Path) -> None:
    nodes, elements, result = _fixture()
    output = tmp_path / "bundle"
    manifest = write_professional_evidence_bundle(output, _workspace(nodes, elements, result), nodes, elements, result)
    (output / "index.html").write_text((output / "index.html").read_text(encoding="utf-8") + "<!-- tamper -->\n", encoding="utf-8")
    with pytest.raises(ValueError, match="INDEX_TAMPERED"):
        verify_professional_evidence_bundle(output, manifest)


def test_professional_evidence_bundle_rejects_false_claim_metadata(tmp_path: Path) -> None:
    nodes, elements, result = _fixture()
    output = tmp_path / "bundle"
    manifest = write_professional_evidence_bundle(output, _workspace(nodes, elements, result), nodes, elements, result)
    with pytest.raises(ValueError, match="FALSE_CLAIM_REFUSED"):
        verify_professional_evidence_bundle(output, replace(manifest, ansys_equivalence=True))


def test_professional_evidence_bundle_detects_manifest_tamper(tmp_path: Path) -> None:
    nodes, elements, result = _fixture()
    output = tmp_path / "bundle"
    manifest = write_professional_evidence_bundle(output, _workspace(nodes, elements, result), nodes, elements, result)
    path = output / "manifest.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"converged": false', '"converged": true'), encoding="utf-8")
    with pytest.raises(ValueError, match="MANIFEST_TAMPERED"):
        verify_professional_evidence_bundle(output, manifest)
