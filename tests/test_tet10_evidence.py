from __future__ import annotations

import json

import numpy as np

from astermax.fea.evidence import verify_analysis_evidence_manifest
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet10_evidence import tet10_mesh_fingerprint, write_tet10_analysis_evidence_manifest


def _mesh():
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
    return nodes, elements


def test_tet10_mesh_fingerprint_is_deterministic_and_element_specific():
    nodes, elements = _mesh()
    first = tet10_mesh_fingerprint(nodes, elements)
    second = tet10_mesh_fingerprint(nodes.copy(), elements.copy())
    assert first == second
    assert len(first) == 64
    try:
        tet10_mesh_fingerprint(nodes[:4], np.asarray([[0, 1, 2, 3]]))
    except ValueError as exc:
        assert "TET10" in str(exc)
    else:
        raise AssertionError("TET4 connectivity must not enter a TET10 evidence chain")


def test_tet10_manifest_verifies_with_generic_chain_verifier(tmp_path):
    nodes, elements = _mesh()
    source = tmp_path / "source.step"
    source.write_text("deterministic-step-fixture", encoding="utf-8")
    result = tmp_path / "result.vtu"
    result.write_text("quadratic-vtu-fixture", encoding="utf-8")
    viewer = tmp_path / "viewer.html"
    viewer.write_text("quadratic-viewer-fixture", encoding="utf-8")

    analysis_definition = {
        "mesh": {"element": "TET10_QUADRATIC", "gmsh_element_type": 11},
        "stress": {"location": "INTEGRATION_POINT", "nodal_smoothing": False},
    }
    solver_identity = {"analysis": "LINEAR_STATIC_3D_TET10", "solver": "unit-test"}
    manifest = write_tet10_analysis_evidence_manifest(
        tmp_path,
        nodes_mm=nodes,
        elements=elements,
        analysis_definition=analysis_definition,
        solver_identity=solver_identity,
        artifacts=[("result.vtu", "TET10_FEA_RESULT_VTU"), ("viewer.html", "TET10_OFFLINE_RESULT_VIEWER")],
        source_path=source,
        source_kind="STEP_CAD_VERIFICATION_FIXTURE",
        converged_claim=True,
        industrial_validation_claim=False,
    )

    assert manifest.analysis_type == "LINEAR_STATIC_3D_TET10"
    assert manifest.mesh["tet10"] == 1
    assert manifest.mesh["gmsh_element_type"] == 11
    assert manifest.mesh["vtk_cell_type"] == 24
    assert manifest.claims == {"converged": True, "industrial_validation": False}
    verification = verify_analysis_evidence_manifest(tmp_path)
    assert verification["valid"] is True
    assert verification["chain_sha256"] == manifest.chain_sha256

    payload = json.loads((tmp_path / "analysis_evidence.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "AsterMaxTet10AnalysisEvidenceV1"
    assert payload["analysis_type"] == "LINEAR_STATIC_3D_TET10"
    assert payload["analysis_definition"]["canonical"]["stress"]["nodal_smoothing"] is False
