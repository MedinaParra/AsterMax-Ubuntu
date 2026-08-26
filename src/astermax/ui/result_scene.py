from __future__ import annotations

from dataclasses import dataclass

from vtkmodules.vtkFiltersCore import vtkFeatureEdges
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.vtkRenderingCore import vtkActor, vtkDataSetMapper, vtkRenderer

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


@dataclass(frozen=True)
class ResultSceneState:
    field_array_name: str
    field_association: str
    display_mode: StressDisplayMode
    show_mesh: bool = True
    show_undeformed: bool = False
    deformation_scale: float = 0.0
    displacement_array_name: str | None = None
    section_enabled: bool = False
    section_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    section_normal: tuple[float, float, float] = (1.0, 0.0, 0.0)
    unit: str | None = None
    legend_title: str = "Result"


@dataclass(frozen=True)
class SceneEvidence:
    minimum: float
    maximum: float
    p95: float
    p99: float
    min_location: tuple[float, float, float]
    max_location: tuple[float, float, float]
    deformation_scale: float
    display_mode: str
    section_enabled: bool
    show_mesh: bool


class ResultSceneController:
    """Build an ANSYS-style VTK scene without changing underlying result evidence.

    The controller is deliberately presentation-only. Raw elemental data remains in the
    validated grid. Nodal averaging is created only when explicitly requested and is
    therefore a display field, never a replacement for solver-authored values.
    """

    def __init__(self, renderer: vtkRenderer) -> None:
        self.renderer = renderer
        self._scalar_bar: vtkScalarBarActor | None = None
        self._result_actor: vtkActor | None = None
        self._undeformed_actor: vtkActor | None = None

    def clear(self) -> None:
        self.renderer.RemoveAllViewProps()
        self._scalar_bar = None
        self._result_actor = None
        self._undeformed_actor = None

    def apply(self, grid, state: ResultSceneState) -> SceneEvidence:
        if state.deformation_scale < 0:
            raise ValueError("deformation scale cannot be negative")

        source_grid = grid
        array_name = state.field_array_name
        association = state.field_association

        if state.display_mode == StressDisplayMode.NODAL_AVERAGED:
            if association != "CELL":
                raise ValueError("nodal averaging is only valid for a cell result field")
            averaged_name = f"{array_name}__NODAL_AVERAGED_DISPLAY"
            source_grid = nodal_average_from_cell_field(source_grid, array_name, averaged_name)
            array_name = averaged_name
            association = "POINT"

        undeformed_grid = source_grid
        display_grid = source_grid
        if state.deformation_scale > 0:
            if not state.displacement_array_name:
                raise ValueError("deformed display requires a displacement array name")
            display_grid = deformed_grid(
                display_grid,
                state.displacement_array_name,
                state.deformation_scale,
            )

        if state.section_enabled:
            display_grid = clipped_grid(
                display_grid,
                state.section_origin,
                state.section_normal,
            )
            if state.show_undeformed:
                undeformed_grid = clipped_grid(
                    undeformed_grid,
                    state.section_origin,
                    state.section_normal,
                )

        stats = field_statistics(display_grid, array_name, association)
        field = AnsysStyleField(
            array_name=array_name,
            association=association,
            legend_title=state.legend_title,
            unit=state.unit,
            display_mode=state.display_mode,
        )
        actor, _, _ = build_result_actor(
            display_grid,
            field,
            show_mesh=state.show_mesh,
        )

        self.clear()
        self._result_actor = actor
        self.renderer.AddActor(actor)

        if state.show_undeformed and state.deformation_scale > 0:
            mapper = vtkDataSetMapper()
            mapper.SetInputData(undeformed_grid)
            mapper.ScalarVisibilityOff()
            overlay = vtkActor()
            overlay.SetMapper(mapper)
            overlay.GetProperty().SetRepresentationToWireframe()
            overlay.GetProperty().SetColor(0.20, 0.20, 0.20)
            overlay.GetProperty().SetOpacity(0.35)
            overlay.GetProperty().SetLineWidth(0.7)
            self._undeformed_actor = overlay
            self.renderer.AddActor(overlay)

        scalar_bar = vtkScalarBarActor()
        scalar_bar.SetLookupTable(actor.GetMapper().GetLookupTable())
        unit = f" [{state.unit}]" if state.unit else ""
        scalar_bar.SetTitle(f"{state.legend_title}{unit}")
        scalar_bar.SetNumberOfLabels(6)
        self._scalar_bar = scalar_bar
        self.renderer.AddActor2D(scalar_bar)

        minimum = extrema_probe(display_grid, array_name, association, maximum=False)
        maximum = extrema_probe(display_grid, array_name, association, maximum=True)
        self.renderer.ResetCameraClippingRange()

        return SceneEvidence(
            minimum=stats.minimum,
            maximum=stats.maximum,
            p95=stats.p95,
            p99=stats.p99,
            min_location=minimum.point_xyz,
            max_location=maximum.point_xyz,
            deformation_scale=state.deformation_scale,
            display_mode=state.display_mode.value,
            section_enabled=state.section_enabled,
            show_mesh=state.show_mesh,
        )
