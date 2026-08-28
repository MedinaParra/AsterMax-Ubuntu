from dataclasses import replace
import math

import pytest

from astermax.credibility import canonical_sha256
from astermax.fea.analytical_load_case import (
    AnalyticalLoadCaseError,
    build_analytical_load_case,
    build_load_case_witnesses,
)
from astermax.fea.circular_section import CircularSectionApplicability
from astermax.fea.section_evidence import PlanarSectionProperties


def _section():
    area = math.pi * 10.0**2
    i = math.pi * 10.0**4 / 4.0
    payload = {
        "schema": "AsterMaxPlanarSectionPropertiesV1",
        "selection_id": "S",
        "source_sha256": "1" * 64,
        "face_signature_sha256": "2" * 64,
        "area_mm2": area,
        "centroid_mm": (0.0, 0.0, 0.0),
        "normal": (1.0, 0.0, 0.0),
        "axis_u": (0.0, 1.0, 0.0),
        "axis_v": (0.0, 0.0, 1.0),
        "i_u_mm4": i,
        "i_v_mm4": i,
        "i_uv_mm4": 0.0,
        "principal_i_min_mm4": i,
        "principal_i_max_mm4": i,
        "polar_i_n_mm4": 2.0 * i,
        "polar_identity_relative_residual": 0.0,
        "method": "TEST",
    }
    return PlanarSectionProperties(**payload, section_sha256=canonical_sha256(payload))


def _app(section):
    payload = {
        "schema": "AsterMaxCircularSectionApplicabilityV1",
        "selection_id": section.selection_id,
        "source_sha256": section.source_sha256,
        "section_sha256": section.section_sha256,
        "face_signature_sha256": section.face_signature_sha256,
        "radius_mm": 10.0,
        "area_mm2": section.area_mm2,
        "polar_j_mm4": section.polar_i_n_mm4,
        "boundary_curve_count": 1,
        "boundary_curve_types": ("Circle",),
        "inertia_isotropy_relative_residual": 0.0,
        "product_inertia_relative_residual": 0.0,
        "circular_polar_identity_relative_residual": 0.0,
        "method": "TEST",
    }
    return CircularSectionApplicability(**payload, applicability_sha256=canonical_sha256(payload))


def test_same_load_case_rebuilds_same_witnesses():
    section = _section(); app = _app(section)
    load = build_analytical_load_case(
        load_case_id="LC1",
        selection_id="S",
        section_sha256=section.section_sha256,
        axial_force_n=1000.0,
        moment_u_nmm=2000.0,
        moment_v_nmm=-3000.0,
        torque_nmm=4000.0,
    )
    first = build_load_case_witnesses(section, app, load)
    second = build_load_case_witnesses(section, app, load)
    assert first == second


def test_load_case_hash_changes_when_one_resultant_changes():
    section = _section()
    a = build_analytical_load_case(
        load_case_id="LC1", selection_id="S", section_sha256=section.section_sha256,
        axial_force_n=1.0, moment_u_nmm=2.0, moment_v_nmm=3.0, torque_nmm=4.0,
    )
    b = build_analytical_load_case(
        load_case_id="LC1", selection_id="S", section_sha256=section.section_sha256,
        axial_force_n=1.0, moment_u_nmm=2.0, moment_v_nmm=3.0, torque_nmm=4.1,
    )
    assert a.load_case_sha256 != b.load_case_sha256


def test_load_case_rejects_section_hash_mismatch():
    section = _section(); app = _app(section)
    load = build_analytical_load_case(
        load_case_id="LC1", selection_id="S", section_sha256="9" * 64,
        axial_force_n=1.0, moment_u_nmm=2.0, moment_v_nmm=3.0, torque_nmm=4.0,
    )
    with pytest.raises(AnalyticalLoadCaseError, match="SECTION_SHA_MISMATCH"):
        build_load_case_witnesses(section, app, load)
