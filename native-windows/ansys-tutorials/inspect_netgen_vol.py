#!/usr/bin/env python3
import argparse, json
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument("--vol", required=True)
p.add_argument("--out", required=True)
a=p.parse_args()
lines=[x.strip() for x in Path(a.vol).read_text(encoding="utf-8",errors="ignore").splitlines()]
def section(name):
    try:i=lines.index(name)
    except ValueError: raise SystemExit(f"Missing NetGen VOL section: {name}")
    n=int(lines[i+1])
    return lines[i+2:i+2+n]

surf=section("surfaceelements")
vols=section("volumeelements")
points=section("points")

surf_counts=[]
for line in surf:
    t=line.split()
    if len(t)<6: raise SystemExit("Malformed surface element: "+line)
    np=int(t[4])
    if len(t)<5+np: raise SystemExit("Truncated surface element")
    surf_counts.append(np)

vol_counts=[]
for line in vols:
    t=line.split()
    if len(t)<3: raise SystemExit("Malformed volume element: "+line)
    np=int(t[1])
    if len(t)<2+np: raise SystemExit("Truncated volume element")
    vol_counts.append(np)

report={
  "source":"NetGenMesher.exe / BREP_MESH",
  "nodes":len(points),
  "surface_elements":len(surf),
  "volume_elements":len(vols),
  "surface_node_counts":sorted(set(surf_counts)),
  "volume_node_counts":sorted(set(vol_counts)),
  "pure_tri6":set(surf_counts)=={6},
  "pure_tet10":set(vol_counts)=={10},
  "quadratic_pass":set(surf_counts)=={6} and set(vol_counts)=={10},
  "synthetic":False
}
Path(a.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))
if not report["quadratic_pass"]:
    raise SystemExit(4)
