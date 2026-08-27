import numpy as np

from astermax.fea.mesh_quality import classify_tetra_metrics, tetra_element_metrics, tetra_mesh_quality
from astermax.fea.quality_policy import DEFAULT_TETRA_QUALITY_POLICY, TetraQualityPolicy
from astermax.mesh_inspector import build_mesh_inspector_payload


def _regular_tet():
    return np.array([[0.,0.,0.],[1.,0.,0.],[0.5,np.sqrt(3)/2,0.],[0.5,np.sqrt(3)/6,np.sqrt(2/3)]])


def test_default_policy_is_serialized_into_gate_evidence():
    report = tetra_mesh_quality(_regular_tet(), np.array([[0,1,2,3]]))
    assert report.policy == DEFAULT_TETRA_QUALITY_POLICY.to_dict()
    assert report.status == "PASS"


def test_custom_policy_changes_classification_without_changing_metric_kernel():
    nodes = _regular_tet()
    elements = np.array([[0,1,2,3]])
    metrics = tetra_element_metrics(nodes, elements)
    strict = TetraQualityPolicy(
        warn_scaled_jacobian=0.95, fail_scaled_jacobian=0.90,
        warn_mean_ratio=0.99, fail_mean_ratio=0.98,
        warn_edge_aspect_ratio=1.01, fail_edge_aspect_ratio=1.02,
    )
    status, _, _ = classify_tetra_metrics(metrics, strict)
    assert status.tolist() == ["FAIL"]
    assert tetra_mesh_quality(nodes, elements, policy=strict).status == "FAIL"


def test_inspector_and_acceptance_gate_agree_on_control_set():
    fixtures = [
        (_regular_tet(), np.array([[0,1,2,3]])),
        (np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]), np.array([[0,2,1,3]])),
        (np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[1e-6,1e-6,1e-8]]), np.array([[0,1,2,3]])),
    ]
    for nodes, elements in fixtures:
        gate = tetra_mesh_quality(nodes, elements)
        inspector = build_mesh_inspector_payload(nodes, elements)
        assert inspector["gate_report"]["status"] == gate.status
        assert inspector["elements"][0]["status"] == gate.status
