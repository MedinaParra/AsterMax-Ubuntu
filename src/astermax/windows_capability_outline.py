from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .code_aster_capabilities import CapabilityStatus
from .code_aster_gui_tree import GuiTreeNode, build_code_aster_gui_tree


class TreeLike(Protocol):
    def insert(self, parent: str, index: str, *, iid: str, text: str, open: bool = False, tags=()): ...
    def tag_configure(self, tagname: str, **kwargs): ...


@dataclass(frozen=True)
class OutlineRow:
    id: str
    parent_id: str
    label: str
    node_type: str
    enabled: bool
    status: CapabilityStatus | None
    roadmap_phase: str
    ui_path: str
    operator: str
    keyword: str
    unit: str | None
    tags: tuple[str, ...]


@dataclass(frozen=True)
class CapabilitySelection:
    node_id: str
    enabled: bool
    title: str
    status_text: str
    roadmap_phase: str
    ui_path: str
    operator_binding: str
    unit: str | None
    action: str
    message: str


_STATUS_LABELS = {
    CapabilityStatus.NOT_IMPLEMENTED: "Not implemented",
    CapabilityStatus.SCHEMA_ONLY: "Schema only",
    CapabilityStatus.IMPLEMENTED_UNVERIFIED: "Implemented · numerical verification pending",
    CapabilityStatus.VERIFIED: "Verified",
}


def _display_label(node: GuiTreeNode) -> str:
    if node.node_type == "capability" and node.status is not None:
        marker = "✓" if node.status is CapabilityStatus.VERIFIED else "●" if node.enabled else "○"
        return f"{marker} {node.label}"
    if node.node_type == "variable":
        suffix = f" [{node.unit}]" if node.unit else ""
        return f"{node.label}{suffix}"
    return node.label


def build_windows_outline_rows() -> tuple[OutlineRow, ...]:
    """Translate the renderer-neutral registry tree into Windows-outline rows.

    The adapter deliberately keeps schema-only capabilities visible while tagging
    them disabled. It never promotes IMPLEMENTED_UNVERIFIED into VERIFIED.
    """
    rows: list[OutlineRow] = []
    for node in build_code_aster_gui_tree():
        if node.parent_id is None:
            continue
        tags = [node.node_type]
        if node.node_type in {"capability", "variable"}:
            tags.append("enabled" if node.enabled else "disabled")
        if node.status is not None:
            tags.append("status_" + node.status.value.lower())
        rows.append(
            OutlineRow(
                id=node.id,
                parent_id=node.parent_id,
                label=_display_label(node),
                node_type=node.node_type,
                enabled=node.enabled,
                status=node.status,
                roadmap_phase=node.roadmap_phase,
                ui_path=node.ui_path,
                operator=node.operator,
                keyword=node.keyword,
                unit=node.unit,
                tags=tuple(tags),
            )
        )
    return tuple(rows)


def configure_outline_tags(tree: TreeLike) -> None:
    """Apply semantic tags without using color as the sole status signal."""
    tree.tag_configure("category", font=("Segoe UI", 9, "bold"))
    tree.tag_configure("disabled", foreground="#777777")
    tree.tag_configure("status_verified", font=("Segoe UI", 9, "bold"))


def populate_capability_outline(tree: TreeLike, *, root_parent: str = "") -> tuple[OutlineRow, ...]:
    """Populate a ttk.Treeview-compatible object from the capability registry."""
    configure_outline_tags(tree)
    rows = build_windows_outline_rows()
    root_id = "code_aster"
    tree.insert(root_parent, "end", iid=root_id, text="Code_Aster Capabilities", open=True, tags=("category",))
    for row in rows:
        parent = root_id if row.parent_id == root_id else row.parent_id
        tree.insert(parent, "end", iid=row.id, text=row.label, open=row.node_type == "category", tags=row.tags)
    return rows


def selection_contract(node_id: str) -> CapabilitySelection:
    """Return the fail-closed UI action contract for an outline selection."""
    nodes = {node.id: node for node in build_code_aster_gui_tree()}
    node = nodes.get(node_id)
    if node is None:
        raise KeyError(f"Unknown capability outline node: {node_id}")

    status_text = _STATUS_LABELS.get(node.status, "")
    operator_binding = ""
    if node.operator or node.keyword:
        operator_binding = "/".join(part for part in (node.operator, node.keyword) if part)

    if node.node_type in {"root", "category"}:
        return CapabilitySelection(
            node_id=node.id,
            enabled=True,
            title=node.label,
            status_text="Capability group",
            roadmap_phase="",
            ui_path="",
            operator_binding="",
            unit=None,
            action="EXPAND",
            message="Browse Code_Aster capabilities and their engineering variables.",
        )

    if not node.enabled:
        return CapabilitySelection(
            node_id=node.id,
            enabled=False,
            title=node.label,
            status_text=status_text,
            roadmap_phase=node.roadmap_phase,
            ui_path=node.ui_path,
            operator_binding=operator_binding,
            unit=node.unit,
            action="BLOCKED",
            message=(
                "Visible for roadmap transparency, but disabled until its implementation "
                "and verification harness gates pass. No solver support is implied."
            ),
        )

    return CapabilitySelection(
        node_id=node.id,
        enabled=True,
        title=node.label,
        status_text=status_text,
        roadmap_phase=node.roadmap_phase,
        ui_path=node.ui_path,
        operator_binding=operator_binding,
        unit=node.unit,
        action="OPEN_ANALYSIS" if node.node_type == "capability" else "OPEN_PROPERTY",
        message=(
            "Capability is available in the PMV workflow. "
            "Numerical verification remains separate from GUI availability."
            if node.status is CapabilityStatus.IMPLEMENTED_UNVERIFIED
            else "Capability passed its declared verification gate."
        ),
    )


def capability_outline_evidence() -> dict[str, object]:
    rows = build_windows_outline_rows()
    capabilities = [row for row in rows if row.node_type == "capability"]
    variables = [row for row in rows if row.node_type == "variable"]
    return {
        "contract": "ASTERMAX_WINDOWS_CAPABILITY_OUTLINE_V1",
        "capability_count": len(capabilities),
        "variable_count": len(variables),
        "enabled_capabilities": [row.id for row in capabilities if row.enabled],
        "disabled_capabilities": [row.id for row in capabilities if not row.enabled],
        "verified_capabilities": [row.id for row in capabilities if row.status is CapabilityStatus.VERIFIED],
        "implemented_unverified_capabilities": [
            row.id for row in capabilities if row.status is CapabilityStatus.IMPLEMENTED_UNVERIFIED
        ],
        "fea_solve_executed": False,
        "numerical_verification": False,
        "results_verified": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
