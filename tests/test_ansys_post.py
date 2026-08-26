import numpy as np
import pytest
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

from astermax.ui.ansys_post import (
    AnsysStyleField,
    StressDisplayMode,
    build_result_actor,
    clipped_grid,
    deformed_grid,
    extrema_probe,
    field_statistics,
    nodal_average_from_cell_field,
)


def one_tet_grid():
    points = vtk.vtkPoints()
    for xyz in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)):
        points.InsertNextPoint(*xyz)
    tet = vtk.vtkTetra()
    for i in range(4):
        tet.GetPointIds().SetId(i, i)
    cells = vtk.vtkCellArray()
    cells.InsertNextCell(tet)
    grid = vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    grid.SetCells(vtk.VTK_TETRA, cells)

    vm = numpy_to_vtk(np.array([123.0]), deep=True)
    vm.SetName("S_VM_RAW")
    grid.GetCellData().AddArray(vm)

    disp = numpy_to_vtk(
        np.array([[0, 0, 0], [0.1, 0, 0], [0, 0.2, 0], [0, 0, 0.3]]),
        deep=True,
    )
    disp.SetNumberOfComponents(3)
    disp.SetName("U")
    grid.GetPointData().AddArray(disp)
    return grid


def test_deformed_grid_uses_real_displacement_vector_and_scale():
    grid = one_tet_grid()
    moved = deformed_grid(grid, "U", 10.0)
    assert moved.GetPoint(1) == pytest.approx((2.0, 0.0, 0.0))
    assert moved.GetPoint(2) == pytest.approx((0.0, 3.0, 0.0))
    assert moved.GetPoint(3) == pytest.approx((0.0, 0.0, 4.0))


def test_nodal_average_preserves_raw_cell_field_and_creates_point_field():
    grid = one_tet_grid()
    averaged = nodal_average_from_cell_field(grid, "S_VM_RAW", "S_VM_NODAL_AVG")
    assert averaged.GetCellData().GetArray("S_VM_RAW") is not None
    arr = averaged.GetPointData().GetArray("S_VM_NODAL_AVG")
    assert arr is not None
    assert vtk_to_numpy(arr).tolist() == pytest.approx([123.0] * 4)


def test_statistics_and_extrema_are_deterministic():
    grid = one_tet_grid()
    stats = field_statistics(grid, "S_VM_RAW", "CELL")
    assert stats.minimum == pytest.approx(123.0)
    assert stats.p99 == pytest.approx(123.0)
    probe = extrema_probe(grid, "S_VM_RAW", "CELL", maximum=True)
    assert probe.value == pytest.approx(123.0)
    assert probe.point_xyz == pytest.approx((0.25, 0.25, 0.25))


def test_ansys_style_actor_uses_mesh_overlay_without_changing_values():
    grid = one_tet_grid()
    actor, mapper, stats = build_result_actor(
        grid,
        AnsysStyleField(
            array_name="S_VM_RAW",
            association="CELL",
            legend_title="Equivalent Stress",
            unit="MPa",
            display_mode=StressDisplayMode.ELEMENTAL_UNAVERAGED,
        ),
        show_mesh=True,
    )
    assert actor.GetProperty().GetEdgeVisibility() == 1
    assert mapper.GetScalarRange() == pytest.approx((123.0, 123.0))
    assert stats.maximum == pytest.approx(123.0)


def test_section_plane_reduces_or_keeps_valid_unstructured_grid():
    grid = one_tet_grid()
    clipped = clipped_grid(grid, (0.2, 0, 0), (1, 0, 0))
    assert clipped.GetNumberOfPoints() > 0
    assert clipped.GetNumberOfCells() > 0
