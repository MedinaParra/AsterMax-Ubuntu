from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.curved_section_resultants import (
    CurvedSectionResultantError,
    curved_section_resultant_evidence,
    integrate_curved_tet10_section_resultant_slab,
)
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet10_isoparametric import duffy_tetra_gauss_rule


def _fixture():
    nodes = straight_sided_tet10_from_vertices(
        np.asarray(
            [
                [0.0, 0.0, 0.0],
                [10.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [0.0, 0.0, 2.0],
            ],
            dtype=float,
        )
    )
    elements = np.arange(10, dtype=np.int64).reshape(1, 10)
    rule = duffy_tetra_gauss_rule(4)
    stress = np.zeros((1, rule.points.shape[0], 6), dtype=float)
    stress[:, :, 0] = 5.0
    stress[:, :, 3] = 2.0
    stress[:, :, 5] = -3.0
    return nodes, elements, rule, stress


def _kwargs():
    nodes, elements, rule, stress = _fixture()
    return dict(
        nodes_mm=nodes,
        elements=elements,
        mesh_sha256="a" * 64,
        integration_point_natural_coordinates=rule.points,
        integration_point_weights=rule.weights,
        integration_point_stress_mpa=stress,
        coordinate_min_mm=0.0,
        coordinate_max_mm=10.0,
        section_area_mm2=100.0,
        section_centroid_mm=(0.0, 0.5, 0.5),
        section_normal=(2.0, 0.0, 0.0),
    )


def test_uniform_stress_recovers_force_and_zero_centroid_moment():
    result = integrate_curved_tet10_section_resultant_slab(**_kwargs())
    assert result.resultant_force_n == pytest.approx((500.0, 200.0, -300.0), rel=0.0, abs=1e-10)
    assert result.resultant_moment_nmm == pytest.approx((0.0, 0.0, 0.0), rel=0.0, abs=1e-10)
    assert result.weighted_mean_traction_mpa == pytest.approx((5.0, 2.0, -3.0), rel=0.0, abs=1e-12)
    assert result.section_normal == pytest.approx((1.0, 0.0, 0.0), rel=0.0, abs=1e-15)
    assert result.selected_integration_point_count == result.quadrature_point_count


def test_evidence_is_deterministic_and_mesh_bound():
    a = integrate_curved_tet10_section_resultant_slab(**_kwargs())
    b = integrate_curved_tet10_section_resultant_slab(**_kwargs())
    assert a.evidence_sha256 == b.evidence_sha256
    record = curved_section_resultant_evidence(a)
    assert record.payload_sha256 == a.evidence_sha256
    assert record.metadata["mesh_sha256"] == "a" * 64


def test_changed_stress_changes_resultant_and_evidence():
    kwargs = _kwargs()
    a = integrate_curved_tet10_section_resultant_slab(**kwargs)
    changed = np.asarray(kwargs["integration_point_stress_mpa"], dtype=float).copy()
    changed[:, :, 0] += 1.0
    kwargs["integration_point_stress_mpa"] = changed
    b = integrate_curved_tet10_section_resultant_slab(**kwargs)
    assert b.resultant_force_n[0] == pytest.approx(a.resultant_force_n[0] + 100.0)
    assert a.evidence_sha256 != b.evidence_sha256


def test_fail_closed_for_invalid_provenance_shapes_area_and_normal():
    kwargs = _kwargs()
    kwargs["mesh_sha256"] = "bad"
    with pytest.raises(ValueError, match="mesh_sha256"):
        integrate_curved_tet10_section_resultant_slab(**kwargs)

    kwargs = _kwargs()
    kwargs["integration_point_stress_mpa"] = kwargs["integration_point_stress_mpa"][:, :, :5]
    with pytest.raises(ValueError, match="integration_point_stress_mpa"):
        integrate_curved_tet10_section_resultant_slab(**kwargs)

    kwargs = _kwargs()
    kwargs["section_area_mm2"] = 0.0
    with pytest.raises(ValueError, match="section_area_mm2"):
        integrate_curved_tet10_section_resultant_slab(**kwargs)

    kwargs = _kwargs()
    kwargs["section_normal"] = (0.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="section_normal"):
        integrate_curved_tet10_section_resultant_slab(**kwargs)


def test_fail_closed_when_declared_slab_has_no_integration_points():
    kwargs = _kwargs()
    kwargs["coordinate_min_mm"] = 20.0
    kwargs["coordinate_max_mm"] = 21.0
    with pytest.raises(CurvedSectionResultantError, match="CONTAINS_NO_INTEGRATION_POINTS"):
        integrate_curved_tet10_section_resultant_slab(**kwargs)
