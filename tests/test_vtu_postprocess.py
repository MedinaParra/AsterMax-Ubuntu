from __future__ import annotations

import json
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

from astermax.fea.postprocess import write_linear_static_vtu
from astermax.fea.solver import solve_linear_static
from astermax.fea.tet4 import IsotropicMaterial


def test_vtu_contains_authentic_solver_fields_and_fail_closed_claims() -> None:
    nodes = np.array(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [0.0, 0.0, 10.0],
        ]
    )
    elements = np.array([[0, 1, 2, 3]], dtype=int)
    loads = np.zeros((4, 3))
    loads[1, 0] = 1000.0
    fixed = [0, 1, 2, 6, 7, 8, 9, 10, 11]
    result = solve_linear_static(
        nodes,
        elements,
        IsotropicMaterial(210000.0, 0.30),
        loads,
        fixed,
    )

    with tempfile.TemporaryDirectory() as tmp:
        vtu = Path(tmp) / "single_tet.vtu"
        manifest = write_linear_static_vtu(vtu, nodes, elements, result)

        assert vtu.is_file()
        sidecar = vtu.with_suffix(".vtu.manifest.json")
        assert sidecar.is_file()
        assert manifest.node_count == 4
        assert manifest.tet4_count == 1
        assert manifest.displacement_max_mm > 0.0
        assert manifest.von_mises_max_mpa > 0.0
        assert manifest.converged_claim is False
        assert manifest.industrial_validation_claim is False
        assert len(manifest.vtu_sha256) == 64

        parsed_manifest = json.loads(sidecar.read_text(encoding="utf-8"))
        assert parsed_manifest["result_class"] == "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT"
        assert parsed_manifest["units"] == {"length": "mm", "force": "N", "stress": "MPa"}
        assert parsed_manifest["converged_claim"] is False
        assert parsed_manifest["industrial_validation_claim"] is False

        root = ET.parse(vtu).getroot()
        piece = root.find("./UnstructuredGrid/Piece")
        assert piece is not None
        assert piece.attrib["NumberOfPoints"] == "4"
        assert piece.attrib["NumberOfCells"] == "1"

        arrays = {node.attrib.get("Name"): node for node in root.findall(".//DataArray")}
        for required in (
            "Coordinates_mm",
            "connectivity",
            "offsets",
            "types",
            "U_mm",
            "U_MAG_mm",
            "STRESS_MPa",
            "VON_MISES_MPa",
            "ASTERMAX_CONVERGED_CLAIM",
            "ASTERMAX_INDUSTRIAL_VALIDATION_CLAIM",
        ):
            assert required in arrays
        assert arrays["types"].text.strip() == "10"
        assert arrays["ASTERMAX_CONVERGED_CLAIM"].text.strip() == "0"
        assert arrays["ASTERMAX_INDUSTRIAL_VALIDATION_CLAIM"].text.strip() == "0"


def test_vtu_rejects_non_finite_fields() -> None:
    nodes = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    elements = np.array([[0, 1, 2, 3]])
    loads = np.zeros((4, 3))
    loads[1, 0] = 1.0
    fixed = [0, 1, 2, 6, 7, 8, 9, 10, 11]
    result = solve_linear_static(nodes, elements, IsotropicMaterial(210000.0, 0.3), loads, fixed)
    result.displacement_mm[1, 0] = np.nan

    with tempfile.TemporaryDirectory() as tmp:
        try:
            write_linear_static_vtu(Path(tmp) / "bad.vtu", nodes, elements, result)
        except ValueError as exc:
            assert "non-finite" in str(exc)
        else:
            raise AssertionError("non-finite fields must be rejected")
