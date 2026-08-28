from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from astermax.credibility import canonical_sha256
from .arbitrary_bc import prepare_arbitrary_bc_model, solve_arbitrary_bc_model
from .evidence import sha256_file
from .native_cad_picker_ui import NativeCadPickerAssignment


class ProductionPickerRoutingError(ValueError):
    pass


@dataclass(frozen=True)
class ProductionPickerRoute:
    schema: str
    source_step_sha256: str
    support_face_ids: tuple[str, ...]
    load_face_ids: tuple[str, ...]
    support_named_selection_sha256: str
    load_named_selection_sha256: str
    support_binding_sha256: str
    load_binding_sha256: str
    mesh_size_mm: float
    route_sha256: str


def prepare_picker_routed_model(
    step_path: str | Path,
    assignment: NativeCadPickerAssignment,
    *,
    mesh_size_mm: float,
) -> dict:
    """Route the exact native picker assignment into the production arbitrary-BC preparation.

    The route is intentionally independent of X/Y/Z MIN/MAX authoring keys. It
    verifies the STEP identity and requires the bindings rebuilt by the
    production preparation path to match the bindings created by the picker.
    """
    step = Path(step_path).expanduser().resolve()
    current_step_sha = sha256_file(step)
    if current_step_sha != assignment.support_selection.source_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_SUPPORT_STEP_STALE")
    if current_step_sha != assignment.load_selection.source_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_LOAD_STEP_STALE")
    if assignment.support_selection.named_selection_sha256 != assignment.support_binding.named_selection_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_SUPPORT_SELECTION_BINDING_MISMATCH")
    if assignment.load_selection.named_selection_sha256 != assignment.load_binding.named_selection_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_LOAD_SELECTION_BINDING_MISMATCH")
    if set(assignment.support_binding.face_signature_sha256) & set(assignment.load_binding.face_signature_sha256):
        raise ProductionPickerRoutingError("PICKER_ROUTE_SUPPORT_LOAD_OVERLAP")

    prepared = prepare_arbitrary_bc_model(
        step,
        mesh_size_mm=float(mesh_size_mm),
        support_selection=assignment.support_selection,
        load_selection=assignment.load_selection,
    )
    rebuilt_support = prepared["support_binding"]
    rebuilt_load = prepared["load_binding"]
    if rebuilt_support.binding_sha256 != assignment.support_binding.binding_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_SUPPORT_BINDING_REBUILD_MISMATCH")
    if rebuilt_load.binding_sha256 != assignment.load_binding.binding_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_LOAD_BINDING_REBUILD_MISMATCH")

    core = {
        "schema": "AsterMaxProductionPickerRouteV1",
        "source_step_sha256": current_step_sha,
        "support_face_ids": list(assignment.support_face_ids),
        "load_face_ids": list(assignment.load_face_ids),
        "support_named_selection_sha256": assignment.support_selection.named_selection_sha256,
        "load_named_selection_sha256": assignment.load_selection.named_selection_sha256,
        "support_binding_sha256": assignment.support_binding.binding_sha256,
        "load_binding_sha256": assignment.load_binding.binding_sha256,
        "mesh_size_mm": float(mesh_size_mm),
    }
    route = ProductionPickerRoute(
        schema=core["schema"],
        source_step_sha256=current_step_sha,
        support_face_ids=tuple(assignment.support_face_ids),
        load_face_ids=tuple(assignment.load_face_ids),
        support_named_selection_sha256=assignment.support_selection.named_selection_sha256,
        load_named_selection_sha256=assignment.load_selection.named_selection_sha256,
        support_binding_sha256=assignment.support_binding.binding_sha256,
        load_binding_sha256=assignment.load_binding.binding_sha256,
        mesh_size_mm=float(mesh_size_mm),
        route_sha256=canonical_sha256(core),
    )
    prepared["picker_assignment"] = assignment
    prepared["production_picker_route"] = route
    return prepared


def verify_picker_route(prepared: dict) -> ProductionPickerRoute:
    route = prepared.get("production_picker_route")
    assignment = prepared.get("picker_assignment")
    evidence = prepared.get("evidence")
    if not isinstance(route, ProductionPickerRoute):
        raise ProductionPickerRoutingError("PICKER_ROUTE_EVIDENCE_MISSING")
    if not isinstance(assignment, NativeCadPickerAssignment):
        raise ProductionPickerRoutingError("PICKER_ROUTE_ASSIGNMENT_MISSING")
    if evidence is None:
        raise ProductionPickerRoutingError("PICKER_ROUTE_PREPARATION_EVIDENCE_MISSING")
    if evidence.source_step_sha256 != route.source_step_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_STEP_STALE")
    if evidence.support_binding_sha256 != route.support_binding_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_SUPPORT_BINDING_STALE")
    if evidence.load_binding_sha256 != route.load_binding_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_LOAD_BINDING_STALE")
    core = {
        "schema": route.schema,
        "source_step_sha256": route.source_step_sha256,
        "support_face_ids": list(route.support_face_ids),
        "load_face_ids": list(route.load_face_ids),
        "support_named_selection_sha256": route.support_named_selection_sha256,
        "load_named_selection_sha256": route.load_named_selection_sha256,
        "support_binding_sha256": route.support_binding_sha256,
        "load_binding_sha256": route.load_binding_sha256,
        "mesh_size_mm": route.mesh_size_mm,
    }
    if canonical_sha256(core) != route.route_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_SHA_MISMATCH")
    return route


def solve_picker_routed_model(
    prepared: dict,
    *,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
) -> dict:
    """Solve only a verified picker-routed preparation through the production sparse path."""
    route = verify_picker_route(prepared)
    solved = solve_arbitrary_bc_model(
        prepared,
        young_modulus_mpa=float(young_modulus_mpa),
        poisson_ratio=float(poisson_ratio),
        resultant_n=resultant_n,
    )
    evidence = solved["solve_evidence"]
    if evidence.support_binding_sha256 != route.support_binding_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_SOLVE_SUPPORT_BINDING_MISMATCH")
    if evidence.load_binding_sha256 != route.load_binding_sha256:
        raise ProductionPickerRoutingError("PICKER_ROUTE_SOLVE_LOAD_BINDING_MISMATCH")
    solved["production_picker_route"] = route
    return solved
