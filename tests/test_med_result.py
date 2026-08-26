from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import h5py
import numpy as np
import pytest

from astermax.solver.errors import SolverEvidenceError
from astermax.solver.med_result import read_code_aster_rmed


def _fixed(values: list[str]) -> bytes:
    return "".join(value.ljust(16) for value in values).encode()


def build_structural_med(path: Path, *, profile: str = "MED_NO_PROFILE_INTERNAL") -> tuple[np.ndarray, np.ndarray]:
    """Create a structural MED-layout fixture only; values are not FEA evidence."""
    points = np.arange(21, dtype=np.float64).reshape(7, 3) / 10.0
    displacement = np.arange(42, dtype=np.float64).reshape(7, 6) / 1000.0
    stress = (np.arange(42, dtype=np.float64).reshape(1, 7, 6) + 1.0) * 10.0
    with h5py.File(path, "w") as f:
        info = f.create_group("INFOS_GENERALES")
        info.attrs.update(MAJ=3, MIN=3, REL=0)
        meshes = f.create_group("ENS_MAA")
        mesh = meshes.create_group("MESH")
        mesh.attrs.update(DIM=3, ESP=3)
        step = mesh.create_group("STEP")
        noe = step.create_group("NOE")
        noe.attrs["PFL"] = b"MED_NO_PROFILE_INTERNAL"
        coo = noe.create_dataset("COO", data=points.T.reshape(-1))
        coo.attrs["NBR"] = 7
        mai = step.create_group("MAI")
        tr7 = mai.create_group("TR7")
        tr7.attrs["PFL"] = b"MED_NO_PROFILE_INTERNAL"
        nod = tr7.create_dataset("NOD", data=np.arange(1, 8, dtype=np.int64))
        nod.attrs["NBR"] = 1

        cha = f.create_group("CHA")
        displacement_group = cha.create_group("ELAS1___DEPL")
        displacement_group.attrs["MAI"] = b"MESH"
        displacement_group.attrs["NCO"] = 6
        displacement_group.attrs["NOM"] = _fixed(["DX", "DY", "DZ", "DRX", "DRY", "DRZ"])
        displacement_group.attrs["UNI"] = _fixed(["", "", "", "", "", ""])
        displacement_step = displacement_group.create_group("T")
        displacement_association = displacement_step.create_group("NOE")
        displacement_association.attrs["PFL"] = profile.encode()
        displacement_profile = displacement_association.create_group(profile)
        displacement_profile.attrs.update(NBR=7, NGA=1)
        displacement_profile.create_dataset("CO", data=displacement.T.reshape(-1))

        stress_group = cha.create_group("ELAS1___SIGM_ELNO")
        stress_group.attrs["MAI"] = b"MESH"
        stress_group.attrs["NCO"] = 6
        stress_group.attrs["NOM"] = _fixed(["SIXX", "SIYY", "SIZZ", "SIXY", "SIXZ", "SIYZ"])
        stress_group.attrs["UNI"] = _fixed(["", "", "", "", "", ""])
        stress_step = stress_group.create_group("T")
        stress_association = stress_step.create_group("NOE.TR7")
        stress_association.attrs["PFL"] = b"MED_NO_PROFILE_INTERNAL"
        stress_profile = stress_association.create_group("MED_NO_PROFILE_INTERNAL")
        stress_profile.attrs.update(NBR=1, NGA=7)
        stress_profile.create_dataset("CO", data=stress.transpose(2, 0, 1).reshape(-1))
    return displacement, stress


def test_reads_component_major_med_fields_without_changing_values(tmp_path: Path) -> None:
    path = tmp_path / "structural.rmed"
    expected_depl, expected_stress = build_structural_med(path)
    digest = sha256(path.read_bytes()).hexdigest()
    result = read_code_aster_rmed(path, expected_sha256=digest)
    assert result.med_version == (3, 3, 0)
    assert result.points.shape == (7, 3)
    assert result.cell_blocks[0].connectivity.tolist() == [[0, 1, 2, 3, 4, 5, 6]]
    assert np.array_equal(result.fields["ELAS1___DEPL"].values, expected_depl)
    assert np.array_equal(result.fields["ELAS1___SIGM_ELNO"].values, expected_stress)
    assert result.fields["ELAS1___SIGM_ELNO"].common_unit is None


def test_rejects_hash_mismatch_before_reading(tmp_path: Path) -> None:
    path = tmp_path / "structural.rmed"
    build_structural_med(path)
    with pytest.raises(SolverEvidenceError, match="SHA-256 mismatch"):
        read_code_aster_rmed(path, expected_sha256="0" * 64)


def test_rejects_profiled_med_field_instead_of_silently_dropping(tmp_path: Path) -> None:
    path = tmp_path / "profiled.rmed"
    build_structural_med(path, profile="CUSTOM_PROFILE")
    with pytest.raises(SolverEvidenceError, match="unsupported MED profile"):
        read_code_aster_rmed(path)
