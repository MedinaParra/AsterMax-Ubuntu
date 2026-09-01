from types import SimpleNamespace

import numpy as np
import pytest

from astermax.persistent_viewport import (
    ViewportSnapshot,
    projected_box_segments,
    snapshot_from_inventory,
    snapshot_with_assignment,
    snapshot_with_results,
    stage_caption,
    validate_snapshot,
)


def _inventory():
    return SimpleNamespace(
        nodes_mm=np.array([[0.0, 0.0, 0.0], [100.0, 20.0, 10.0], [50.0, 5.0, 8.0]]),
        elements=np.zeros((2, 10), dtype=int),
    )


def test_inventory_snapshot_is_real_mm_tet10_evidence():
    snap = snapshot_from_inventory(_inventory())
    assert snap.stage == "MESH_READY"
    assert snap.units == ("mm", "N", "MPa")
    assert snap.bbox_min_mm == (0.0, 0.0, 0.0)
    assert snap.bbox_max_mm == (100.0, 20.0, 10.0)
    assert snap.node_count == 3
    assert snap.element_count == 2
    validate_snapshot(snap)
    assert len(projected_box_segments(snap)) == 12
    assert "100.000 × 20.000 × 10.000 mm" in stage_caption(snap)


def test_assignment_and_results_keep_geometry_and_require_provenance():
    base = snapshot_from_inventory(_inventory())
    assignment = SimpleNamespace(
        support_selection=SimpleNamespace(face_ids=("face-1",)),
        load_selection=SimpleNamespace(face_ids=("face-7", "face-8")),
    )
    bc = snapshot_with_assignment(base, assignment)
    assert bc.stage == "BOUNDARY_CONDITIONS_READY"
    assert bc.bbox_max_mm == base.bbox_max_mm
    assert bc.support_face_ids == ("face-1",)
    assert bc.load_face_ids == ("face-7", "face-8")
    validate_snapshot(bc)

    summary = {
        "production_results": {"workspace_sha256": "abc123"},
        "solve_evidence": {"solve_evidence_sha256": "def456"},
    }
    solved = snapshot_with_results(bc, summary)
    assert solved.stage == "RESULTS_READY"
    assert solved.workspace_sha256 == "abc123"
    assert solved.solve_evidence_sha256 == "def456"
    validate_snapshot(solved)
    assert stage_caption(solved).endswith("results provenance verified")


def test_viewport_fails_closed_on_fake_results_or_units():
    with pytest.raises(ValueError, match="VIEWPORT_UNIT_CONTRACT_CHANGED"):
        validate_snapshot(ViewportSnapshot(stage="EMPTY", units=("m", "N", "Pa")))

    fake = ViewportSnapshot(
        stage="RESULTS_READY",
        units=("mm", "N", "MPa"),
        bbox_min_mm=(0.0, 0.0, 0.0),
        bbox_max_mm=(1.0, 1.0, 1.0),
        node_count=4,
        element_count=1,
    )
    with pytest.raises(ValueError, match="VIEWPORT_RESULTS_PROVENANCE_REQUIRED"):
        validate_snapshot(fake)


def test_viewport_rejects_empty_mesh_evidence():
    inv = SimpleNamespace(nodes_mm=np.zeros((0, 3)), elements=np.zeros((0, 10), dtype=int))
    with pytest.raises(ValueError, match="VIEWPORT_EMPTY_INVENTORY"):
        snapshot_from_inventory(inv)
