from dataclasses import replace
from pathlib import Path

import pytest

from astermax.app import prepare_step_analysis, solve_prepared_analysis
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.pre_solve_review import (
    PreSolveReviewError,
    accept_model_preparation,
    verify_acceptance,
)


def _write_box(path: Path, *, dx: float = 60.0, dy: float = 20.0, dz: float = 10.0) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c4_5_fixture")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, dx, dy, dz)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _prepare(tmp_path: Path):
    step = tmp_path / "box.step"
    _write_box(step)
    prepared = prepare_step_analysis(
        step,
        mesh_size_mm=20.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(1000.0, 0.0, 0.0),
    )
    return step, prepared


def test_prepare_phase_creates_review_without_solving(tmp_path: Path) -> None:
    _, prepared = _prepare(tmp_path)
    review = prepared["review"]
    assert review.state == "REVIEW_REQUIRED"
    assert review.node_count > 0 and review.tet10_count > 0
    assert review.minimum_det_jacobian_mm3 > 0.0
    assert 0.0 < review.edge_ratio_minimum <= 1.0
    assert review.constraint_selection_sha256 != review.load_selection_sha256
    assert review.converged is False
    assert review.industrial_validation is False
    assert review.ansys_equivalence is False
    assert not (tmp_path / "astermax_result.vtu").exists()


def test_acceptance_is_deterministic_and_bound_to_exact_review(tmp_path: Path) -> None:
    _, prepared = _prepare(tmp_path)
    first = accept_model_preparation(prepared["review"])
    second = accept_model_preparation(prepared["review"])
    assert first.state == "MODEL_PREPARATION_ACCEPTED"
    assert first.acceptance_sha256 == second.acceptance_sha256
    verify_acceptance(prepared, first)


def test_stale_or_tampered_acceptance_fails_closed(tmp_path: Path) -> None:
    _, prepared = _prepare(tmp_path)
    accepted = accept_model_preparation(prepared["review"])
    stale = replace(accepted, review_sha256="0" * 64)
    with pytest.raises(PreSolveReviewError, match="STALE"):
        verify_acceptance(prepared, stale)
    tampered = replace(accepted, acceptance_sha256="f" * 64)
    with pytest.raises(PreSolveReviewError, match="TAMPERED"):
        verify_acceptance(prepared, tampered)


def test_step_change_after_review_blocks_solve(tmp_path: Path) -> None:
    step, prepared = _prepare(tmp_path)
    accepted = accept_model_preparation(prepared["review"])
    step.write_text(step.read_text(encoding="utf-8", errors="ignore") + "\n/* changed after review */\n", encoding="utf-8")
    with pytest.raises(PreSolveReviewError, match="STEP_CHANGED_AFTER"):
        verify_acceptance(prepared, accepted)


def test_illegal_claim_cannot_be_accepted(tmp_path: Path) -> None:
    _, prepared = _prepare(tmp_path)
    illegal = replace(prepared["review"], ansys_equivalence=True)
    with pytest.raises(PreSolveReviewError, match="ILLEGAL_CLAIM"):
        accept_model_preparation(illegal)


def test_accepted_preparation_solves_and_records_review_chain(tmp_path: Path) -> None:
    _, prepared = _prepare(tmp_path)
    accepted = accept_model_preparation(prepared["review"])
    summary = solve_prepared_analysis(prepared, accepted, tmp_path / "result")
    assert summary["pre_solve_review"]["state"] == "MODEL_PREPARATION_ACCEPTED"
    assert summary["pre_solve_review"]["review_sha256"] == prepared["review"].review_sha256
    assert summary["pre_solve_review"]["acceptance_sha256"] == accepted.acceptance_sha256
    assert summary["claims"] == {"converged": False, "industrial_validation": False, "ansys_equivalence": False}
    assert Path(summary["artifacts"]["vtu"]).is_file()
    assert Path(summary["artifacts"]["viewer"]).is_file()
