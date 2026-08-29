import numpy as np
import pytest

from astermax.fea.surface_axial_qoi import measure_fillet_surface_axial_stress
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


MATERIAL = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)


def _fixture():
    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, 0.0, 4.0]],
        dtype=float,
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    elements = np.arange(10, dtype=np.int64).reshape(1, 10)
    tri6 = np.asarray([[0, 1, 2, 4, 5, 6]], dtype=np.int64)
    eps = 2.5e-4
    disp = np.zeros_like(nodes)
    disp[:, 0] = eps * nodes[:, 0]
    disp[:, 1] = -MATERIAL.poisson_ratio * eps * nodes[:, 1]
    disp[:, 2] = -MATERIAL.poisson_ratio * eps * nodes[:, 2]
    return nodes, elements, tri6, disp


def test_frozen_surface_qoi_has_four_direct_samples_and_no_continuous_peak_claim():
    nodes, elements, tri6, disp = _fixture()
    measurement, samples = measure_fillet_surface_axial_stress(
        measurement_id="TEST_SURFACE_QOI",
        nodes_mm=nodes,
        elements=elements,
        displacement_mm=disp,
        material=MATERIAL,
        transition_tri6=tri6,
        mesh_sha256="1" * 64,
        transition_selection_sha256="2" * 64,
    )
    assert measurement.tri6_face_count == 1
    assert measurement.sample_points_per_face == 4
    assert measurement.sample_count == 4
    assert len(samples) == 4
    assert measurement.qoi_id == "SURFACE_SAMPLED_MAX_AXIAL_NORMAL_STRESS_MPA"
    assert measurement.minimum_axial_normal_stress_mpa == pytest.approx(50.0, abs=1e-9)
    assert measurement.mean_axial_normal_stress_mpa == pytest.approx(50.0, abs=1e-9)
    assert measurement.maximum_axial_normal_stress_mpa == pytest.approx(50.0, abs=1e-9)
    assert measurement.no_nodal_stress_recovery is True
    assert measurement.no_stress_smoothing is True
    assert measurement.no_integration_point_stress_extrapolation is True
    assert measurement.continuous_surface_peak_claim is False


def test_empty_surface_is_rejected():
    nodes, elements, _, disp = _fixture()
    with pytest.raises(ValueError, match="invalid TET10 or TRI6 arrays"):
        measure_fillet_surface_axial_stress(
            measurement_id="EMPTY",
            nodes_mm=nodes,
            elements=elements,
            displacement_mm=disp,
            material=MATERIAL,
            transition_tri6=np.empty((0, 6), dtype=np.int64),
            mesh_sha256="1" * 64,
            transition_selection_sha256="2" * 64,
        )
