#!/usr/bin/env python3
"""Render genuine WS01.1 AsterMax/Code_Aster VTU results to PNG evidence.

The input VTU is produced by bridge-c964-med-results.py from the real Code_Aster
MED result. This script does not synthesize FEA values.
"""
import argparse
from pathlib import Path
import vtk

FIELDS = [
    ("Total Deformation", "ws01-total-deformation.png"),
    ("Equivalent Stress", "ws01-von-mises.png"),
]

def render(grid, field_name, out_path):
    point_data = grid.GetPointData()
    arr = point_data.GetArray(field_name)
    if arr is None:
        raise RuntimeError(f"missing VTU point array: {field_name}")

    rng = arr.GetRange()
    surface = vtk.vtkDataSetSurfaceFilter()
    surface.SetInputData(grid)
    surface.Update()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(surface.GetOutputPort())
    mapper.SetScalarModeToUsePointFieldData()
    mapper.SelectColorArray(field_name)
    mapper.SetScalarRange(rng)
    mapper.ScalarVisibilityOn()

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().EdgeVisibilityOn()
    actor.GetProperty().SetLineWidth(0.4)

    scalar_bar = vtk.vtkScalarBarActor()
    scalar_bar.SetLookupTable(mapper.GetLookupTable())
    scalar_bar.SetTitle(field_name)
    scalar_bar.SetNumberOfLabels(7)

    title = vtk.vtkTextActor()
    title.SetInput(f"AsterMax WS01.1 — {field_name}\nCode_Aster result / Cap_fillets.stp")
    title.GetTextProperty().SetFontSize(22)
    title.GetTextProperty().BoldOn()
    title.SetPosition(30, 820)

    renderer = vtk.vtkRenderer()
    renderer.AddActor(actor)
    renderer.AddActor2D(scalar_bar)
    renderer.AddActor2D(title)
    renderer.SetBackground(0.96, 0.96, 0.96)

    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(1400, 900)
    window.AddRenderer(renderer)

    camera = renderer.GetActiveCamera()
    renderer.ResetCamera()
    camera.Azimuth(35)
    camera.Elevation(25)
    renderer.ResetCameraClippingRange()

    window.Render()
    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(window)
    w2i.SetInputBufferTypeToRGB()
    w2i.ReadFrontBufferOff()
    w2i.Update()

    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(out_path))
    writer.SetInputConnection(w2i.GetOutputPort())
    writer.Write()

    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError(f"render failed or PNG unexpectedly small: {out_path}")
    return {"field": field_name, "range": [float(rng[0]), float(rng[1])], "png": str(out_path)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vtu", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    reader = vtk.vtkXMLUnstructuredGridReader()
    reader.SetFileName(args.vtu)
    reader.Update()
    grid = reader.GetOutput()
    if grid is None or grid.GetNumberOfPoints() == 0 or grid.GetNumberOfCells() == 0:
        raise RuntimeError("VTU contains no mesh")

    evidence = []
    for field, name in FIELDS:
        evidence.append(render(grid, field, out / name))

    import json
    manifest = {
        "tutorial": "ANSYS Mechanical WS01.1 Mechanical Basics",
        "source": str(Path(args.vtu).name),
        "mesh_points": int(grid.GetNumberOfPoints()),
        "mesh_cells": int(grid.GetNumberOfCells()),
        "renders": evidence,
        "fea_values_invented": False,
    }
    (out / "ws01-render-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
