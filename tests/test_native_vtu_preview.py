from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from astermax.native_vtu_preview import (
    assert_native_preview_claim_boundary,
    load_native_vtu_preview,
    projected_preview_geometry,
    sha256_file,
)


def _write_fixture(path: Path, *, converged: int = 0, industrial: int = 0, stress_is_nodal: int = 0) -> str:
    points = "0 0 0  1 0 0  0 1 0  0 0 1  0.5 0 0  0.5 0.5 0  0 0.5 0  0 0 0.5  0.5 0 0.5  0 0.5 0.5"
    disp = "0 0 0  0.1 0 0  0 0.2 0  0 0 0.3  0.05 0 0  0.05 0.1 0  0 0.1 0  0 0 0.15  0.05 0 0.15  0 0.1 0.15"
    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">
<UnstructuredGrid><Piece NumberOfPoints="10" NumberOfCells="1">
<FieldData>
<DataArray type="Int32" Name="ASTERMAX_CONVERGED_CLAIM" format="ascii">{converged}</DataArray>
<DataArray type="Int32" Name="ASTERMAX_INDUSTRIAL_VALIDATION_CLAIM" format="ascii">{industrial}</DataArray>
<DataArray type="Int32" Name="ASTERMAX_STRESS_IS_NODAL" format="ascii">{stress_is_nodal}</DataArray>
</FieldData>
<Points><DataArray type="Float64" NumberOfComponents="3" Name="Coordinates_mm" format="ascii">{points}</DataArray></Points>
<Cells>
<DataArray type="Int64" Name="connectivity" format="ascii">0 1 2 3 4 5 6 7 8 9</DataArray>
<DataArray type="Int64" Name="offsets" format="ascii">10</DataArray>
<DataArray type="UInt8" Name="types" format="ascii">24</DataArray>
</Cells>
<PointData><DataArray type="Float64" Name="U_mm" NumberOfComponents="3" format="ascii">{disp}</DataArray></PointData>
<CellData><DataArray type="Float64" Name="VON_MISES_IP_MAX_MPa" NumberOfComponents="1" format="ascii">123.5</DataArray></CellData>
</Piece></UnstructuredGrid></VTKFile>'''
    path.write_text(xml, encoding="utf-8")
    return sha256_file(path)


def test_load_hash_verified_vtu_and_preserve_result_representation(tmp_path: Path) -> None:
    path = tmp_path / "result.vtu"
    digest = _write_fixture(path)
    data = load_native_vtu_preview(path, expected_sha256=digest)
    assert data.schema == "AsterMaxNativeVtuPreviewV1"
    assert data.points_mm.shape == (10, 3)
    assert data.tet10_connectivity.shape == (1, 10)
    assert data.von_mises_ip_max_mpa.tolist() == [123.5]
    assert data.stress_is_nodal is False
    assert_native_preview_claim_boundary(data)


def test_native_preview_fails_closed_on_tampered_vtu(tmp_path: Path) -> None:
    path = tmp_path / "result.vtu"
    digest = _write_fixture(path)
    path.write_text(path.read_text(encoding="utf-8").replace("123.5", "999.0"), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_native_vtu_preview(path, expected_sha256=digest)


def test_projection_uses_actual_displacement_and_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "result.vtu"
    digest = _write_fixture(path)
    data = load_native_vtu_preview(path, expected_sha256=digest)
    p0, vm0 = projected_preview_geometry(data, deformation_scale=0.0)
    p1, vm1 = projected_preview_geometry(data, deformation_scale=1.0)
    p1_repeat, _ = projected_preview_geometry(data, deformation_scale=1.0)
    assert p0.shape == (10, 2)
    assert not np.allclose(p0, p1)
    assert np.allclose(p1, p1_repeat)
    assert np.array_equal(vm0, vm1)


def test_claim_boundary_rejects_unearned_convergence(tmp_path: Path) -> None:
    path = tmp_path / "result.vtu"
    digest = _write_fixture(path, converged=1)
    data = load_native_vtu_preview(path, expected_sha256=digest)
    with pytest.raises(ValueError, match="convergence"):
        assert_native_preview_claim_boundary(data)


def test_claim_boundary_rejects_nodal_stress_representation(tmp_path: Path) -> None:
    path = tmp_path / "result.vtu"
    digest = _write_fixture(path, stress_is_nodal=1)
    data = load_native_vtu_preview(path, expected_sha256=digest)
    with pytest.raises(ValueError, match="nodal stress"):
        assert_native_preview_claim_boundary(data)
