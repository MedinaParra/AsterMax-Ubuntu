import numpy as np
import pytest

from astermax.fea.adaptive_tet10_section import build_adaptive_tet10_section


def _curved_tet10_fixture() -> tuple[np.ndarray, np.ndarray]:
    f = lambda r: r * r - r + 0.2
    p0 = np.array([0.0, 0.0, f(0.0)])
    p1 = np.array([1.0, 0.0, f(1.0)])
    p2 = np.array([0.0, 1.0, f(0.0)])
    p3 = np.array([0.0, 0.0, 1.0])
    p4 = np.array([0.5, 0.0, f(0.5)])
    p5 = np.array([0.5, 0.5, f(0.5)])
    p6 = np.array([0.0, 0.5, f(0.0)])
    p7 = 0.5 * (p0 + p3)
    p8 = 0.5 * (p2 + p3)
    p9 = 0.5 * (p1 + p3)
    return np.vstack((p0, p1, p2, p3, p4, p5, p6, p7, p8, p9)), np.arange(10, dtype=np.int64).reshape(1, 10)


def _linear_tet10_fixture() -> tuple[np.ndarray, np.ndarray]:
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([1.0, 0.0, 0.0])
    p2 = np.array([0.0, 1.0, 0.0])
    p3 = np.array([0.0, 0.0, 1.0])
    p4 = 0.5 * (p0 + p1)
    p5 = 0.5 * (p1 + p2)
    p6 = 0.5 * (p2 + p0)
    p7 = 0.5 * (p0 + p3)
    p8 = 0.5 * (p2 + p3)
    p9 = 0.5 * (p1 + p3)
    return np.vstack((p0, p1, p2, p3, p4, p5, p6, p7, p8, p9)), np.arange(10, dtype=np.int64).reshape(1, 10)


def _build(target: float = 1.0e-3, *, workspace: str = "workspace", solve: str = "solve"):
    nodes, elements = _curved_tet10_fixture()
    return build_adaptive_tet10_section(
        nodes,
        elements,
        plane_origin_mm=(0.0, 0.0, 0.0),
        plane_normal=(0.0, 0.0, 1.0),
        workspace_sha256=workspace,
        solve_evidence_sha256=solve,
        target_error_mm=target,
        initial_sampling_divisions=4,
        max_sampling_divisions=128,
    )


def test_adaptive_section_refines_until_declared_error_target():
    result = _build(1.0e-3)
    assert result.converged
    assert result.length_unit == "mm"
    assert result.max_plane_residual_mm <= result.target_error_mm
    assert result.max_chord_error_mm <= result.target_error_mm
    assert result.selected_sampling_divisions >= 4
    assert result.iterations[-1].converged
    assert all(
        later.sampling_divisions > earlier.sampling_divisions
        for earlier, later in zip(result.iterations, result.iterations[1:])
    )


def test_stricter_target_never_selects_coarser_converged_section():
    loose = _build(5.0e-3)
    strict = _build(5.0e-4)
    assert loose.converged and strict.converged
    assert strict.selected_sampling_divisions >= loose.selected_sampling_divisions
    assert strict.max_chord_error_mm <= strict.target_error_mm


def test_nonconvergence_is_explicit_and_fail_closed_at_resolution_cap():
    nodes, elements = _curved_tet10_fixture()
    result = build_adaptive_tet10_section(
        nodes,
        elements,
        plane_origin_mm=(0.0, 0.0, 0.0),
        plane_normal=(0.0, 0.0, 1.0),
        workspace_sha256="workspace",
        solve_evidence_sha256="solve",
        target_error_mm=1.0e-12,
        initial_sampling_divisions=4,
        max_sampling_divisions=4,
    )
    assert not result.converged
    assert result.selected_sampling_divisions == 4
    assert not result.iterations[-1].converged


def test_linear_tet_section_reports_one_closed_topological_component():
    nodes, elements = _linear_tet10_fixture()
    result = build_adaptive_tet10_section(
        nodes,
        elements,
        plane_origin_mm=(0.0, 0.0, 0.3),
        plane_normal=(0.0, 0.0, 1.0),
        workspace_sha256="workspace",
        solve_evidence_sha256="solve",
        target_error_mm=1.0e-10,
        topology_tolerance_mm=1.0e-8,
        initial_sampling_divisions=8,
        max_sampling_divisions=16,
    )
    assert result.converged
    assert result.connected_component_count == 1
    assert result.closed_component_count == 1
    assert result.open_component_count == 0
    assert result.max_chord_error_mm < 1.0e-12


def test_section_identity_is_deterministic_and_provenance_bound():
    first = _build()
    second = _build()
    assert first == second
    assert first.section_sha256 == second.section_sha256
    assert _build(workspace="workspace-2").section_sha256 != first.section_sha256
    assert _build(solve="solve-2").section_sha256 != first.section_sha256


def test_invalid_adaptive_contracts_fail_closed():
    nodes, elements = _linear_tet10_fixture()
    kwargs = dict(
        plane_origin_mm=(0.0, 0.0, 0.3),
        plane_normal=(0.0, 0.0, 1.0),
        workspace_sha256="workspace",
        solve_evidence_sha256="solve",
    )
    with pytest.raises(ValueError, match="TARGET_ERROR"):
        build_adaptive_tet10_section(nodes, elements, target_error_mm=0.0, **kwargs)
    with pytest.raises(ValueError, match="TOPOLOGY_TOLERANCE"):
        build_adaptive_tet10_section(nodes, elements, topology_tolerance_mm=0.0, **kwargs)
    with pytest.raises(ValueError, match="DIVISIONS"):
        build_adaptive_tet10_section(nodes, elements, initial_sampling_divisions=32, max_sampling_divisions=16, **kwargs)


def test_contract_does_not_claim_unvalidated_section_fea_quantities():
    result = _build(5.0e-3)
    text = repr(result).lower()
    for forbidden in (
        "stress_interpolation",
        "von_mises_field",
        "section_resultant",
        "industrial_validation",
        "ansys_equivalence",
    ):
        assert forbidden not in text
    assert "geometry_only_error_bounded" in result.semantics
