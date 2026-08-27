from pathlib import Path

import numpy as np

from astermax.fea.quality_policy import TetraQualityPolicy
from astermax.mesh_inspector import build_mesh_inspector_payload, write_mesh_inspector


def test_mesh_inspector_regular_tet_is_pass(tmp_path: Path):
    nodes = np.array([[0., 0., 0.], [1., 0., 0.], [0.5, 0.866025403784, 0.], [0.5, 0.288675134595, 0.816496580928]])
    elements = np.array([[0, 1, 2, 3]], dtype=int)
    p = build_mesh_inspector_payload(nodes, elements)
    assert p['schema'] == 'AsterMaxMeshInspectorV3'
    assert p['element_family'] == 'TET4'
    assert p['gate_report']['status'] == 'PASS'
    assert p['elements'][0]['status'] == 'PASS'
    assert p['worst_element_index'] == 0
    assert p['claims']['acceptance_driven_by_inspector_ranking'] is False
    assert p['claims']['status_derived_from_shared_classifier'] is True
    assert p['claims']['policy_is_single_source_of_truth'] is True
    assert p['policy'] == p['gate_report']['policy']
    assert p['corner_elements'] == [[0, 1, 2, 3]]
    assert len(p['element_centroids_mm']) == 1
    assert len(p['surface_triangles']) == 4
    assert set(p['surface_owner']) == {0}
    out = tmp_path / 'mesh.html'
    manifest = write_mesh_inspector(out, nodes, elements)
    text = out.read_text(encoding='utf-8')
    assert out.is_file() and 'Mesh Inspector V3' in text
    assert 'same serialized TetraQualityPolicy' in text
    assert 'Section position' in text and 'Show worst N tetrahedra' in text
    assert len(manifest['html_sha256']) == 64


def test_mesh_inspector_inverted_tet_is_fail():
    nodes = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
    elements = np.array([[0, 2, 1, 3]], dtype=int)
    p = build_mesh_inspector_payload(nodes, elements)
    assert p['gate_report']['status'] == 'FAIL'
    assert p['gate_report']['inverted_elements'] == 1
    assert p['elements'][0]['status'] == 'FAIL'
    assert p['elements'][0]['severity'] >= 1.0


def test_mesh_inspector_policy_drift_control_changes_gate_and_element_status_together():
    nodes = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 0.35]])
    elements = np.array([[0, 1, 2, 3]], dtype=int)
    default = build_mesh_inspector_payload(nodes, elements)
    strict = TetraQualityPolicy(
        warn_scaled_jacobian=0.90,
        fail_scaled_jacobian=0.80,
        warn_mean_ratio=0.90,
        fail_mean_ratio=0.80,
        warn_edge_aspect_ratio=1.2,
        fail_edge_aspect_ratio=1.5,
    )
    changed = build_mesh_inspector_payload(nodes, elements, policy=strict)
    assert default['gate_report']['status'] == default['elements'][0]['status']
    assert changed['gate_report']['status'] == changed['elements'][0]['status']
    assert changed['policy'] == strict.to_dict()
    assert changed['gate_report']['policy'] == strict.to_dict()
    assert changed['elements'][0]['status'] == 'FAIL'
    assert changed['elements'][0]['severity'] >= 1.0


def test_mesh_inspector_tet10_uses_volume_owner_for_surface_coloring():
    nodes = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.], [.5, 0, 0], [.5, .5, 0], [0, .5, 0], [0, 0, .5], [0, .5, .5], [.5, 0, .5]])
    elements = np.array([[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]], dtype=int)
    p = build_mesh_inspector_payload(nodes, elements)
    assert p['element_family'] == 'TET10'
    assert len(p['surface_triangles']) == 16
    assert set(p['surface_owner']) == {0}
    assert p['corner_elements'] == [[0, 1, 2, 3]]
    assert p['gate_report']['element_count'] == 1


def test_mesh_inspector_tet4_removes_shared_internal_face():
    nodes = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.], [0., 0., -1.]])
    elements = np.array([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=int)
    p = build_mesh_inspector_payload(nodes, elements)
    assert len(p['surface_triangles']) == 6
    assert set(p['surface_owner']) == {0, 1}
    assert len(p['element_centroids_mm']) == 2
