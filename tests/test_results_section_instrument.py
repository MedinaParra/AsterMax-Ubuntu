from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from astermax.fea.results_section_instrument import (
    build_live_section_view,
    build_section_instrument_state,
    resolve_section_instrument_state,
)
from astermax.fea.results_workspace import build_professional_results_workspace
from astermax.fea.results_workspace_ui import build_results_render_payload
from astermax.fea.solver import Tet10LinearStaticResult


def _fixture():
    nodes = np.asarray([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 10.0],
        [5.0, 0.0, 0.0],
        [5.0, 5.0, 0.0],
        [0.0, 5.0, 0.0],
        [0.0, 0.0, 5.0],
        [0.0, 5.0, 5.0],
        [5.0, 0.0, 5.0],
    ], dtype=float)
    elements = np.arange(10, dtype=np.int64).reshape((1, 10))
    displacement = np.zeros_like(nodes)
    displacement[:, 0] = np.linspace(0.0, 0.9, nodes.shape[0])
    stress = np.zeros((1, 4, 6), dtype=float)
    vm = np.asarray([[11.0, 22.0, 33.0, 44.0]], dtype=float)
    result = Tet10LinearStaticResult(displacement, np.zeros_like(nodes), stress, vm)
    workspace = build_professional_results_workspace(
        nodes, elements, result, solve_evidence_sha256="a" * 64, deformation_scale=2.0
    )
    render = build_results_render_payload(workspace, nodes, elements, result, field="U_MAG")
    return nodes, elements, result, workspace, render


def test_state_is_deterministic_axis_normalized_and_sensitive() -> None:
    first = build_section_instrument_state(enabled=True, axis="x", offset_mm=2.5)
    second = build_section_instrument_state(enabled=True, axis="X", offset_mm=2.5)
    moved = build_section_instrument_state(enabled=True, axis="X", offset_mm=3.5)
    disabled = build_section_instrument_state(enabled=False, axis="X", offset_mm=2.5)
    assert first == second
    assert first.axis == "X"
    assert len(first.state_sha256) == 64
    assert len({first.state_sha256, moved.state_sha256, disabled.state_sha256}) == 3


def test_state_fails_closed_on_invalid_axis_and_offset() -> None:
    with pytest.raises(ValueError, match="SECTION_INSTRUMENT_AXIS"):
        build_section_instrument_state(enabled=True, axis="Q", offset_mm=0.0)
    with pytest.raises(ValueError, match="SECTION_INSTRUMENT_OFFSET"):
        build_section_instrument_state(enabled=True, axis="X", offset_mm=float("nan"))


def test_clip_sync_reuses_exact_global_axis_and_absolute_mm_offset() -> None:
    state = build_section_instrument_state(enabled=True, axis="Z", offset_mm=9.0, sync_with_clip=True)
    resolved = resolve_section_instrument_state(state, clip_axis="y", clip_offset_mm=-3.25)
    assert resolved.enabled is True
    assert resolved.sync_with_clip is True
    assert resolved.axis == "Y"
    assert resolved.offset_mm == pytest.approx(-3.25)
    assert resolved.state_sha256 != state.state_sha256
    with pytest.raises(ValueError, match="SECTION_INSTRUMENT_CLIP_SYNC_INPUT"):
        resolve_section_instrument_state(state, clip_axis="X")


def test_disabled_state_builds_no_section_geometry() -> None:
    nodes, elements, _result, workspace, render = _fixture()
    state = build_section_instrument_state(enabled=False, axis="X", offset_mm=2.5)
    assert build_live_section_view(
        state, workspace, nodes, elements, render, canvas_width=900.0, canvas_height=600.0
    ) is None


def test_live_section_view_is_canvas_ready_and_provenance_bound() -> None:
    nodes, elements, _result, workspace, render = _fixture()
    state = build_section_instrument_state(enabled=True, axis="X", offset_mm=2.5)
    view = build_live_section_view(
        state, workspace, nodes, elements, render, canvas_width=900.0, canvas_height=600.0
    )
    assert view is not None
    assert view.axis == "X"
    assert view.offset_mm == pytest.approx(2.5)
    assert view.workspace_sha256 == workspace.workspace_sha256
    assert view.solve_evidence_sha256 == workspace.solve_evidence_sha256
    assert view.polyline_count == 1
    assert len(view.polylines[0].canvas_xy) == 3
    assert len(view.section_sha256) == 64
    assert len(view.view_sha256) == 64
    assert "visualization_only" in view.semantics


def test_live_section_moves_without_changing_raw_result_contract() -> None:
    nodes, elements, _result, workspace, render = _fixture()
    a = build_live_section_view(
        build_section_instrument_state(enabled=True, axis="X", offset_mm=2.5),
        workspace, nodes, elements, render, canvas_width=900.0, canvas_height=600.0,
    )
    b = build_live_section_view(
        build_section_instrument_state(enabled=True, axis="X", offset_mm=7.5),
        workspace, nodes, elements, render, canvas_width=900.0, canvas_height=600.0,
    )
    assert a is not None and b is not None
    assert a.section_sha256 != b.section_sha256
    assert a.view_sha256 != b.view_sha256
    assert render.value_min == pytest.approx(0.0)
    assert render.value_max == pytest.approx(0.9)
    assert render.workspace_sha256 == workspace.workspace_sha256


def test_live_section_fails_closed_on_stale_workspace_or_solve_render() -> None:
    nodes, elements, _result, workspace, render = _fixture()
    state = build_section_instrument_state(enabled=True, axis="X", offset_mm=2.5)
    with pytest.raises(ValueError, match="SECTION_INSTRUMENT_WORKSPACE_STALE"):
        build_live_section_view(
            state, workspace, nodes, elements,
            replace(render, workspace_sha256="b" * 64),
            canvas_width=900.0, canvas_height=600.0,
        )
    with pytest.raises(ValueError, match="SECTION_INSTRUMENT_SOLVE_STALE"):
        build_live_section_view(
            state, workspace, nodes, elements,
            replace(render, solve_evidence_sha256="c" * 64),
            canvas_width=900.0, canvas_height=600.0,
        )


def test_instrument_does_not_introduce_cut_field_or_ansys_claims() -> None:
    state = build_section_instrument_state(enabled=True, axis="X", offset_mm=2.5)
    text = repr(state).lower()
    for forbidden in ("von_mises", "stress", "resultant", "ansys_equivalence", "industrial_validation"):
        assert forbidden not in text
