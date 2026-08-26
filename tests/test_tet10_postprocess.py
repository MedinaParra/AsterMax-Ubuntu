from __future__ import annotations

import json
from xml.etree import ElementTree as ET

import numpy as np

from astermax.fea.solver import Tet10LinearStaticResult
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet10_postprocess import tet10_hotspot, write_tet10_linear_static_vtu


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
    displacement[:, 0] = nodes[:, 0] * 1.0e-3
    stress = np.zeros((1, 4, 6), dtype=float)
    stress[0, :, 0] = [10.0, 20.0, 30.0, 40.0]
    vm = np.asarray([[10.0, 20.0, 30.0, 40.0]])
    result = Tet10LinearStaticResult(
        displacement_mm=displacement,
        reactions_n=np.zeros_like(nodes),
        integration_point_stress_mpa=stress,
        integration_point_von_mises_mpa=vm,
    )
    return nodes, elements, result


def test_tet10_vtu_is_quadratic_and_keeps_integration_point_fields(tmp_path):
    nodes, elements, result = _fixture()
    output = tmp_path / "tet10.vtu"
    manifest = write_tet10_linear_static_vtu(output, nodes, elements, result, converged_claim=True)

    assert manifest.element_family == "TET10_QUADRATIC"
    assert manifest.vtk_cell_type == 24
    assert manifest.tet10_count == 1
    assert manifest.integration_points_per_element == 4
    assert manifest.stress_location == "INTEGRATION_POINT"
    assert manifest.nodal_stress_smoothing is False
    assert manifest.von_mises_max_mpa == 40.0
    assert manifest.hotspot_element_index == 0
    assert manifest.hotspot_integration_point_index == 3
    assert manifest.converged_claim is True

    root = ET.parse(output).getroot()
    arrays = {node.attrib.get("Name"): node for node in root.findall(".//DataArray")}
    assert arrays["types"].text.strip() == "24"
    assert arrays["offsets"].text.strip() == "10"
    assert arrays["IP_STRESS_MPa"].attrib["NumberOfComponents"] == "24"
    assert arrays["IP_VON_MISES_MPa"].attrib["NumberOfComponents"] == "4"
    assert arrays["VON_MISES_MAX_MPa"].text.strip() == "40"
    assert arrays["ASTERMAX_NODAL_STRESS_SMOOTHING"].text.strip() == "0"

    sidecar = json.loads((tmp_path / "tet10.vtu.manifest.json").read_text(encoding="utf-8"))
    assert sidecar["vtk_cell_type"] == 24
    assert sidecar["stress_location"] == "INTEGRATION_POINT"
    assert sidecar["nodal_stress_smoothing"] is False
    assert len(sidecar["vtu_sha256"]) == 64


def test_tet10_hotspot_reports_raw_integration_point_location():
    nodes, elements, result = _fixture()
    hotspot = tet10_hotspot(nodes, elements, result)
    assert hotspot is not None
    assert hotspot["element_index"] == 0
    assert hotspot["integration_point_index"] == 3
    assert hotspot["von_mises_mpa"] == 40.0
    assert len(hotspot["coordinates_mm"]) == 3
    assert len(hotspot["displaced_coordinates_mm"]) == 3


def test_tet10_vtu_rejects_non_finite_integration_point_fields(tmp_path):
    nodes, elements, result = _fixture()
    result.integration_point_von_mises_mpa[0, 0] = np.nan
    try:
        write_tet10_linear_static_vtu(tmp_path / "bad.vtu", nodes, elements, result)
    except ValueError as exc:
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("non-finite TET10 fields must be rejected")
