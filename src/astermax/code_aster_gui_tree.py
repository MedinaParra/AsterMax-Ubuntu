from __future__ import annotations

from dataclasses import dataclass

from .code_aster_capabilities import CAPABILITIES, CapabilityStatus


@dataclass(frozen=True)
class GuiTreeNode:
    id: str
    label: str
    parent_id: str | None
    node_type: str
    enabled: bool
    status: CapabilityStatus | None = None
    roadmap_phase: str = ""
    ui_path: str = ""
    operator: str = ""
    keyword: str = ""
    unit: str | None = None


ROOT_ID = "code_aster"


def _category_id(category: str) -> str:
    return "category." + "".join(ch.lower() if ch.isalnum() else "_" for ch in category).strip("_")


def build_code_aster_gui_tree() -> tuple[GuiTreeNode, ...]:
    """Build the complete visible analysis tree from the capability registry.

    The model is renderer-neutral so Tk today and Qt/VTK later can consume the
    same capability truth. Schema-only capabilities remain visible but disabled.
    Variable nodes are children of their owning capability and inherit its enabled
    state. This prevents a visible GUI control from silently becoming a solver
    support claim.
    """
    nodes: list[GuiTreeNode] = [
        GuiTreeNode(
            id=ROOT_ID,
            label="Code_Aster Analysis Capabilities",
            parent_id=None,
            node_type="root",
            enabled=True,
        )
    ]
    categories: dict[str, str] = {}
    for capability in CAPABILITIES:
        category_id = _category_id(capability.category)
        if category_id not in categories:
            categories[category_id] = capability.category
            nodes.append(
                GuiTreeNode(
                    id=category_id,
                    label=capability.category,
                    parent_id=ROOT_ID,
                    node_type="category",
                    enabled=True,
                )
            )
        nodes.append(
            GuiTreeNode(
                id=capability.id,
                label=capability.label,
                parent_id=category_id,
                node_type="capability",
                enabled=capability.gui_selectable,
                status=capability.status,
                roadmap_phase=capability.roadmap_phase,
                ui_path=capability.gui_path,
            )
        )
        for variable in capability.variables:
            nodes.append(
                GuiTreeNode(
                    id=f"{capability.id}::{variable.id}",
                    label=variable.engineering_name,
                    parent_id=capability.id,
                    node_type="variable",
                    enabled=capability.gui_selectable,
                    status=capability.status,
                    roadmap_phase=capability.roadmap_phase,
                    ui_path=variable.ui_path,
                    operator=variable.operator,
                    keyword=variable.keyword,
                    unit=variable.unit,
                )
            )
    return tuple(nodes)


def gui_tree_summary() -> dict[str, int]:
    tree = build_code_aster_gui_tree()
    return {
        "total_nodes": len(tree),
        "categories": sum(node.node_type == "category" for node in tree),
        "capabilities": sum(node.node_type == "capability" for node in tree),
        "variables": sum(node.node_type == "variable" for node in tree),
        "enabled_capabilities": sum(node.node_type == "capability" and node.enabled for node in tree),
        "disabled_capabilities": sum(node.node_type == "capability" and not node.enabled for node in tree),
    }
