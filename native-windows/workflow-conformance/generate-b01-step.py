#!/usr/bin/env python3
"""Reconstruct the B01 axial bar from declared dimensions; no ANSYS geometry is copied."""
from __future__ import annotations
import argparse
from pathlib import Path
import gmsh

p = argparse.ArgumentParser()
p.add_argument("--out", required=True)
args = p.parse_args()
out = Path(args.out).resolve()
out.parent.mkdir(parents=True, exist_ok=True)

gmsh.initialize()
try:
    gmsh.model.add("B01_Axial_Bar")
    gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 10.0, 10.0)
    gmsh.model.occ.synchronize()
    gmsh.write(str(out))
finally:
    gmsh.finalize()

if not out.is_file() or out.stat().st_size < 1000:
    raise SystemExit("B01 STEP reconstruction failed")
print(f"B01_STEP={out}")
print("B01_DIMENSIONS_MM=100x10x10")
