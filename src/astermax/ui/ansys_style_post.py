from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from astermax.solver.fe_result_package import (
    ElementFamily,
    FEFieldV1,
    FEResultPackageV1,
    FieldAssociation,
)


class StressDisplayMode(StrEnum):
    ELEMENTAL_UNAVERAGED = "ELEMENTAL_UNAVERAGED"
    NODAL_AVERAGED = "NODAL_AVERAGED"


@dataclass(frozen=True)
class AnsysStyleViewConfig:
    field_name: str
    stress_display_mode: StressDisplayMode = StressDisplayMode.NODAL_AVERAGED
    deformation_scale: float = 1.0
    show_mesh: bool = False
    show_nodes: bool = False
    show_undeformed_wireframe: bool = False
    clip_normal: tuple[float, float, float] | None = None
    clip_origin_mm: tuple[float, float, float] | None = None

    def __post_init__(self) -> None:
        if self.deformation_scale < 0:
            raise ValueError("deformation scale cannot be negative")
        if (self.clip_normal is None) != (self.clip_origin_mm is None):
            raise ValueError("clip_normal and clip_origin_mm must be supplied together")
        if self.clip_normal is not None and np.linalg.norm(self.clip_normal) <= 1e-12:
            raise ValueError("clip normal cannot be zero")


def _tet_volume_mm3(nodes: np.ndarray, connectivity: list[int]) -> float:
    corner_ids = connectivity[:4]
    x = nodes[np.asarray(corner_ids, dtype=int)]
    matrix = np.column_stack((x[1] - x[0], x[2] - x[0], x[3] - x[0]))
    return abs(float(np.linalg.det(matrix))) / 6.0


def volume_weighted_cell_to_point_scalar(
    package: FEResultPackageV1,
    cell_values: np.ndarray,
) -> np.ndarray:
    """Deterministically average cell scalars to nodes using element volume weights.

    This is a display field only. It does not replace the raw elemental solver field.
    For Tet10, all ten nodes receive the parent element weight while volume is computed
    from the four corner nodes.
    """

    values = np.asarray(cell_values, dtype=float)
    if values.shape != (len(package.mesh.connectivity),):
        raise ValueError("cell scalar length must equal element count")
    nodes = np.asarray(package.mesh.nodes_mm, dtype=float)
    numerator = np.zeros(len(nodes), dtype=float)
    denominator = np.zeros(len(nodes), dtype=float)
    for element_index, conn in enumerate(package.mesh.connectivity):
        volume = _tet_volume_mm3(nodes, conn)
        if not np.isfinite(volume) or volume <= 1e-12:
            raise ValueError(f"element {element_index} has invalid geometric volume")
        for node_id in conn:
            numerator[node_id] += values[element_index] * volume
            denominator[node_id] += volume
    if np.any(denominator <= 0):
        raise ValueError("mesh contains orphan nodes; nodal averaging would be undefined")
    return numerator / denominator


def _find_field(package: FEResultPackageV1, state_index: int, name: str) -> FEFieldV1:
    if state_index < 0 or state_index >= len(package.states):
        raise IndexError("state index outside result package")
    for field in package.states[state_index].fields:
        if field.name == name:
            return field
    raise KeyError(f"result field not found: {name}")


def _displacement(package: FEResultPackageV1, state_index: int) -> np.ndarray:
    field = _find_field(package, state_index, "DISPLACEMENT")
    if field.association != FieldAssociation.POINT or field.components != 3:
        raise ValueError("DISPLACEMENT must be a three-component point field")
    return np.asarray(field.values, dtype=float)


