from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path

import numpy as np
import pytest

from astermax.credibility import canonical_sha256
from astermax.fea.adaptive_mesh_provenance import (
    AdaptiveMeshProvenanceError,
    build_adaptive_mesh_provenance_bridge,
    verify_adaptive_mesh_provenance_bridge,
)
from astermax.fea.face_ownership import Tet10FaceOwnershipInventory
from astermax.fea.gmsh_local_refinement import GmshLocalRemeshEvidenceV1


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _remesh(path: Path, source_sha: str, mesh_sha: str) -> GmshLocalRemeshEvidenceV1:
    core = {
        "schema": "AsterMaxGmshLocalRemeshEvidenceV1",
        "plan_sha256": _sha("plan"), "approval_sha256": _sha("approval"),
        "source_step_sha256": source_sha, "route_sha256": _sha("route"),
        "baseline_mesh_sha256": _sha("baseline"), "output_mesh_sha256": mesh_sha,
        "output_path": str(path), "element_order": 2, "tetra_element_type": 11,
        "tetra_element_count": 1, "node_count": 10,
        "preserves_source_geometry": True, "preserves_bc_load_route": True,
        "qoi_convergence_claimed": False, "global_analysis_converged": False,
        "industrial_validation": False, "ansys_equivalence": False,
    }
    return GmshLocalRemeshEvidenceV1(**core, evidence_sha256=canonical_sha256(core))


def _inventory(source_sha: str) -> Tet10FaceOwnershipInventory:
    return Tet10FaceOwnershipInventory(
        schema="AsterMaxTet10FaceOwnershipInventoryV1", source_step_sha256=source_sha,
        source_size_bytes=20, nodes_mm=np.zeros((10, 3)),
        elements=np.arange(10, dtype=np.int64).reshape((1, 10)), faces=(),
        bbox_mm=(0., 0., 0., 1., 1., 1.), dimensions_mm=(1., 1., 1.),
        gmsh_version="witness", ownership_sha256=_sha("refined-inventory"),
    )


def test_bridge_requires_exact_mesh_bytes(tmp_path: Path):
    mesh = tmp_path / "approved.msh"; mesh.write_bytes(b"approved-tet10-mesh")
    mesh_sha = hashlib.sha256(mesh.read_bytes()).hexdigest(); source_sha = _sha("step")
    bridge = build_adaptive_mesh_provenance_bridge(
        local_remesh=_remesh(mesh, source_sha, mesh_sha), output_mesh_path=mesh,
        inventory=_inventory(source_sha),
    )
    verify_adaptive_mesh_provenance_bridge(bridge)
    assert bridge.exact_output_file_verified and bridge.ready_for_second_solve
    assert not bridge.global_analysis_converged and not bridge.ansys_equivalence


def test_bridge_rejects_modified_mesh_artifact(tmp_path: Path):
    mesh = tmp_path / "approved.msh"; mesh.write_bytes(b"approved")
    source_sha = _sha("step"); evidence = _remesh(mesh, source_sha, hashlib.sha256(mesh.read_bytes()).hexdigest())
    mesh.write_bytes(b"tampered")
    with pytest.raises(AdaptiveMeshProvenanceError, match="OUTPUT_SHA_MISMATCH"):
        build_adaptive_mesh_provenance_bridge(local_remesh=evidence, output_mesh_path=mesh, inventory=_inventory(source_sha))


def test_bridge_rejects_source_mismatch_and_overclaim(tmp_path: Path):
    mesh = tmp_path / "approved.msh"; mesh.write_bytes(b"approved")
    source_sha = _sha("step"); evidence = _remesh(mesh, source_sha, hashlib.sha256(mesh.read_bytes()).hexdigest())
    with pytest.raises(AdaptiveMeshProvenanceError, match="SOURCE_STEP_MISMATCH"):
        build_adaptive_mesh_provenance_bridge(local_remesh=evidence, output_mesh_path=mesh, inventory=_inventory(_sha("other-step")))
    bridge = build_adaptive_mesh_provenance_bridge(local_remesh=evidence, output_mesh_path=mesh, inventory=_inventory(source_sha))
    with pytest.raises(AdaptiveMeshProvenanceError, match="GLOBAL_CONVERGENCE_OVERCLAIM"):
        verify_adaptive_mesh_provenance_bridge(replace(bridge, global_analysis_converged=True))
