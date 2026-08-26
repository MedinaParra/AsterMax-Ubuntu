from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkCommonDataModel import vtkPlane, vtkUnstructuredGrid
from vtkmodules.vtkFiltersCore import vtkCellCenters, vtkCellDataToPointData
from vtkmodules.vtkFiltersGeneral import vtkClipDataSet
from vtkmodules.vtkRenderingCore import vtkActor, vtkDataSetMapper


class StressDisplayMode(StrEnum):
    ELEMENTAL_UNAVERAGED = "ELEMENTAL_UNAVERAGED"
    NODAL_AVERAGED = "NODAL_AVERAGED"


@dataclass(frozen=True)
class FieldStatistics:
    minimum: float
    maximum: float
    p95: float
    p99: float


@dataclass(frozen=True)
class ProbeLocation:
    point_xyz: tuple[float, float, float]
    value: float
    source_index: int


@dataclass(frozen=True)
class AnsysStyleField:
    array_name: str
    association: str
    legend_title: str
    unit: str | None
    display_mode: StressDisplayMode


def _array_values(grid, array_name: str, association: str) -> np.ndarray:
    if association == "POINT":
        array = grid.GetPointData().GetArray(array_name)
    elif association == "CELL":
        array = grid.GetCellData().GetArray(array_name)
    else:
        raise ValueError(f"unsupported result association: {association}")
    if array is None:
        raise ValueError(f"result array not found: {array_name}")
    if array.GetNumberOfComponents() != 1:
        raise ValueError(f"result array must be scalar: {array_name}")
    values = np.asarray(vtk_to_numpy(array), dtype=float)
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError(f"result array is empty or non-finite: {array_name}")
    return values


def field_statistics(grid, array_name: str, association: str) -> FieldStatistics:
    values = _array_values(grid, array_name, association)
    return FieldStatistics(
        minimum=float(np.min(values)),
        maximum=float(np.max(values)),
        p95=float(np.percentile(values, 95.0)),
        p99=float(np.percentile(values, 99.0)),
    )


def extrema_probe(grid, array_name: str, association: str, *, maximum: bool) -> ProbeLocation:
    values = _array_values(grid, array_name, association)
    index = int(np.argmax(values) if maximum else np.argmin(values))
    if association == "POINT":
        xyz = tuple(float(value) for value in grid.GetPoint(index))
    else:
        centers = vtkCellCenters()
        centers.SetInputData(grid)
        centers.Update()
        xyz = tuple(float(value) for value in centers.GetOutput().GetPoint(index))
    return ProbeLocation(point_xyz=xyz, value=float(values[index]), source_index=index)


def nodal_average_from_cell_field(
    grid: vtkUnstructuredGrid,
    source_array_name: str,
    target_array_name: str,
) -> vtkUnstructuredGrid:
    if grid.GetCellData().GetArray(source_array_name) is None:
        raise ValueError(f"cell result array not found: {source_array_name}")
    converter = vtkCellDataToPointData()
    converter.SetInputData(grid)
    converter.PassCellDataOn()
    converter.Update()
    output = vtkUnstructuredGrid()
    output.DeepCopy(converter.GetOutput())
    array = output.GetPointData().GetArray(source_array_name)
    if array is None:
        raise ValueError("VTK failed to produce nodal-averaged result field")
    array.SetName(target_array_name)
    return output


def deformed_grid(
    grid: vtkUnstructuredGrid,
    displacement_array_name: str,
    scale_factor: float,
) -> vtkUnstructuredGrid:
    if not np.isfinite(scale_factor) or scale_factor < 0:
        raise ValueError("deformation scale factor must be finite and non-negative")
    displacement = grid.GetPointData().GetArray(displacement_array_name)
    if displacement is None or displacement.GetNumberOfComponents() != 3:
        raise ValueError("deformation requires a three-component point displacement array")
    disp = np.asarray(vtk_to_numpy(displacement), dtype=float)
    points = np.array([grid.GetPoint(i) for i in range(grid.GetNumberOfPoints())], dtype=float)
    if disp.shape != points.shape or not np.all(np.isfinite(disp)):
        raise ValueError("displacement array shape does not match mesh points")
    output = vtkUnstructuredGrid()
    output.DeepCopy(grid)
    new_points = output.GetPoints()
    moved = points + scale_factor * disp
    for index, xyz in enumerate(moved):
        new_points.SetPoint(index, *(float(value) for value in xyz))
    new_points.Modified()
    output.Modified()
    return output


def clipped_grid(
    grid: vtkUnstructuredGrid,
    origin_xyz: tuple[float, float, float],
    normal_xyz: tuple[float, float, float],
    *,
    inside_out: bool = False,
) -> vtkUnstructuredGrid:
    normal = np.asarray(normal_xyz, dtype=float)
    if normal.shape != (3,) or not np.all(np.isfinite(normal)) or np.linalg.norm(normal) <= 0:
        raise ValueError("section normal must be a finite non-zero vector")
    plane = vtkPlane()
    plane.SetOrigin(*(float(value) for value in origin_xyz))
    plane.SetNormal(*(float(value) for value in normal / np.linalg.norm(normal)))
    clipper = vtkClipDataSet()
    clipper.SetInputData(grid)
    clipper.SetClipFunction(plane)
    clipper.SetInsideOut(bool(inside_out))
    clipper.Update()
    output = vtkUnstructuredGrid()
    output.DeepCopy(clipper.GetOutput())
    return output


def build_result_actor(
    grid: vtkUnstructuredGrid,
    field: AnsysStyleField,
    *,
    show_mesh: bool = False,
) -> tuple[vtkActor, vtkDataSetMapper, FieldStatistics]:
    stats = field_statistics(grid, field.array_name, field.association)
    mapper = vtkDataSetMapper()
    mapper.SetInputData(grid)
    if field.association == "POINT":
        mapper.SetScalarModeToUsePointFieldData()
    elif field.association == "CELL":
        mapper.SetScalarModeToUseCellFieldData()
    else:
        raise ValueError(f"unsupported association: {field.association}")
    mapper.SelectColorArray(field.array_name)
    mapper.SetScalarRange(stats.minimum, stats.maximum)
    mapper.ScalarVisibilityOn()

    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetInterpolationToPhong()
    if show_mesh:
        actor.GetProperty().EdgeVisibilityOn()
        actor.GetProperty().SetEdgeColor(0.08, 0.08, 0.08)
        actor.GetProperty().SetLineWidth(0.7)
    return actor, mapper, stats
