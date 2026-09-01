import numpy as np
import pytest
from astermax.results_scene import ResultsFieldBinding, build_results_scene, normalized_scalar, result_scene_modes, validate_results_binding


def _nodes():
    return np.array([[0.,0.,0.],[10.,0.,0.],[0.,5.,0.],[0.,0.,2.]])


def _binding():
    return ResultsFieldBinding(
        displacement_mm=np.array([[0.,0.,0.],[.1,0.,0.],[0.,.2,0.],[0.,0.,.05]]),
        von_mises_mpa=np.array([0.,25.,50.,100.]),
        workspace_sha256="workspace-abc123",
        solve_evidence_sha256="solve-def456",
    )


def test_results_scene_deformation_and_scalar_are_bound_to_real_nodes():
    nodes=_nodes(); b=_binding(); validate_results_binding(nodes,b)
    scene=build_results_scene(nodes,b,deformation_scale=2.0)
    np.testing.assert_allclose(scene.deformed_nodes_mm,nodes+b.displacement_mm*2.0)
    np.testing.assert_allclose(scene.displacement_magnitude_mm,np.linalg.norm(b.displacement_mm,axis=1))
    assert scene.scalar_min==0.0 and scene.scalar_max==100.0
    assert scene.workspace_sha256==b.workspace_sha256
    assert scene.solve_evidence_sha256==b.solve_evidence_sha256


def test_von_mises_normalization_is_deterministic_and_unitless_for_display_only():
    n=normalized_scalar(np.array([0.,25.,50.,100.]))
    np.testing.assert_allclose(n,[0.,.25,.5,1.])
    np.testing.assert_array_equal(normalized_scalar(np.array([7.,7.])),np.zeros(2))


def test_results_modes_are_hidden_until_verified_binding_exists():
    assert result_scene_modes(False)==("surface","wireframe","surface+edges")
    assert result_scene_modes(True)==("surface","wireframe","surface+edges","total_deformation","von_mises")


def test_results_scene_fails_closed_on_shape_nonfinite_negative_vm_and_missing_provenance():
    nodes=_nodes(); b=_binding()
    with pytest.raises(ValueError,match="DISPLACEMENT_SHAPE_MISMATCH"):
        validate_results_binding(nodes,ResultsFieldBinding(np.zeros((3,3)),b.von_mises_mpa,b.workspace_sha256,b.solve_evidence_sha256))
    bad_vm=b.von_mises_mpa.copy(); bad_vm[1]=np.nan
    with pytest.raises(ValueError,match="NONFINITE_FIELD"):
        validate_results_binding(nodes,ResultsFieldBinding(b.displacement_mm,bad_vm,b.workspace_sha256,b.solve_evidence_sha256))
    neg=b.von_mises_mpa.copy(); neg[2]=-1.0
    with pytest.raises(ValueError,match="VON_MISES_NEGATIVE"):
        validate_results_binding(nodes,ResultsFieldBinding(b.displacement_mm,neg,b.workspace_sha256,b.solve_evidence_sha256))
    with pytest.raises(ValueError,match="WORKSPACE_PROVENANCE_REQUIRED"):
        validate_results_binding(nodes,ResultsFieldBinding(b.displacement_mm,b.von_mises_mpa,"",b.solve_evidence_sha256))
    with pytest.raises(ValueError,match="SOLVE_PROVENANCE_REQUIRED"):
        validate_results_binding(nodes,ResultsFieldBinding(b.displacement_mm,b.von_mises_mpa,b.workspace_sha256,""))


def test_deformation_scale_rejects_negative_or_nonfinite():
    with pytest.raises(ValueError,match="DEFORMATION_SCALE_INVALID"):
        build_results_scene(_nodes(),_binding(),deformation_scale=-1)
    with pytest.raises(ValueError,match="DEFORMATION_SCALE_INVALID"):
        build_results_scene(_nodes(),_binding(),deformation_scale=float("nan"))
