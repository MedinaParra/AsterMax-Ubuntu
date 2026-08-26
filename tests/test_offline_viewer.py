import json
import numpy as np

from astermax.fea.connected_scaling import build_structured_bar
from astermax.fea.solver import solve_linear_static
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.viewer import build_viewer_payload, extract_surface_triangles, write_offline_viewer_html


def solved_bar():
    nodes, elements, loads, fixed = build_structured_bar(1, ny=1, nz=1)
    result = solve_linear_static(nodes, elements, IsotropicMaterial(210000.0, 0.3), loads, fixed)
    return nodes, elements, result


def test_surface_extraction():
    faces, owners = extract_surface_triangles(np.array([[0, 1, 2, 3]], dtype=int))
    assert faces.shape == (4, 3)
    assert np.all(owners == 0)
    _, elements, _, _ = build_structured_bar(1, ny=1, nz=1)
    faces, owners = extract_surface_triangles(elements)
    assert elements.shape == (6, 4)
    assert faces.shape == (12, 3)
    assert owners.shape == (12,)


def test_payload_keeps_evidence_boundary():
    nodes, elements, result = solved_bar()
    payload = build_viewer_payload(nodes, elements, result)
    assert payload["counts"]["surface_triangles"] == 12
    assert payload["fields"]["U_MAG_mm"]["location"] == "POINT"
    assert payload["fields"]["VON_MISES_MPa"]["location"] == "CELL"
    assert payload["provenance"]["converged_claim"] is False
    assert payload["provenance"]["industrial_validation_claim"] is False
    assert len(payload["payload_sha256"]) == 64


def test_html_is_offline_and_manifested(tmp_path):
    nodes, elements, result = solved_bar()
    output = tmp_path / "astermax_viewer.html"
    manifest = write_offline_viewer_html(output, nodes, elements, result)
    text = output.read_text(encoding="utf-8")
    assert "AsterMax Offline Result Viewer" in text
    assert "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT" in text
    assert "http://" not in text and "https://" not in text
    assert "Display deformation scale is visual only" in text
    assert manifest.converged_claim is False
    assert manifest.industrial_validation_claim is False
    sidecar = json.loads((tmp_path / "astermax_viewer.html.manifest.json").read_text(encoding="utf-8"))
    assert sidecar["html_sha256"] == manifest.html_sha256
    assert sidecar["payload_sha256"] == manifest.payload_sha256
