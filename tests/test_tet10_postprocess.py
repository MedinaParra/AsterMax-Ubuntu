from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pytest

from astermax.fea.evidence import verify_analysis_evidence_manifest
from astermax.fea.evidence_tet10 import (
    mesh_fingerprint_tet10,
    write_tet10_analysis_evidence_manifest,
)
from astermax.fea.postprocess_tet10 import write_tet10_linear_static_vtu
from astermax.fea.solver import Tet10LinearStaticResult
from astermax.fea.viewer_tet10 import (
    build_tet10_viewer_payload,
    extract_surface_tri6,
    subdivide_tri6,
    write_tet10_offline_viewer,
)


def _single_tet10() -> tuple[np.ndarray, np.ndarray, Tet10LinearStaticResult]:
    corners = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    n0, n1, n2, n3 = corners
    nodes = np.vstack(
        [
            corners,
            0.5 * (n0 + n1),
            0.5 * (n1 + n2),
            0.5 * (n2 + n0),
            0.5 * (n0 + n3),
            0.5 * (n2 + n3),
            0.5 * (n1 + n3),
        ]
    )
    elements = np.arange(10, dtype=np.int64).reshape((1, 10))
    displacement = np.zeros_like(nodes)
    displacement[:, 0] = nodes[:, 0] * 0.01
    stress = np.zeros((1, 4, 6), dtype=float)
    stress[0, :, 0] = [10.0, 20.0, 30.0, 40.0]
    mises = np.asarray([[10.0, 20.0, 30.0, 40.0]])
    result = Tet10LinearStaticResult(
        displacement_mm=displacement,
        reactions_n=np.zeros_like(nodes),
        integration_point_stress_mpa=stress,
        integration_point_von_mises_mpa=mises,
    )
    return nodes, elements, result


def test_tet10_boundary_uses_quadratic_midside_nodes() -> None:
    _, elements, _ = _single_tet10()
    tri6, owners = extract_surface_tri6(elements)
    display, display_owner = subdivide_tri6(tri6, owners)
    assert tri6.shape == (4, 6)
    assert display.shape == (16, 3)
    assert display_owner.shape == (16,)
    assert set(display.reshape(-1)) == set(range(10))


def test_tet10_viewer_preserves_ip_stress_without_nodal_smoothing(tmp_path: Path) -> None:
    nodes, elements, result = _single_tet10()
    payload = build_tet10_viewer_payload(nodes, elements, result, converged_claim=True)
    assert payload["provenance"]["stress_representation"] == "FOUR_INTEGRATION_POINTS_PRESERVED_NO_NODAL_SMOOTHING"
    assert payload["integration_point_fields"]["VON_MISES_IP4_MPa"] == [[10.0, 20.0, 30.0, 40.0]]
    assert payload["fields"]["VON_MISES_IP_MAX_MPa"]["values"] == [40.0]
    assert "VON_MISES_NODAL" not in json.dumps(payload)

    manifest = write_tet10_offline_viewer(
        tmp_path / "viewer.html",
        nodes,
        elements,
        result,
        converged_claim=True,
    )
    assert manifest.tet10_count == 1
    assert manifest.boundary_tri6_count == 4
    assert manifest.rendered_triangle_count == 16
    assert manifest.converged_claim is True
    html = (tmp_path / "viewer.html").read_text(encoding="utf-8")
    assert "does not manufacture nodal stress" in html


def test_tet10_vtu_uses_quadratic_tetra_and_keeps_four_ip_values(tmp_path: Path) -> None:
    nodes, elements, result = _single_tet10()
    path = tmp_path / "result.vtu"
    manifest = write_tet10_linear_static_vtu(
        path,
        nodes,
        elements,
        result,
        converged_claim=True,
    )
    tree = ElementTree.parse(path)
    arrays = {item.attrib.get("Name"): item for item in tree.findall(".//DataArray")}
    assert arrays["types"].text.strip() == "24"
    assert arrays["VON_MISES_IP4_MPa"].attrib["NumberOfComponents"] == "4"
    assert arrays["STRESS_IP4_MPa"].attrib["NumberOfComponents"] == "24"
    assert arrays["VON_MISES_IP_MAX_MPa"].text.strip() == "40"
    assert arrays["ASTERMAX_STRESS_IS_NODAL"].text.strip() == "0"
    assert manifest.tet10_count == 1
    assert manifest.von_mises_ip_max_mpa == 40.0
    assert manifest.stress_representation.endswith("NO_NODAL_SMOOTHING")


def test_tet10_mesh_fingerprint_changes_with_midside_geometry() -> None:
    nodes, elements, _ = _single_tet10()
    first = mesh_fingerprint_tet10(nodes, elements)
    changed = nodes.copy()
    changed[4, 1] += 1.0e-6
    second = mesh_fingerprint_tet10(changed, elements)
    assert first != second


def test_tet10_evidence_requires_real_convergence_gate(tmp_path: Path) -> None:
    nodes, elements, result = _single_tet10()
    package = tmp_path / "pkg"
    package.mkdir()
    source = package / "source.step"
    source.write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")
    vtu = package / "result.vtu"
    viewer = package / "viewer.html"
    write_tet10_linear_static_vtu(vtu, nodes, elements, result, converged_claim=True)
    write_tet10_offline_viewer(viewer, nodes, elements, result, converged_claim=True)

    with pytest.raises(ValueError, match="converged_claim"):
        write_tet10_analysis_evidence_manifest(
            package,
            nodes_mm=nodes,
            elements=elements,
            analysis_definition={"material": "test"},
            solver_identity={"solver": "test"},
            convergence_evidence={"convergence_decision": {"converged": False}},
            artifacts=[("result.vtu", "TET10_VTU"), ("viewer.html", "TET10_VIEWER")],
            source_path=source,
            converged_claim=True,
        )

    manifest = write_tet10_analysis_evidence_manifest(
        package,
        nodes_mm=nodes,
        elements=elements,
        analysis_definition={"material": "test"},
        solver_identity={"solver": "test"},
        convergence_evidence={"convergence_decision": {"converged": True}},
        artifacts=[("result.vtu", "TET10_VTU"), ("viewer.html", "TET10_VIEWER")],
        source_path=source,
        converged_claim=True,
    )
    assert manifest.analysis_type == "LINEAR_STATIC_3D_TET10"
    verification = verify_analysis_evidence_manifest(package)
    assert verification["valid"] is True


def test_tet10_evidence_refuses_industrial_or_ansys_equivalence_claim(tmp_path: Path) -> None:
    nodes, elements, result = _single_tet10()
    package = tmp_path / "pkg"
    package.mkdir()
    source = package / "source.step"
    source.write_text("STEP", encoding="utf-8")
    artifact = package / "result.txt"
    artifact.write_text("result", encoding="utf-8")
    common = dict(
        package_dir=package,
        nodes_mm=nodes,
        elements=elements,
        analysis_definition={},
        solver_identity={},
        convergence_evidence={"convergence_decision": {"converged": True}},
        artifacts=[("result.txt", "RESULT")],
        source_path=source,
        converged_claim=True,
    )
    with pytest.raises(ValueError, match="industrial_validation_claim"):
        write_tet10_analysis_evidence_manifest(**common, industrial_validation_claim=True)
    with pytest.raises(ValueError, match="ansys_equivalence_claim"):
        write_tet10_analysis_evidence_manifest(**common, ansys_equivalence_claim=True)
