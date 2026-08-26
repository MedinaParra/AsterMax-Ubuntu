from __future__ import annotations

import json

import numpy as np

from astermax.fea.solver import Tet10LinearStaticResult
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet10_viewer import (
    build_tet10_viewer_payload,
    extract_tet10_boundary_tri6,
    linearize_tri6_faces,
    write_tet10_offline_viewer_html,
)


def _fixture():
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [0.0, 0.0, 10.0],
        ]
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    elements = np.arange(10, dtype=int).reshape((1, 10))
    displacement = np.zeros_like(nodes)
    displacement[:, 1] = nodes[:, 0] * -1.0e-3
    stress = np.zeros((1, 4, 6), dtype=float)
    vm = np.asarray([[5.0, 10.0, 15.0, 20.0]])
    result = Tet10LinearStaticResult(
        displacement_mm=displacement,
        reactions_n=np.zeros_like(nodes),
        integration_point_stress_mpa=stress,
        integration_point_von_mises_mpa=vm,
    )
    return nodes, elements, result


def test_tet10_boundary_faces_use_midside_nodes_and_linearize_to_four_triangles_each():
    _, elements, _ = _fixture()
    faces, owners = extract_tet10_boundary_tri6(elements)
    assert faces.shape == (4, 6)
    assert owners.shape == (4,)
    triangles, tri_owners = linearize_tri6_faces(faces, owners)
    assert triangles.shape == (16, 3)
    assert tri_owners.shape == (16,)
    assert np.all(tri_owners == 0)
    # All ten TET10 nodes participate in the rendered boundary of a single tet.
    assert set(np.unique(triangles).tolist()) == set(range(10))


def test_tet10_viewer_payload_preserves_raw_ip_stress_boundary():
    nodes, elements, result = _fixture()
    payload = build_tet10_viewer_payload(nodes, elements, result, converged_claim=True)
    assert payload["counts"] == {
        "nodes": 10,
        "tet10": 1,
        "boundary_tri6": 4,
        "rendered_triangles": 16,
    }
    assert payload["provenance"]["element_family"] == "TET10_QUADRATIC"
    assert payload["provenance"]["stress_location"] == "INTEGRATION_POINT"
    assert payload["provenance"]["nodal_stress_smoothing"] is False
    assert payload["fields"]["VON_MISES_MAX_MPa"]["values"] == [20.0]
    assert payload["fields"]["IP_VON_MISES_MPa"]["values"] == [[5.0, 10.0, 15.0, 20.0]]
    assert payload["hotspot"]["integration_point_index"] == 3
    assert payload["hotspot"]["von_mises_mpa"] == 20.0
    assert payload["provenance"]["converged_claim"] is True
    assert len(payload["payload_sha256"]) == 64


def test_tet10_html_is_offline_quadratic_and_manifested(tmp_path):
    nodes, elements, result = _fixture()
    output = tmp_path / "tet10_viewer.html"
    manifest = write_tet10_offline_viewer_html(output, nodes, elements, result, converged_claim=True)
    text = output.read_text(encoding="utf-8")
    assert "AsterMax TET10 Offline Result Viewer" in text
    assert "TET10" in text
    assert "Integration point" in text
    assert "hotspot" in text.lower()
    assert "http://" not in text and "https://" not in text
    assert manifest.tet10_count == 1
    assert manifest.boundary_tri6_count == 4
    assert manifest.rendered_triangle_count == 16
    assert manifest.hotspot_von_mises_mpa == 20.0
    assert manifest.converged_claim is True
    sidecar = json.loads((tmp_path / "tet10_viewer.html.manifest.json").read_text(encoding="utf-8"))
    assert sidecar["html_sha256"] == manifest.html_sha256
    assert sidecar["payload_sha256"] == manifest.payload_sha256
