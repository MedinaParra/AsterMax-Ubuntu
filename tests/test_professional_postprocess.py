from __future__ import annotations

import numpy as np
import pytest

from astermax.cae_scene_contract import CaeSceneContract
from astermax.professional_postprocess import (
    ProfessionalPostprocessError,
    build_clip_plane,
    build_professional_postprocess_view,
    probe_nearest_node,
)


def _scene() -> CaeSceneContract:
    nodes = np.array([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 10.0],
    ])
    triangles = np.array([
        [0, 2, 1],
        [0, 1, 3],
        [0, 3, 2],
        [1, 2, 3],
    ], dtype=int)
    displacement = np.array([
        [0.0, 0.0, 0.0],
        [0.010, 0.0, 0.0],
        [0.020, 0.0, 0.0],
        [0.030, 0.0, 0.0],
    ])
    magnitude = np.linalg.norm(displacement, axis=1)
    mises = np.array([10.0, 20.0, 30.0, 40.0])
    tri_vm = mises[triangles].mean(axis=1)
    tri_norm = (tri_vm - tri_vm.min()) / (tri_vm.max() - tri_vm.min())
    return CaeSceneContract(
        undeformed_nodes_mm=nodes,
        deformed_nodes_mm=nodes + 2.0 * displacement,
        surface_triangles=triangles,
        nodal_von_mises_mpa=mises,
        triangle_von_mises_mpa=tri_vm,
        triangle_scalar_normalized=tri_norm,
        displacement_magnitude_mm=magnitude,
        scalar_min_mpa=10.0,
        scalar_max_mpa=40.0,
        deformation_scale=2.0,
        length_unit="mm",
        stress_unit="MPa",
        stress_representation="CODE_ASTER_SIEQ_NOEU:test;DISPLAY_SURFACE=NODE_AVERAGE_ONLY",
        workspace_sha256="a" * 64,
        solve_evidence_sha256="b" * 64,
    )


def test_stress_view_keeps_native_noeu_identity_and_provenance():
    scene = _scene()
    view = build_professional_postprocess_view(scene, field="SIEQ_NOEU", legend_levels=7)
    assert view.field == "SIEQ_NOEU"
    assert view.field_location == "NOEU"
    assert view.unit == "MPa"
    assert view.legend.minimum == 10.0
    assert view.legend.maximum == 40.0
    assert len(view.legend.levels) == 7
    assert view.workspace_sha256 == scene.workspace_sha256
    assert view.solve_evidence_sha256 == scene.solve_evidence_sha256
    assert "CODE_ASTER_SIEQ_NOEU" in view.legend.provenance


def test_displacement_magnitude_is_explicitly_derived_not_solver_native_scalar():
    scene = _scene()
    view = build_professional_postprocess_view(scene, field="DEPL_MAG")
    assert view.unit == "mm"
    assert view.field_location == "NOEU_DERIVED_FROM_DEPL"
    assert "ASTERMAX_NORM" in view.legend.provenance
    assert np.allclose(view.nodal_scalar, scene.displacement_magnitude_mm)


def test_deformation_scale_can_change_display_without_changing_physical_scalar():
    scene = _scene()
    view = build_professional_postprocess_view(scene, field="SIEQ_NOEU", deformation_scale=5.0)
    native_displacement = (scene.deformed_nodes_mm - scene.undeformed_nodes_mm) / scene.deformation_scale
    assert np.allclose(view.display_nodes_mm, scene.undeformed_nodes_mm + 5.0 * native_displacement)
    assert np.array_equal(view.nodal_scalar, scene.nodal_von_mises_mpa)


def test_probe_returns_nearest_native_node_with_units_and_provenance():
    scene = _scene()
    probe = probe_nearest_node(scene, (9.9, 0.1, 0.0), field="SIEQ_NOEU")
    assert probe.node_index == 1
    assert probe.value == 20.0
    assert probe.unit == "MPa"
    assert probe.field_location == "NOEU"
    assert probe.workspace_sha256 == scene.workspace_sha256


def test_clip_plane_partitions_all_surface_triangles_deterministically():
    scene = _scene()
    clip = build_clip_plane(scene, origin_mm=(2.0, 0.0, 0.0), normal=(1.0, 0.0, 0.0))
    all_indices = set(clip.kept_triangle_indices.tolist()) | set(clip.rejected_triangle_indices.tolist())
    assert all_indices == set(range(len(scene.surface_triangles)))
    assert set(clip.kept_triangle_indices.tolist()).isdisjoint(clip.rejected_triangle_indices.tolist())
    assert np.isclose(np.linalg.norm(np.asarray(clip.normal)), 1.0)


def test_unsupported_field_and_zero_clip_normal_fail_closed():
    scene = _scene()
    with pytest.raises(ProfessionalPostprocessError, match="FIELD_UNSUPPORTED"):
        build_professional_postprocess_view(scene, field="SIEQ_ELGA")
    with pytest.raises(ProfessionalPostprocessError, match="CLIP_NORMAL_ZERO"):
        build_clip_plane(scene, origin_mm=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 0.0))


def test_invalid_deformation_scale_and_legend_levels_fail_closed():
    scene = _scene()
    with pytest.raises(ProfessionalPostprocessError, match="DEFORMATION_SCALE_INVALID"):
        build_professional_postprocess_view(scene, deformation_scale=-1.0)
    with pytest.raises(ProfessionalPostprocessError, match="LEGEND_LEVELS_INVALID"):
        build_professional_postprocess_view(scene, legend_levels=1)
