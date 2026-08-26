import numpy as np
import pytest
import vtk
from vtk.util.numpy_support import numpy_to_vtk

from astermax.ui.ansys_post import StressDisplayMode
from astermax.ui.result_scene import ResultSceneController, ResultSceneState


def result_grid():
    points = vtk.vtkPoints()
    for xyz in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)):
        points.InsertNextPoint(*xyz)
    tet = vtk.vtkTetra()
    for index in range(4):
        tet.GetPointIds().SetId(index, index)
    cells = vtk.vtkCellArray()
    cells.InsertNextCell(tet)
    grid = vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    grid.SetCells(vtk.VTK_TETRA, cells)

    raw = numpy_to_vtk(np.array([120.0]), deep=True)
    raw.SetName("S_VM_RAW")
    grid.GetCellData().AddArray(raw)

    displacement = numpy_to_vtk(
        np.array([[0, 0, 0], [0.01, 0, 0], [0, 0.02, 0], [0, 0, 0.03]]),
        deep=True,
    )
    displacement.SetNumberOfComponents(3)
    displacement.SetName("U")
    grid.GetPointData().AddArray(displacement)
    return grid


def test_scene_can_show_elemental_unaveraged_with_mesh():
    renderer = vtk.vtkRenderer()
    scene = ResultSceneController(renderer)
    evidence = scene.apply(
        result_grid(),
        ResultSceneState(
            field_array_name="S_VM_RAW",
            field_association="CELL",
            display_mode=StressDisplayMode.ELEMENTAL_UNAVERAGED,
            show_mesh=True,
            legend_title="Equivalent Stress",
            unit="MPa",
        ),
    )
    assert evidence.minimum == pytest.approx(120.0)
    assert evidence.maximum == pytest.approx(120.0)
    assert evidence.display_mode == "ELEMENTAL_UNAVERAGED"
    assert evidence.show_mesh is True
    assert renderer.GetActors().GetNumberOfItems() == 1


def test_scene_nodal_averaging_is_explicit_display_mode():
    renderer = vtk.vtkRenderer()
    scene = ResultSceneController(renderer)
    evidence = scene.apply(
        result_grid(),
        ResultSceneState(
            field_array_name="S_VM_RAW",
            field_association="CELL",
            display_mode=StressDisplayMode.NODAL_AVERAGED,
            show_mesh=False,
            legend_title="Equivalent Stress",
            unit="MPa",
        ),
    )
    assert evidence.display_mode == "NODAL_AVERAGED"
    assert evidence.p99 == pytest.approx(120.0)


def test_deformed_scene_requires_real_vector_field():
    renderer = vtk.vtkRenderer()
    scene = ResultSceneController(renderer)
    with pytest.raises(ValueError, match="displacement array name"):
        scene.apply(
            result_grid(),
            ResultSceneState(
                field_array_name="S_VM_RAW",
                field_association="CELL",
                display_mode=StressDisplayMode.ELEMENTAL_UNAVERAGED,
                deformation_scale=50.0,
            ),
        )


def test_scene_supports_deformed_plus_undeformed_overlay():
    renderer = vtk.vtkRenderer()
    scene = ResultSceneController(renderer)
    evidence = scene.apply(
        result_grid(),
        ResultSceneState(
            field_array_name="S_VM_RAW",
            field_association="CELL",
            display_mode=StressDisplayMode.ELEMENTAL_UNAVERAGED,
            deformation_scale=50.0,
            displacement_array_name="U",
            show_undeformed=True,
        ),
    )
    assert evidence.deformation_scale == pytest.approx(50.0)
    assert renderer.GetActors().GetNumberOfItems() == 2


def test_section_state_is_applied_to_real_grid():
    renderer = vtk.vtkRenderer()
    scene = ResultSceneController(renderer)
    evidence = scene.apply(
        result_grid(),
        ResultSceneState(
            field_array_name="S_VM_RAW",
            field_association="CELL",
            display_mode=StressDisplayMode.ELEMENTAL_UNAVERAGED,
            section_enabled=True,
            section_origin=(0.2, 0.0, 0.0),
            section_normal=(1.0, 0.0, 0.0),
        ),
    )
    assert evidence.section_enabled is True


def test_nodal_average_rejects_point_field_as_source():
    renderer = vtk.vtkRenderer()
    scene = ResultSceneController(renderer)
    with pytest.raises(ValueError, match="only valid for a cell"):
        scene.apply(
            result_grid(),
            ResultSceneState(
                field_array_name="U",
                field_association="POINT",
                display_mode=StressDisplayMode.NODAL_AVERAGED,
            ),
        )
