import json
import numpy as np

from astermax.fea.connected_scaling import (
    build_structured_bar,
    connected_scaling_report_json,
    run_connected_scaling,
)
from astermax.fea.tet4 import tet4_B_matrix


def test_connected_fixture_partitions_expected_volume_and_load():
    nodes, elements, loads, fixed = build_structured_bar(2, ny=2, nz=1)
    assert nodes.shape == (18, 3)
    assert elements.shape == (24, 4)
    assert fixed.size == 18
    assert np.allclose(loads.sum(axis=0), [0.0, -1000.0, 0.0])

    volume = sum(tet4_B_matrix(nodes[conn])[1] for conn in elements)
    assert np.isclose(volume, 100.0 * 20.0 * 10.0, rtol=1e-12, atol=1e-8)

    referenced = np.unique(elements)
    assert referenced.size == nodes.shape[0]


def test_connected_scaling_closes_force_and_moment():
    records = run_connected_scaling((1, 2, 4), ny=2, nz=1)
    assert [record.nx for record in records] == [1, 2, 4]
    assert [record.dofs for record in records] == sorted(record.dofs for record in records)
    assert [record.csr_nnz for record in records] == sorted(record.csr_nnz for record in records)

    for record in records:
        assert record.tet4 == 12 * record.nx
        assert record.csr_bytes > 0
        assert record.dense_equivalent_bytes > record.csr_bytes
        assert 0.0 < record.compression_ratio < 1.0
        assert np.isclose(record.volume_mm3, 20000.0, rtol=1e-12, atol=1e-7)
        assert np.isfinite(record.max_displacement_mm)
        assert record.max_displacement_mm > 0.0
        assert np.isfinite(record.max_von_mises_mpa)
        assert record.max_von_mises_mpa > 0.0
        assert record.force_residual_n < 1e-6
        assert record.moment_residual_nmm < 1e-4


def test_connected_report_is_provenance_safe():
    report = json.loads(connected_scaling_report_json((1, 2)))
    assert report["classification"] == "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT"
    assert report["claim"] == "CONNECTED_MESH_SCALABILITY_MEASUREMENT_ONLY"
    assert report["fixture"]["topology"] == "CONNECTED_STRUCTURED_TET4_BAR"
    assert report["units"]["moment"] == "N*mm"
    assert len(report["records"]) == 2


def test_connected_levels_must_be_strictly_increasing():
    for levels in ((2, 1), (2, 2), (0, 2)):
        with np.testing.assert_raises(ValueError):
            run_connected_scaling(levels)
