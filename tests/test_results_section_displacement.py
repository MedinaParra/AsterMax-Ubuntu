from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.adaptive_tet10_section import build_adaptive_tet10_section
from astermax.fea.section_polyline_assembly import assemble_section_polylines
from astermax.fea.section_displacement_field import build_section_displacement_field
from astermax.fea.results_section_displacement import build_section_displacement_contour, probe_section_displacement


def _linear_tet10():
    c = np.asarray(((0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.)), float)
    nodes = np.vstack((c, .5*(c[0]+c[1]), .5*(c[1]+c[2]), .5*(c[2]+c[0]), .5*(c[0]+c[3]), .5*(c[2]+c[3]), .5*(c[1]+c[3])))
    return nodes, np.arange(10, dtype=np.int64).reshape(1,10)


def _affine(points):
    x,y,z = points[:,0], points[:,1], points[:,2]
    return np.column_stack((1+2*x-3*y+.5*z, -2+x+4*y-z, .25-.5*x+2*z))


def _reference(nodes):
    return np.column_stack((nodes[:,0] + .36*nodes[:,2], -nodes[:,1] + .22*nodes[:,2]))


def _field(nodes, elements, nodal):
    section = build_adaptive_tet10_section(nodes,elements,plane_origin_mm=(0.,0.,.3),plane_normal=(0.,0.,1.),workspace_sha256="workspace-c5-4t",solve_evidence_sha256="solve-c5-4t",target_error_mm=1e-10,topology_tolerance_mm=1e-8,initial_sampling_divisions=4,max_sampling_divisions=8)
    assembly = assemble_section_polylines(section, endpoint_tolerance_mm=1e-8)
    return build_section_displacement_field(nodes,elements,nodal,assembly,workspace_sha256="workspace-c5-4t",solve_evidence_sha256="solve-c5-4t",geometry_tolerance_mm=1e-10,cross_element_tolerance_mm=1e-10)


def _contour(nodes, elements, nodal, width=900.):
    return build_section_displacement_contour(nodes,elements,nodal,workspace_sha256="workspace-c5-4t",solve_evidence_sha256="solve-c5-4t",axis="Z",offset_mm=.3,projected_view_xy=_reference(nodes),canvas_width=width,canvas_height=650.,target_error_mm=1e-10,topology_tolerance_mm=1e-8,initial_sampling_divisions=4,max_sampling_divisions=8,geometry_tolerance_mm=1e-10,cross_element_tolerance_mm=1e-10)


def test_affine_u_mag_contour_is_ready_and_bounded():
    nodes,elements = _linear_tet10(); nodal = _affine(nodes)
    contour = _contour(nodes,elements,nodal)
    assert contour.status == "READY"
    assert contour.polyline_count == 1
    assert contour.field_sha256
    assert contour.min_displacement_magnitude_mm <= contour.max_displacement_magnitude_mm
    assert contour.max_geometry_residual_mm < 1e-10
    assert all(0.0 <= value <= 1.0 for value in contour.polylines[0].normalized_scalar)


def test_contour_determinism_and_canvas_separation():
    nodes,elements = _linear_tet10(); nodal = _affine(nodes)
    a = _contour(nodes,elements,nodal,900.); b = _contour(nodes,elements,nodal,900.); resized = _contour(nodes,elements,nodal,1200.)
    assert a.contour_sha256 == b.contour_sha256
    assert a.field_sha256 == resized.field_sha256
    assert a.assembly_sha256 == resized.assembly_sha256
    assert a.contour_sha256 != resized.contour_sha256


def test_probe_returns_verified_vector_and_magnitude():
    nodes,elements = _linear_tet10(); nodal = _affine(nodes)
    contour = _contour(nodes,elements,nodal); field = _field(nodes,elements,nodal)
    x,y = contour.polylines[0].canvas_xy[0]
    probe = probe_section_displacement(contour,field.samples,canvas_x=x+.2,canvas_y=y-.2,max_distance_px=2.)
    assert probe.hit
    expected = _affine(np.asarray([probe.point_mm]))[0]
    assert np.allclose(probe.displacement_mm, expected, rtol=0., atol=1e-11)
    assert probe.displacement_magnitude_mm == pytest.approx(float(np.linalg.norm(expected)), abs=1e-11)
    assert probe.field_sha256 == contour.field_sha256


def test_probe_miss_and_invalid_radius_are_explicit():
    nodes,elements = _linear_tet10(); nodal = _affine(nodes)
    contour = _contour(nodes,elements,nodal); field = _field(nodes,elements,nodal)
    miss = probe_section_displacement(contour,field.samples,canvas_x=-1000.,canvas_y=-1000.,max_distance_px=1.)
    assert not miss.hit
    with pytest.raises(ValueError, match="SECTION_PROBE_RADIUS"):
        probe_section_displacement(contour,field.samples,canvas_x=0.,canvas_y=0.,max_distance_px=0.)


def test_field_change_changes_contour_field_identity():
    nodes,elements = _linear_tet10(); nodal = _affine(nodes)
    a = _contour(nodes,elements,nodal)
    changed = nodal.copy(); changed[0,0] += .01
    b = _contour(nodes,elements,changed)
    assert a.field_sha256 != b.field_sha256
    assert a.contour_sha256 != b.contour_sha256


def test_stale_or_invalid_inputs_fail_closed():
    nodes,elements = _linear_tet10(); nodal = _affine(nodes)
    with pytest.raises(ValueError, match="SECTION_CONTOUR_AXIS"):
        build_section_displacement_contour(nodes,elements,nodal,workspace_sha256="w",solve_evidence_sha256="s",axis="Q",offset_mm=.3,projected_view_xy=_reference(nodes),canvas_width=900.,canvas_height=650.)


def test_contract_does_not_claim_unverified_stress_or_resultants():
    nodes,elements = _linear_tet10(); contour = _contour(nodes,elements,_affine(nodes))
    text = (contour.schema + " " + contour.semantics).lower()
    forbidden = ("von_mises", "stress_interpolation", "section_resultant", "ansys_equivalence")
    assert not any(token in text for token in forbidden)
