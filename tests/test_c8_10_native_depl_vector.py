import numpy as np
import pytest

from astermax.cae_scene_contract import CaeSceneContract, validate_cae_scene_contract
from astermax.professional_postprocess import build_professional_postprocess_view


def _scene(scale=0.0):
    nodes = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
    depl = np.array([[0.,0.,0.],[0.1,0.2,0.],[0.,0.3,0.4]])
    mag = np.linalg.norm(depl, axis=1)
    vm = np.array([1.,2.,3.])
    tri = np.array([[0,1,2]])
    return CaeSceneContract(
        undeformed_nodes_mm=nodes,
        deformed_nodes_mm=nodes + scale*depl,
        surface_triangles=tri,
        nodal_von_mises_mpa=vm,
        triangle_von_mises_mpa=np.array([2.]),
        triangle_scalar_normalized=np.array([0.5]),
        displacement_magnitude_mm=mag,
        scalar_min_mpa=1.,
        scalar_max_mpa=3.,
        deformation_scale=scale,
        length_unit='mm',
        stress_unit='MPa',
        stress_representation='CODE_ASTER_SIEQ_NOEU',
        workspace_sha256='abcdef123456',
        solve_evidence_sha256='123456abcdef',
        displacement_vector_mm=depl,
    )


def test_native_vector_survives_zero_display_scale_and_can_be_rescaled():
    scene = _scene(scale=0.0)
    validate_cae_scene_contract(scene)
    view = build_professional_postprocess_view(scene, deformation_scale=10.0)
    np.testing.assert_allclose(view.display_nodes_mm, scene.undeformed_nodes_mm + 10.0*scene.displacement_vector_mm)
    assert view.displacement_vector_source == 'NATIVE_SCENE_DEPL_NOEU'


def test_native_vector_magnitude_mismatch_fails_closed():
    scene = _scene(scale=1.0)
    bad = CaeSceneContract(**{**scene.__dict__, 'displacement_magnitude_mm': np.zeros(3)})
    with pytest.raises(ValueError, match='DISPLACEMENT_VECTOR_MAGNITUDE_MISMATCH'):
        validate_cae_scene_contract(bad)


def test_native_vector_deformed_geometry_mismatch_fails_closed():
    scene = _scene(scale=2.0)
    bad = CaeSceneContract(**{**scene.__dict__, 'deformed_nodes_mm': scene.undeformed_nodes_mm.copy()})
    with pytest.raises(ValueError, match='DEFORMED_VECTOR_INCONSISTENT'):
        validate_cae_scene_contract(bad)
