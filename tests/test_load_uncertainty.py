import math

import pytest

from astermax.credibility import canonical_sha256
from astermax.fea.analytical_load_case import build_analytical_load_case
from astermax.fea.circular_section import CircularSectionApplicability
from astermax.fea.load_uncertainty import (
    LoadUncertaintyBounds,
    bounded_load_uncertainty_envelope,
)
from astermax.fea.section_evidence import PlanarSectionProperties


def _section_and_app():
    area = math.pi * 10.0**2
    i = math.pi * 10.0**4 / 4.0
    section_payload = {
        "schema": "AsterMaxPlanarSectionPropertiesV1", "selection_id": "S",
        "source_sha256": "1" * 64, "face_signature_sha256": "2" * 64,
        "area_mm2": area, "centroid_mm": (0.0, 0.0, 0.0),
        "normal": (1.0, 0.0, 0.0), "axis_u": (0.0, 1.0, 0.0), "axis_v": (0.0, 0.0, 1.0),
        "i_u_mm4": i, "i_v_mm4": i, "i_uv_mm4": 0.0,
        "principal_i_min_mm4": i, "principal_i_max_mm4": i,
        "polar_i_n_mm4": 2.0 * i, "polar_identity_relative_residual": 0.0, "method": "TEST",
    }
    section = PlanarSectionProperties(**section_payload, section_sha256=canonical_sha256(section_payload))
    app_payload = {
        "schema": "AsterMaxCircularSectionApplicabilityV1", "selection_id": "S",
        "source_sha256": section.source_sha256, "section_sha256": section.section_sha256,
        "face_signature_sha256": section.face_signature_sha256, "radius_mm": 10.0,
        "area_mm2": area, "polar_j_mm4": 2.0 * i, "boundary_curve_count": 1,
        "boundary_curve_types": ("Circle",), "inertia_isotropy_relative_residual": 0.0,
        "product_inertia_relative_residual": 0.0, "circular_polar_identity_relative_residual": 0.0,
        "method": "TEST",
    }
    app = CircularSectionApplicability(**app_payload, applicability_sha256=canonical_sha256(app_payload))
    return section, app


def _load(section):
    return build_analytical_load_case(
        load_case_id="LC1", selection_id="S", section_sha256=section.section_sha256,
        axial_force_n=1000.0, moment_u_nmm=2000.0, moment_v_nmm=-3000.0, torque_nmm=4000.0,
    )


def test_zero_uncertainty_returns_nominal_envelope():
    section, app = _section_and_app(); load = _load(section)
    result = bounded_load_uncertainty_envelope(
        section, app, load,
        LoadUncertaintyBounds(0.0, 0.0, 0.0, 0.0),
    )
    assert result.vertex_count == 16
    assert result.worst_case_max_von_mises_mpa == pytest.approx(result.nominal_max_von_mises_mpa)
    assert result.amplification_factor == pytest.approx(1.0)


def test_nonzero_load_uncertainty_cannot_reduce_worst_case_envelope():
    section, app = _section_and_app(); load = _load(section)
    result = bounded_load_uncertainty_envelope(
        section, app, load,
        LoadUncertaintyBounds(200.0, 500.0, 500.0, 1000.0),
    )
    assert result.worst_case_max_von_mises_mpa >= result.nominal_max_von_mises_mpa
    assert result.amplification_factor >= 1.0
    assert len(result.critical_vertex_resultants) == 4


def test_uncertainty_hash_is_deterministic():
    section, app = _section_and_app(); load = _load(section)
    bounds = LoadUncertaintyBounds(10.0, 20.0, 30.0, 40.0)
    assert bounded_load_uncertainty_envelope(section, app, load, bounds) == bounded_load_uncertainty_envelope(section, app, load, bounds)
