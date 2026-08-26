import json
import numpy as np

from astermax.fea.scaling import (
    build_independent_tetra_pack,
    run_sparse_scaling,
    scaling_report_json,
)


def test_scaling_fixture_shape_and_load_balance():
    nodes, elements, loads, fixed = build_independent_tetra_pack(3)
    assert nodes.shape == (12, 3)
    assert elements.shape == (3, 4)
    assert loads.shape == (12, 3)
    assert fixed.size == 27
    assert np.allclose(loads.sum(axis=0), [3000.0, 0.0, 0.0])


def test_sparse_scaling_records_measured_memory_and_equilibrium():
    records = run_sparse_scaling((2, 4, 8))
    assert [r.cells for r in records] == [2, 4, 8]
    assert [r.dofs for r in records] == sorted(r.dofs for r in records)
    assert [r.csr_nnz for r in records] == sorted(r.csr_nnz for r in records)

    for record in records:
        assert record.csr_bytes > 0
        assert record.dense_equivalent_bytes > record.csr_bytes
        assert 0.0 < record.compression_ratio < 1.0
        assert record.assembly_seconds >= 0.0
        assert record.solve_seconds >= 0.0
        assert np.isfinite(record.max_displacement_mm)
        assert record.max_displacement_mm > 0.0
        assert record.force_residual_n < 1e-7 * record.cells


def test_scaling_report_never_claims_industrial_validation():
    report = json.loads(scaling_report_json((2, 4)))
    assert report["classification"] == "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT"
    assert report["claim"] == "SCALABILITY_MEASUREMENT_ONLY"
    assert report["units"]["length"] == "mm"
    assert len(report["records"]) == 2


def test_scaling_levels_must_be_strictly_increasing():
    for levels in ((4, 2), (2, 2), (0, 2)):
        with np.testing.assert_raises(ValueError):
            run_sparse_scaling(levels)
