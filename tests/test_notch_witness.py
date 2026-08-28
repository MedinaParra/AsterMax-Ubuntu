import math
import pytest

from astermax.fea.bounded_stress_concentration import build_stress_concentration_grid
from astermax.fea.notch_witness import NotchWitnessError, build_notch_stress_witness
from astermax.fea.shaft_shoulder import build_shaft_shoulder_geometry
from astermax.fea.stress_concentration_source import build_stress_concentration_source


def _source():
    return build_stress_concentration_source(
        source_id="SYNTHETIC_NOTCH_SOURCE",
        title="Synthetic notch verification",
        edition_or_release="1",
        publisher="AsterMax verification",
        locator="synthetic",
        source_url="https://example.invalid/notch",
        rights_note="SYNTHETIC_SOFTWARE_VERIFICATION_DATA",
    )


def _grid(name, mode, values):
    src = _source()
    return build_stress_concentration_grid(
        dataset_id=f"{name}_{mode}",
        factor_name=name,
        load_mode=mode,
        source_provenance_sha256=src.provenance_sha256,
        diameter_ratios=(1.1, 1.3),
        radius_ratios=(0.02, 0.10),
        factors=values,
    )


def test_notch_witness_combines_bending_and_torsion_factors():
    geometry = build_shaft_shoulder_geometry(
        geometry_id="S1",
        small_diameter_mm=100.0,
        large_diameter_mm=120.0,
        fillet_radius_mm=6.0,
    )
    kt = _grid("Kt", "BENDING", ((2.0, 1.5), (2.4, 1.7)))
    kts = _grid("Kts", "TORSION", ((1.8, 1.3), (2.0, 1.5)))
    witness = build_notch_stress_witness(
        geometry,
        bending_grid=kt,
        torsion_grid=kts,
        nominal_normal_stress_mpa=100.0,
        nominal_shear_stress_mpa=40.0,
    )
    assert witness.kt == pytest.approx((2.0 + 1.5 + 2.4 + 1.7) / 4.0)
    assert witness.kts == pytest.approx((1.8 + 1.3 + 2.0 + 1.5) / 4.0)
    expected = math.sqrt(
        witness.local_normal_stress_mpa**2 + 3.0 * witness.local_shear_stress_mpa**2
    )
    assert witness.local_von_mises_mpa == pytest.approx(expected)


def test_notch_witness_rejects_wrong_factor_role():
    geometry = build_shaft_shoulder_geometry(
        geometry_id="S1",
        small_diameter_mm=100.0,
        large_diameter_mm=120.0,
        fillet_radius_mm=6.0,
    )
    bad = _grid("Kts", "TORSION", ((1.8, 1.3), (2.0, 1.5)))
    with pytest.raises(NotchWitnessError, match="BENDING_GRID"):
        build_notch_stress_witness(
            geometry,
            bending_grid=bad,
            torsion_grid=bad,
            nominal_normal_stress_mpa=100.0,
            nominal_shear_stress_mpa=40.0,
        )
