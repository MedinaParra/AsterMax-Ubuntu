import json

import numpy as np

from astermax.fea.evidence import (
    canonical_sha256,
    mesh_fingerprint,
    verify_analysis_evidence_manifest,
    write_analysis_evidence_manifest,
)


def _mesh():
    nodes = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    elements = np.array([[0, 1, 2, 3]], dtype=int)
    return nodes, elements


def test_mesh_fingerprint_is_deterministic_and_geometry_sensitive():
    nodes, elements = _mesh()
    first = mesh_fingerprint(nodes, elements)
    second = mesh_fingerprint(nodes.copy(), elements.copy())
    assert first == second
    changed = nodes.copy()
    changed[1, 0] += 1e-6
    assert mesh_fingerprint(changed, elements) != first


def test_canonical_hash_ignores_dict_insertion_order():
    assert canonical_sha256({"a": 1, "b": [2, 3]}) == canonical_sha256({"b": [2, 3], "a": 1})


def test_evidence_manifest_verifies_and_detects_artifact_tamper(tmp_path):
    nodes, elements = _mesh()
    package = tmp_path / "package"
    package.mkdir()
    result = package / "result.vtu"
    viewer = package / "viewer.html"
    result.write_text("VTU fixture\n", encoding="utf-8")
    viewer.write_text("<html>fixture</html>\n", encoding="utf-8")

    manifest = write_analysis_evidence_manifest(
        package,
        nodes_mm=nodes,
        elements=elements,
        analysis_definition={
            "material": {"E_MPa": 210000.0, "nu": 0.3},
            "constraint": "X_MIN_FIXED",
            "load": {"surface": "X_MAX", "Fy_N": -1000.0},
        },
        solver_identity={"name": "AsterMax PMV", "solver": "SciPy spsolve", "kernel": "TET4"},
        artifacts=[("result.vtu", "FEA_RESULT_VTU"), ("viewer.html", "OFFLINE_RESULT_VIEWER")],
    )
    assert manifest.classification == "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT"
    assert manifest.claims == {"converged": False, "industrial_validation": False}
    assert len(manifest.chain_sha256) == 64

    status = verify_analysis_evidence_manifest(package)
    assert status["valid"] is True
    assert status["chain_ok"] is True
    assert status["artifacts_ok"] is True

    viewer.write_text("<html>tampered</html>\n", encoding="utf-8")
    status = verify_analysis_evidence_manifest(package)
    assert status["valid"] is False
    assert status["chain_ok"] is True
    assert status["artifacts_ok"] is False
    assert "sha256:viewer.html" in status["artifact_errors"]


def test_manifest_chain_detects_metadata_tamper(tmp_path):
    nodes, elements = _mesh()
    package = tmp_path / "package"
    package.mkdir()
    artifact = package / "result.vtu"
    artifact.write_text("fixture\n", encoding="utf-8")
    write_analysis_evidence_manifest(
        package,
        nodes_mm=nodes,
        elements=elements,
        analysis_definition={"load_N": 1000.0},
        solver_identity={"name": "AsterMax PMV"},
        artifacts=[("result.vtu", "FEA_RESULT_VTU")],
    )
    manifest_path = package / "analysis_evidence.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["analysis_definition"]["canonical"]["load_N"] = 2000.0
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = verify_analysis_evidence_manifest(package)
    assert status["valid"] is False
    assert status["chain_ok"] is False