def build_ansys_style_grid(
    package: FEResultPackageV1,
    state_index: int,
    config: AnsysStyleViewConfig,
):
    """Create a VTK unstructured grid from stored FE topology and fields.

    VTK is imported lazily so the deterministic data/convergence core does not require
    a rendering stack. The returned grid contains either the raw elemental scalar or a
    separately named, volume-weighted nodal display scalar. Raw fields remain intact.
    """

    from vtkmodules.util.numpy_support import numpy_to_vtk
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import (
        VTK_QUADRATIC_TETRA,
        VTK_TETRA,
        vtkCellArray,
        vtkUnstructuredGrid,
    )

    nodes = np.asarray(package.mesh.nodes_mm, dtype=float)
    displacement = _displacement(package, state_index)
    displayed_nodes = nodes + config.deformation_scale * displacement

    points = vtkPoints()
    points.SetData(numpy_to_vtk(displayed_nodes, deep=True))
    grid = vtkUnstructuredGrid()
    grid.SetPoints(points)

    cell_type = VTK_TETRA if package.mesh.element_family == ElementFamily.TET4 else VTK_QUADRATIC_TETRA
    cells = vtkCellArray()
    for conn in package.mesh.connectivity:
        cells.InsertNextCell(len(conn), conn)
    grid.SetCells(cell_type, cells)

    disp_array = numpy_to_vtk(displacement, deep=True)
    disp_array.SetName("DISPLACEMENT")
    disp_array.SetNumberOfComponents(3)
    grid.GetPointData().AddArray(disp_array)

    source = _find_field(package, state_index, config.field_name)
    source_values = np.asarray(source.values, dtype=float)
    if source.components != 1:
        raise ValueError("ANSYS-style contour currently requires a scalar field")
    source_scalar = source_values[:, 0]

    if source.association == FieldAssociation.CELL:
        raw = numpy_to_vtk(source_scalar, deep=True)
        raw.SetName(f"{source.name}__ELEMENTAL_UNAVERAGED")
        grid.GetCellData().AddArray(raw)
        if config.stress_display_mode == StressDisplayMode.ELEMENTAL_UNAVERAGED:
            grid.GetCellData().SetActiveScalars(raw.GetName())
            active_name = raw.GetName()
            association = "CELL"
        else:
            averaged_values = volume_weighted_cell_to_point_scalar(package, source_scalar)
            averaged = numpy_to_vtk(averaged_values, deep=True)
            averaged.SetName(f"{source.name}__NODAL_AVERAGED_DISPLAY")
            grid.GetPointData().AddArray(averaged)
            grid.GetPointData().SetActiveScalars(averaged.GetName())
            active_name = averaged.GetName()
            association = "POINT"
    elif source.association == FieldAssociation.POINT:
        raw = numpy_to_vtk(source_scalar, deep=True)
        raw.SetName(source.name)
        grid.GetPointData().AddArray(raw)
        grid.GetPointData().SetActiveScalars(raw.GetName())
        active_name = raw.GetName()
        association = "POINT"
    else:  # pragma: no cover - enum boundary
        raise ValueError(f"unsupported field association: {source.association}")

    return grid, {
        "active_array": active_name,
        "association": association,
        "deformation_scale": config.deformation_scale,
        "show_mesh": config.show_mesh,
        "show_nodes": config.show_nodes,
        "show_undeformed_wireframe": config.show_undeformed_wireframe,
        "source_evidence_class": source.evidence_class.value,
        "display_is_averaged": active_name.endswith("__NODAL_AVERAGED_DISPLAY"),
        "display_note": (
            "Nodal averaged contour is deterministic display postprocessing; "
            "raw elemental values remain preserved in the same grid."
        ),
    }


def build_vtk_display_pipeline(grid, config: AnsysStyleViewConfig, active_metadata: dict):
    """Return VTK actors/mapper for a conventional FE contour, mesh overlay and clipping."""

    from vtkmodules.vtkCommonDataModel import vtkPlane
    from vtkmodules.vtkFiltersCore import vtkClipDataSet, vtkDataSetSurfaceFilter
    from vtkmodules.vtkRenderingCore import vtkActor, vtkDataSetMapper, vtkPolyDataMapper

    dataset = grid
    clip_filter = None
    if config.clip_normal is not None:
        plane = vtkPlane()
        plane.SetOrigin(*config.clip_origin_mm)
        plane.SetNormal(*config.clip_normal)
        clip_filter = vtkClipDataSet()
        clip_filter.SetInputData(grid)
        clip_filter.SetClipFunction(plane)
        clip_filter.Update()
        dataset = clip_filter.GetOutput()

    mapper = vtkDataSetMapper()
    mapper.SetInputData(dataset)
    if active_metadata["association"] == "POINT":
        mapper.SetScalarModeToUsePointFieldData()
    else:
        mapper.SetScalarModeToUseCellFieldData()
    mapper.SelectColorArray(active_metadata["active_array"])
    array = (
        dataset.GetPointData().GetArray(active_metadata["active_array"])
        if active_metadata["association"] == "POINT"
        else dataset.GetCellData().GetArray(active_metadata["active_array"])
    )
    if array is None:
        raise ValueError("active contour array disappeared from VTK dataset")
    mapper.SetScalarRange(array.GetRange())
    mapper.ScalarVisibilityOn()

    contour_actor = vtkActor()
    contour_actor.SetMapper(mapper)

    mesh_actor = None
    if config.show_mesh:
        surface = vtkDataSetSurfaceFilter()
        surface.SetInputData(dataset)
        surface.Update()
        mesh_mapper = vtkPolyDataMapper()
        mesh_mapper.SetInputConnection(surface.GetOutputPort())
        mesh_mapper.ScalarVisibilityOff()
        mesh_actor = vtkActor()
        mesh_actor.SetMapper(mesh_mapper)
        mesh_actor.GetProperty().SetRepresentationToWireframe()
        mesh_actor.GetProperty().SetLineWidth(0.7)

    return {
        "contour_actor": contour_actor,
        "mesh_actor": mesh_actor,
        "mapper": mapper,
        "clip_filter": clip_filter,
        "scalar_range": array.GetRange(),
    }
