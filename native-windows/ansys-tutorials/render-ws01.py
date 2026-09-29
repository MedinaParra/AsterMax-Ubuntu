#!/usr/bin/env python3
"""Headless renderer for genuine WS01.1 AsterMax/Code_Aster VTU results.

Reads the real VTU produced from Code_Aster MED and renders a sampled external
surface with Matplotlib/Agg. No FEA values are synthesized and no OpenGL context
is required on CI runners.
"""
import argparse, json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm, colors
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy

FIELDS = [
    ("Total Deformation", "ws01-total-deformation.png", "mm"),
    ("Equivalent Stress", "ws01-von-mises.png", "MPa"),
]

MAX_TRIANGLES = 70000

def surface_triangles(grid, field_name):
    surface = vtk.vtkDataSetSurfaceFilter()
    surface.SetInputData(grid)
    surface.Update()

    tri = vtk.vtkTriangleFilter()
    tri.SetInputConnection(surface.GetOutputPort())
    tri.Update()
    poly = tri.GetOutput()

    points = vtk_to_numpy(poly.GetPoints().GetData()).astype(float, copy=False)
    arr = poly.GetPointData().GetArray(field_name)
    if arr is None:
        raise RuntimeError(f"missing VTU point array: {field_name}")
    values = vtk_to_numpy(arr).astype(float, copy=False).reshape(-1)

    raw = vtk_to_numpy(poly.GetPolys().GetData()).astype(np.int64, copy=False)
    if raw.size % 4:
        raise RuntimeError("triangulated surface connectivity is malformed")
    cells = raw.reshape(-1, 4)
    if not np.all(cells[:, 0] == 3):
        raise RuntimeError("surface triangulation contains non-triangles")
    triangles = cells[:, 1:4]

    original_count = len(triangles)
    if original_count > MAX_TRIANGLES:
        idx = np.linspace(0, original_count - 1, MAX_TRIANGLES, dtype=np.int64)
        triangles = triangles[idx]

    return points, triangles, values, original_count

def render(grid, field_name, out_path, unit):
    points, triangles, values, original_triangles = surface_triangles(grid, field_name)
    finite = np.isfinite(values)
    if not finite.all():
        raise RuntimeError(f"{field_name}: non-finite values in genuine VTU field")

    vmin = float(values.min())
    vmax = float(values.max())
    face_values = values[triangles].mean(axis=1)

    norm = colors.Normalize(vmin=vmin, vmax=vmax if vmax > vmin else vmin + 1.0)
    cmap = cm.get_cmap("viridis")

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")
    verts = points[triangles]
    coll = Poly3DCollection(
        verts,
        facecolors=cmap(norm(face_values)),
        linewidths=0.02,
        edgecolors="none",
        antialiased=False,
    )
    ax.add_collection3d(coll)

    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    ctr = (mins + maxs) / 2.0
    spans = np.maximum(maxs - mins, 1e-9)
    radius = float(spans.max()) / 2.0
    ax.set_xlim(ctr[0]-radius, ctr[0]+radius)
    ax.set_ylim(ctr[1]-radius, ctr[1]+radius)
    ax.set_zlim(ctr[2]-radius, ctr[2]+radius)
    try:
        ax.set_box_aspect((spans[0], spans[1], spans[2]))
    except Exception:
        pass
    ax.view_init(elev=25, azim=-55)
    ax.set_axis_off()
    ax.set_title(
        f"AsterMax / Code_Aster — WS01.1\n"
        f"{field_name} max = {vmax:.6g} {unit}",
        pad=18,
    )

    sm = cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, shrink=0.72, pad=0.03)
    cb.set_label(f"{field_name} [{unit}]")

    fig.text(
        0.01, 0.01,
        f"Real VTU surface; displayed triangles: {len(triangles):,} / {original_triangles:,}",
        fontsize=8,
    )
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError(f"render failed or PNG unexpectedly small: {out_path}")

    return {
        "field": field_name,
        "range": [vmin, vmax],
        "png": str(out_path),
        "surface_triangles_total": int(original_triangles),
        "surface_triangles_rendered": int(len(triangles)),
        "fea_values_invented": False,
    }

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
    for field, name, unit in FIELDS:
        evidence.append(render(grid, field, out / name, unit))

    manifest = {
        "tutorial": "ANSYS Mechanical WS01.1 Mechanical Basics",
        "source": str(Path(args.vtu).name),
        "renderer": "matplotlib-agg-headless",
        "mesh_points": int(grid.GetNumberOfPoints()),
        "mesh_cells": int(grid.GetNumberOfCells()),
        "renders": evidence,
        "fea_values_invented": False,
    }
    (out / "ws01-render-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
