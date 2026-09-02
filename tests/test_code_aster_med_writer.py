from pathlib import Path

import h5py
import numpy as np
import pytest

from astermax.code_aster_med_writer import (
    CodeAsterMedWriterError,
    verify_code_aster_med_groups,
    write_code_aster_med,
)
from astermax.code_aster_study import LinearStaticStudy, render_linear_static_comm


def _quadratic_tet_with_two_faces():
    # Gmsh/AsterMax TET10 ordering:
    # 4:01, 5:12, 6:20, 7:03, 8:23, 9:13.
    nodes = np.array([
        [0.0, 0.0, 0.0],   # 0
        [20.0, 0.0, 0.0],  # 1
        [0.0, 10.0, 0.0],  # 2
        [0.0, 0.0, 15.0],  # 3
        [10.0, 0.0, 0.0],  # 4 01
        [10.0, 5.0, 0.0],  # 5 12
        [0.0, 5.0, 0.0],   # 6 20
        [0.0, 0.0, 7.5],   # 7 03
        [0.0, 5.0, 7.5],   # 8 23
        [10.0, 0.0, 7.5],  # 9 13
    ])
    tet10 = np.array([[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]], dtype=int)
    fixed = np.array([[0, 1, 2, 4, 5, 6]], dtype=int)
    load = np.array([[0, 1, 3, 4, 9, 7]], dtype=int)
    return nodes, tet10, fixed, load


def test_real_med_contains_named_families_and_exact_membership(tmp_path: Path):
    nodes, tet10, fixed, load = _quadratic_tet_with_two_faces()
    med = write_code_aster_med(
        tmp_path / "solver_input.med",
        nodes_mm=nodes,
        tet10=tet10,
        support_tri6=fixed,
        load_tri6=load,
    )
    ev = verify_code_aster_med_groups(
        med,
        expected_support_tri6=1,
        expected_load_tri6=1,
        expected_tet10=1,
    )
    assert ev.med_family_names_verified is True
    assert ev.support_group == "FIXED_FACE"
    assert ev.load_group == "LOAD_FACE"
    assert ev.volume_group == "SOLID"
    assert len({ev.support_family, ev.load_family, ev.volume_family}) == 3
    assert ev.support_tri6_count == 1
    assert ev.load_tri6_count == 1
    assert ev.tet10_count == 1
    assert len(ev.med_sha256) == 64
    assert ev.fea_solve_executed is False
    assert ev.results_verified is False

    # Independent file-level witness: the names must physically exist in MED's
    # FAS/ELEME family table, not only in an AsterMax sidecar or in memory.
    names = set()
    with h5py.File(med, "r") as handle:
        fas_root = handle["FAS"][next(iter(handle["FAS"].keys()))]["ELEME"]
        for family in fas_root.values():
            rows = family["GRO"]["NOM"][()]
            for row in rows:
                names.add("".join(chr(int(v)) for v in row).rstrip("\x00").strip())
    assert {"FIXED_FACE", "LOAD_FACE", "SOLID"}.issubset(names)


def test_verified_med_names_are_the_names_rendered_into_code_aster_comm(tmp_path: Path):
    nodes, tet10, fixed, load = _quadratic_tet_with_two_faces()
    med = write_code_aster_med(
        tmp_path / "solver_input.med",
        nodes_mm=nodes,
        tet10=tet10,
        support_tri6=fixed,
        load_tri6=load,
    )
    ev = verify_code_aster_med_groups(
        med,
        expected_support_tri6=1,
        expected_load_tri6=1,
        expected_tet10=1,
    )
    study = LinearStaticStudy(
        mesh_filename=med.name,
        support_group=ev.support_group,
        load_group=ev.load_group,
        young_mpa=210000.0,
        poisson=0.3,
        traction_mpa=(0.0, -5.0, 0.0),
    )
    comm = render_linear_static_comm(study)
    assert "GROUP_MA='FIXED_FACE'" in comm
    assert "GROUP_MA='LOAD_FACE'" in comm
    assert "GROUP_MA='F_2D_1'" not in comm


def test_support_load_overlap_fails_closed(tmp_path: Path):
    nodes, tet10, fixed, _ = _quadratic_tet_with_two_faces()
    with pytest.raises(CodeAsterMedWriterError, match="SUPPORT_LOAD_FACE_OVERLAP"):
        write_code_aster_med(
            tmp_path / "bad.med",
            nodes_mm=nodes,
            tet10=tet10,
            support_tri6=fixed,
            load_tri6=fixed.copy(),
        )


def test_tampered_family_name_is_detected(tmp_path: Path):
    nodes, tet10, fixed, load = _quadratic_tet_with_two_faces()
    med = write_code_aster_med(
        tmp_path / "solver_input.med",
        nodes_mm=nodes,
        tet10=tet10,
        support_tri6=fixed,
        load_tri6=load,
    )
    with h5py.File(med, "r+") as handle:
        element_families = handle["FAS"][next(iter(handle["FAS"].keys()))]["ELEME"]
        target = next(
            family for family in element_families.values()
            if int(family.attrs["NUM"]) == -2
        )
        replacement = "WRONG_FACE" + "\x00" * (80 - len("WRONG_FACE"))
        target["GRO"]["NOM"][0] = np.array([ord(v) for v in replacement], dtype=np.int8)
    with pytest.raises(CodeAsterMedWriterError, match="CODE_ASTER_MED_GROUP_MISSING:LOAD_FACE"):
        verify_code_aster_med_groups(
            med,
            expected_support_tri6=1,
            expected_load_tri6=1,
            expected_tet10=1,
        )
