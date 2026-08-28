from dataclasses import replace
from math import sqrt
from pathlib import Path

import numpy as np
import pytest

from astermax.app import prepare_step_analysis
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.pre_solve_review import PreSolveReviewError, accept_model_preparation
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet_quality import (
    TetQualityError,
    build_tet10_corner_quality_snapshot,
    require_quality_crosscheck,
    tetra_mean_ratio,
    tetra_mean_ratio_cayley_menger,
)


def _regular() -> np.ndarray:
    return np.asarray([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.5, sqrt(3.0) / 2.0, 0.0],
        [0.5, sqrt(3.0) / 6.0, sqrt(2.0 / 3.0)],
    ])


def test_regular_tetra_is_one_in_both_independent_implementations() -> None:
    v = _regular()
    assert tetra_mean_ratio(v) == pytest.approx(1.0, abs=1e-14)
    assert tetra_mean_ratio_cayley_menger(v) == pytest.approx(1.0, abs=1e-14)


def test_mean_ratio_is_invariant_to_scale_rotation_translation_and_permutation() -> None:
    v = _regular()
    angle = 0.731
    r = np.asarray([[np.cos(angle), -np.sin(angle), 0.0], [np.sin(angle), np.cos(angle), 0.0], [0.0, 0.0, 1.0]])
    transformed = (v @ r.T) * 37.5 + np.asarray([11.0, -3.0, 8.0])
    transformed = transformed[[2, 0, 3, 1]]
    assert tetra_mean_ratio(transformed) == pytest.approx(1.0, abs=1e-13)
    assert tetra_mean_ratio_cayley_menger(transformed) == pytest.approx(1.0, abs=1e-13)


def test_quality_degrades_toward_zero_as_tetra_collapses() -> None:
    v = _regular()
    values = []
    for factor in (1.0, 0.1, 0.01, 0.001):
        collapsed = v.copy()
        collapsed[3, 2] *= factor
        values.append(tetra_mean_ratio(collapsed))
    assert values[0] > values[1] > values[2] > values[3] > 0.0
    flat = v.copy(); flat[3, 2] = 0.0
    assert tetra_mean_ratio(flat) == 0.0
    assert tetra_mean_ratio_cayley_menger(flat) == 0.0


def test_snapshot_crosschecks_all_tet10_corner_tetrahedra() -> None:
    tet10 = straight_sided_tet10_from_vertices(_regular())
    snapshot = build_tet10_corner_quality_snapshot(tet10, np.arange(10, dtype=np.int64)[None, :])
    assert snapshot.minimum == pytest.approx(1.0, abs=1e-14)
    assert snapshot.median == pytest.approx(1.0, abs=1e-14)
    assert snapshot.crosscheck_verified is True
    assert snapshot.crosscheck_max_abs_delta <= snapshot.crosscheck_tolerance
    assert snapshot.ansys_metric_equivalence is False
    require_quality_crosscheck(snapshot)


def test_crosscheck_and_ansys_equivalence_fail_closed() -> None:
    tet10 = straight_sided_tet10_from_vertices(_regular())
    snapshot = build_tet10_corner_quality_snapshot(tet10, np.arange(10, dtype=np.int64)[None, :])
    with pytest.raises(TetQualityError, match="CROSSCHECK"):
        require_quality_crosscheck(replace(snapshot, crosscheck_verified=False))
    with pytest.raises(TetQualityError, match="ANSYS"):
        require_quality_crosscheck(replace(snapshot, ansys_metric_equivalence=True))


def _write_box(path: Path) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c4_6_fixture")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 60.0, 20.0, 10.0)
        gmsh.model.occ.synchronize(); gmsh.write(str(path))
    finally:
        gmsh.finalize()


def test_real_step_pre_solve_review_contains_crosschecked_mean_ratio(tmp_path: Path) -> None:
    step = tmp_path / "box.step"; _write_box(step)
    prepared = prepare_step_analysis(step, mesh_size_mm=20.0, young_modulus_mpa=200000.0, poisson_ratio=0.3, resultant_n=(1000.0, 0.0, 0.0))
    review = prepared["review"]
    quality = prepared["quality"]
    assert review.schema == "AsterMaxPreSolveReviewV2"
    assert 0.0 < review.tetra_mean_ratio_minimum <= review.tetra_mean_ratio_p10 <= review.tetra_mean_ratio_median <= 1.0
    assert review.tetra_quality_sha256 == quality.snapshot_sha256
    assert review.tetra_quality_crosscheck_verified is True
    assert quality.ansys_metric_equivalence is False
    accepted = accept_model_preparation(review)
    assert accepted.state == "MODEL_PREPARATION_ACCEPTED"


def test_unverified_quality_cannot_be_accepted(tmp_path: Path) -> None:
    step = tmp_path / "box.step"; _write_box(step)
    prepared = prepare_step_analysis(step, mesh_size_mm=20.0, young_modulus_mpa=200000.0, poisson_ratio=0.3, resultant_n=(1000.0, 0.0, 0.0))
    with pytest.raises(PreSolveReviewError, match="TETRA_QUALITY"):
        accept_model_preparation(replace(prepared["review"], tetra_quality_crosscheck_verified=False))
