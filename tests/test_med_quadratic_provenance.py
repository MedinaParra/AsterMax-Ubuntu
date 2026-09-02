from __future__ import annotations

import numpy as np
import pytest

from astermax.med_quadratic_provenance import (
    QuadraticMedError,
    verify_quadratic_med,
    write_quadratic_med,
)


def _mesh():
    nodes = np.array([
        [0.,0.,0.], [1.,0.,0.], [0.,1.,0.], [0.,0.,1.],
        [.5,0.,0.], [.5,.5,0.], [0.,.5,0.], [0.,0.,.5], [.5,0.,.5], [0.,.5,.5],
    ])
    tet10 = np.array([[0,1,2,3,4,5,6,7,8,9]], dtype=int)
    tri6 = np.array([[0,1,2,4,5,6]], dtype=int)
    return nodes, tet10, tri6


def test_real_med_round_trip_preserves_tet10_tri6_and_provenance(tmp_path):
    nodes, tet10, tri6 = _mesh()
    med = write_quadratic_med(tmp_path / "case.med", nodes_mm=nodes, tet10=tet10, surface_tri6=tri6, surface_group="LOAD_FACE")
    comm = "DEBUT();\n# deterministic C7.8 study\nFIN();\n"
    ev = verify_quadratic_med(med, surface_group="LOAD_FACE", volume_group="SOLID", expected_tri6=1, expected_tet10=1, comm_text=comm)
    assert ev.verified is True
    assert ev.tri6_count == 1
    assert ev.tet10_count == 1
    assert len(ev.med_sha256) == 64
    assert len(ev.comm_sha256) == 64
    assert ev.fea_solve_executed is False
    assert ev.results_verified is False


def test_rejects_bad_quadratic_connectivity(tmp_path):
    nodes, tet10, tri6 = _mesh()
    tet10[0,9] = tet10[0,8]
    with pytest.raises(QuadraticMedError, match="MED_TET10_REPEATED_NODE"):
        write_quadratic_med(tmp_path / "case.med", nodes_mm=nodes, tet10=tet10, surface_tri6=tri6, surface_group="LOAD_FACE")


def test_rejects_wrong_expected_counts(tmp_path):
    nodes, tet10, tri6 = _mesh()
    med = write_quadratic_med(tmp_path / "case.med", nodes_mm=nodes, tet10=tet10, surface_tri6=tri6, surface_group="LOAD_FACE")
    with pytest.raises(QuadraticMedError, match="MED_TRI6_COUNT_MISMATCH"):
        verify_quadratic_med(med, surface_group="LOAD_FACE", volume_group="SOLID", expected_tri6=2, expected_tet10=1, comm_text="DEBUT(); FIN();")


def test_rejects_empty_comm(tmp_path):
    nodes, tet10, tri6 = _mesh()
    med = write_quadratic_med(tmp_path / "case.med", nodes_mm=nodes, tet10=tet10, surface_tri6=tri6, surface_group="LOAD_FACE")
    with pytest.raises(QuadraticMedError, match="COMM_TEXT_EMPTY"):
        verify_quadratic_med(med, surface_group="LOAD_FACE", volume_group="SOLID", expected_tri6=1, expected_tet10=1, comm_text="   ")
