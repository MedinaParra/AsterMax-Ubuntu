from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from .results_quadratic_section import (
    ProductionQuadraticSectionViewV1,
    build_production_quadratic_section_view,
)
from .results_section_view import NativeSectionViewPayloadV1, build_native_section_view_payload
from .results_workspace import AsterMaxProfessionalResultsWorkspaceV1
from .results_workspace_ui import ResultsRenderPayloadV1


@dataclass(frozen=True)
class NativeSectionInstrumentStateV1:
    schema: str
    enabled: bool
    axis: str
    offset_mm: float
    sync_with_clip: bool
    state_sha256: str


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_section_instrument_state(
    *,
    enabled: bool,
    axis: str,
    offset_mm: float,
    sync_with_clip: bool = False,
) -> NativeSectionInstrumentStateV1:
    axis_name = str(axis).upper()
    if axis_name not in {"X", "Y", "Z"}:
        raise ValueError("SECTION_INSTRUMENT_AXIS")
    offset = float(offset_mm)
    if not math.isfinite(offset):
        raise ValueError("SECTION_INSTRUMENT_OFFSET")
    identity = {
        "schema": "AsterMaxNativeSectionInstrumentStateV1",
        "enabled": bool(enabled),
        "axis": axis_name,
        "offset_mm": offset,
        "sync_with_clip": bool(sync_with_clip),
    }
    return NativeSectionInstrumentStateV1(
        schema="AsterMaxNativeSectionInstrumentStateV1",
        enabled=bool(enabled),
        axis=axis_name,
        offset_mm=offset,
        sync_with_clip=bool(sync_with_clip),
        state_sha256=_sha256_json(identity),
    )


def resolve_section_instrument_state(
    state: NativeSectionInstrumentStateV1,
    *,
    clip_axis: str | None = None,
    clip_offset_mm: float | None = None,
) -> NativeSectionInstrumentStateV1:
    """Resolve the live section plane, optionally sharing the active clip controls."""
    if not state.sync_with_clip:
        return state
    if clip_axis is None or clip_offset_mm is None:
        raise ValueError("SECTION_INSTRUMENT_CLIP_SYNC_INPUT")
    return build_section_instrument_state(
        enabled=state.enabled,
        axis=clip_axis,
        offset_mm=clip_offset_mm,
        sync_with_clip=True,
    )


def _validate_live_provenance(
    workspace: AsterMaxProfessionalResultsWorkspaceV1,
    render_payload: ResultsRenderPayloadV1,
) -> None:
    if render_payload.workspace_sha256 != workspace.workspace_sha256:
        raise ValueError("SECTION_INSTRUMENT_WORKSPACE_STALE")
    if render_payload.solve_evidence_sha256 != workspace.solve_evidence_sha256:
        raise ValueError("SECTION_INSTRUMENT_SOLVE_STALE")


def build_live_section_view(
    state: NativeSectionInstrumentStateV1,
    workspace: AsterMaxProfessionalResultsWorkspaceV1,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    render_payload: ResultsRenderPayloadV1,
    *,
    canvas_width: float,
    canvas_height: float,
    margin: float = 38.0,
) -> NativeSectionViewPayloadV1 | None:
    """Legacy verified linearized section path retained for regression compatibility."""
    if not state.enabled:
        return None
    _validate_live_provenance(workspace, render_payload)
    return build_native_section_view_payload(
        np.asarray(nodes_mm, dtype=float),
        np.asarray(elements, dtype=np.int64),
        workspace_sha256=workspace.workspace_sha256,
        solve_evidence_sha256=workspace.solve_evidence_sha256,
        axis=state.axis,
        offset_mm=state.offset_mm,
        projected_view_xy=np.asarray(render_payload.projected_nodes_xy, dtype=float),
        canvas_width=float(canvas_width),
        canvas_height=float(canvas_height),
        margin=float(margin),
    )


def build_live_production_section_view(
    state: NativeSectionInstrumentStateV1,
    workspace: AsterMaxProfessionalResultsWorkspaceV1,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    render_payload: ResultsRenderPayloadV1,
    *,
    canvas_width: float,
    canvas_height: float,
    margin: float = 38.0,
    target_error_mm: float = 1.0e-3,
    topology_tolerance_mm: float = 1.0e-7,
    initial_sampling_divisions: int = 8,
    max_sampling_divisions: int = 128,
) -> ProductionQuadraticSectionViewV1 | None:
    """Production Results route: quadratic section or explicit BLOCKED payload.

    Unlike the retained linearized regression path, this function renders only the
    adaptive quadratic TET10/TRI6 assembly proven ready by the C5.4p/C5.4q gates.
    Non-converged or topologically invalid cuts return a BLOCKED payload with zero
    render polylines instead of silently falling back to corner-node geometry.
    """
    if not state.enabled:
        return None
    _validate_live_provenance(workspace, render_payload)
    return build_production_quadratic_section_view(
        np.asarray(nodes_mm, dtype=float),
        np.asarray(elements, dtype=np.int64),
        workspace_sha256=workspace.workspace_sha256,
        solve_evidence_sha256=workspace.solve_evidence_sha256,
        axis=state.axis,
        offset_mm=state.offset_mm,
        projected_view_xy=np.asarray(render_payload.projected_nodes_xy, dtype=float),
        canvas_width=float(canvas_width),
        canvas_height=float(canvas_height),
        margin=float(margin),
        target_error_mm=float(target_error_mm),
        topology_tolerance_mm=float(topology_tolerance_mm),
        initial_sampling_divisions=int(initial_sampling_divisions),
        max_sampling_divisions=int(max_sampling_divisions),
    )
