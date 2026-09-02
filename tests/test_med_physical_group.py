from pathlib import Path

import numpy as np
import pytest

from astermax.med_physical_group import (
    MedPhysicalGroupError,
    verify_med_surface_group,
    write_med_with_surface_group,
)


def tetra_mesh():
    nodes = np.array([
        [0.0, 0.0, 0.0],
        [20.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 15.0],
    ])
    tetra4 = np.array([[0, 1, 2, 3]], dtype=int)
    load_face = np.array([[0, 1, 2]], dtype=int)
    return nodes, tetra4, load_face


def test_real_med_round_trip_preserves_named_surface_group(tmp_path: Path):
    nodes, tetra4, face = tetra_mesh()
    med = write_med_with_surface_group(
        tmp_path / "model.med",
        nodes_mm=nodes,
        tetra4=tetra4,
        surface_tri3=face,
        surface_group="LOAD_FACE_12",
    )
    evidence = verify_med_surface_group(
        med,
        expected_group="LOAD_FACE_12",
        expected_element_count=1,
    )
    assert med.stat().st_size > 0
    assert evidence.verified is True
    assert evidence.dimension == 2
    assert evidence.entity_count == 1
    assert evidence.element_count == 1
    assert len(evidence.med_sha256) == 64
    assert evidence.fea_solve_executed is False
    assert evidence.results_verified is False


def test_wrong_expected_group_fails_closed(tmp_path: Path):
    nodes, tetra4, face = tetra_mesh()
    med = write_med_with_surface_group(
        tmp_path / "model.med",
        nodes_mm=nodes,
        tetra4=tetra4,
        surface_tri3=face,
        surface_group="LOAD_FACE_12",
    )
    with pytest.raises(MedPhysicalGroupError, match="MED_SURFACE_GROUP_NOT_UNIQUE"):
        verify_med_surface_group(med, expected_group="LOAD_FACE_13", expected_element_count=1)


def test_wrong_element_count_fails_closed(tmp_path: Path):
    nodes, tetra4, face = tetra_mesh()
    med = write_med_with_surface_group(
        tmp_path / "model.med",
        nodes_mm=nodes,
        tetra4=tetra4,
        surface_tri3=face,
        surface_group="LOAD_FACE_12",
    )
    with pytest.raises(MedPhysicalGroupError, match="MED_SURFACE_GROUP_ELEMENT_COUNT_MISMATCH"):
        verify_med_surface_group(med, expected_group="LOAD_FACE_12", expected_element_count=2)


def test_invalid_code_aster_group_name_is_rejected(tmp_path: Path):
    nodes, tetra4, face = tetra_mesh()
    with pytest.raises(MedPhysicalGroupError, match="MED_GROUP_NAME_INVALID"):
        write_med_with_surface_group(
            tmp_path / "model.med",
            nodes_mm=nodes,
            tetra4=tetra4,
            surface_tri3=face,
            surface_group="LOAD FACE WITH SPACES",
        )


def test_duplicate_surface_triangle_is_rejected(tmp_path: Path):
    nodes, tetra4, face = tetra_mesh()
    duplicate = np.vstack([face, face])
    with pytest.raises(MedPhysicalGroupError, match="MED_TRI3_DUPLICATE"):
        write_med_with_surface_group(
            tmp_path / "model.med",
            nodes_mm=nodes,
            tetra4=tetra4,
            surface_tri3=duplicate,
            surface_group="LOAD_FACE_12",
        )
