from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from astermax.solver.med_result import read_code_aster_rmed
from astermax.solver.vtu_export import write_vtu
from test_med_result import build_structural_med


def _array(root, scope: str, name: str) -> np.ndarray:
    element = root.find(f".//{scope}/DataArray[@Name='{name}']")
    assert element is not None
    values = np.fromstring(element.text or "", sep=" ", dtype=np.float64)
    components = int(element.attrib.get("NumberOfComponents", "1"))
    if components > 1:
        values = values.reshape(-1, components)
    return values


def test_vtu_preserves_raw_nodal_and_element_nodal_values_exactly(tmp_path: Path) -> None:
    source = tmp_path / "structural.rmed"
    expected_depl, expected_stress = build_structural_med(source)
    result = read_code_aster_rmed(source)
    output = tmp_path / "result.vtu"
    evidence = write_vtu(result, output, relative_path="output/result.vtu")
    root = ElementTree.parse(output).getroot()
    displacement = _array(root, "PointData", "ASTERMAX_RAW__ELAS1___DEPL")
    raw_stress = _array(
        root,
        "FieldData",
        "ASTERMAX_RAW__ELAS1___SIGM_ELNO__TR7__ELEMENT_NODAL",
    ).reshape(1, 7, 6)
    assert np.array_equal(displacement, expected_depl)
    assert np.array_equal(raw_stress, expected_stress)
    assert evidence.source_sha256 == result.source_sha256
    assert evidence.fields[1].raw_shape == (1, 7, 6)


def test_von_mises_array_is_explicitly_derived_and_masked(tmp_path: Path) -> None:
    source = tmp_path / "structural.rmed"
    build_structural_med(source)
    result = read_code_aster_rmed(source)
    output = tmp_path / "result.vtu"
    write_vtu(result, output)
    root = ElementTree.parse(output).getroot()
    von_mises = _array(root, "CellData", "ASTERMAX_DERIVED__ELAS1___SIGM_ELNO__VON_MISES_MAX")
    mask = _array(root, "CellData", "ASTERMAX_MASK__ELAS1___SIGM_ELNO__APPLICABLE")
    assert von_mises.shape == (1,)
    assert mask.tolist() == [1.0]
