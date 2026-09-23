#!/usr/bin/env python3
"""Convert the native AsterMax/NetGen WS01 VOL to a Code_Aster MED mesh.

The converter is fail-closed:
- requires pure TRI6/TET10;
- reorders NetGen high-order nodes to Gmsh TET10/TRI6 convention;
- binds the exact 30 ANSYS WS01 CAD face ids to four physical groups;
- writes a Gmsh v2 mesh and lets Gmsh perform the MED serialization.

No FEA values are generated.
"""
import argparse, json, subprocess, sys
from collections import Counter
from pathlib import Path

PRESSURE={2,6,7,8,9,10,11,12,39,169,170,171,172,173,174,175,176}
COUNTER={22,66,68,70}
RECESS={35,41,43,74,75,76,77,78}
LIP={13}
SELECTED=PRESSURE|COUNTER|RECESS|LIP
if len(SELECTED)!=30:
    raise RuntimeError("WS01 exact face contract is not 30 unique faces")

ap=argparse.ArgumentParser()
ap.add_argument("--vol",required=True)
ap.add_argument("--msh",required=True)
ap.add_argument("--med",required=True)
ap.add_argument("--evidence",required=True)
a=ap.parse_args()

vol_path=Path(a.vol)
lines=[x.strip() for x in vol_path.read_text(encoding="utf-8",errors="ignore").splitlines()]

def section(*names):
    idx=None
    actual=None
    for name in names:
        try:
            idx=lines.index(name); actual=name; break
        except ValueError:
            pass
    if idx is None:
        raise RuntimeError("Missing VOL section: "+" or ".join(names))
    count=int(lines[idx+1])
    data=lines[idx+2:idx+2+count]
    if len(data)!=count:
        raise RuntimeError(f"Truncated {actual}: expected {count}, got {len(data)}")
    return data,actual

surface_lines,surface_section=section("surfaceelements","surfaceelementsuv")
volume_lines,_=section("volumeelements")
point_lines,_=section("points")

# NetGen TET10 midside order:
# (1-2),(3-1),(1-4),(2-3),(2-4),(3-4)
# Gmsh TET10 midside order:
# (1-2),(2-3),(3-1),(1-4),(2-4),(3-4)
def tet10_netgen_to_gmsh(n):
    if len(n)!=10: raise RuntimeError("Non-TET10 volume")
    return [n[0],n[1],n[2],n[3],n[4],n[7],n[5],n[6],n[8],n[9]]

# NetGen TRI6 midside order:
# (2-3),(3-1),(1-2)
# Gmsh TRI6 midside order:
# (1-2),(2-3),(3-1)
def tri6_netgen_to_gmsh(n):
    if len(n)!=6: raise RuntimeError("Non-TRI6 surface")
    return [n[0],n[1],n[2],n[5],n[3],n[4]]

points=[]
for i,line in enumerate(point_lines,1):
    t=line.split()
    if len(t)<3: raise RuntimeError(f"Malformed point {i}")
    points.append((i,float(t[0]),float(t[1]),float(t[2])))

volumes=[]
for i,line in enumerate(volume_lines,1):
    t=line.split()
    np=int(t[1])
    if np!=10: raise RuntimeError(f"Volume element {i} has {np} nodes, not TET10")
    raw=[int(x) for x in t[2:2+np]]
    volumes.append(tet10_netgen_to_gmsh(raw))

selected_surfaces=[]
seen_face_counts=Counter()
for i,line in enumerate(surface_lines,1):
    t=line.split()
    surfnr=int(t[0])
    np=int(t[4])
    if np!=6: raise RuntimeError(f"Surface element {i} has {np} nodes, not TRI6")
    if surfnr not in SELECTED:
        continue
    raw=[int(x) for x in t[5:5+np]]
    selected_surfaces.append((surfnr,tri6_netgen_to_gmsh(raw)))
    seen_face_counts[surfnr]+=1

missing=sorted(SELECTED-set(seen_face_counts))
if missing:
    raise RuntimeError("Selected WS01 faces missing from NetGen VOL: "+",".join(map(str,missing)))

def phys(face):
    if face in PRESSURE: return 101,"PRESSURE"
    if face in COUNTER: return 102,"SUPPORT_COUNTERBORE"
    if face in RECESS: return 103,"SUPPORT_RECESS"
    if face in LIP: return 104,"SUPPORT_LIP"
    raise RuntimeError(face)

msh=Path(a.msh)
msh.parent.mkdir(parents=True,exist_ok=True)
with msh.open("w",encoding="ascii",newline="\n") as f:
    f.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")
    f.write("$PhysicalNames\n5\n")
    f.write('2 101 "PRESSURE"\n')
    f.write('2 102 "SUPPORT_COUNTERBORE"\n')
    f.write('2 103 "SUPPORT_RECESS"\n')
    f.write('2 104 "SUPPORT_LIP"\n')
    f.write('3 201 "SOLID"\n')
    f.write("$EndPhysicalNames\n")
    f.write(f"$Nodes\n{len(points)}\n")
    for tag,x,y,z in points:
        f.write(f"{tag} {x:.17g} {y:.17g} {z:.17g}\n")
    f.write("$EndNodes\n")
    total=len(selected_surfaces)+len(volumes)
    f.write(f"$Elements\n{total}\n")
    eid=1
    for face,nodes in selected_surfaces:
        pg,_=phys(face)
        f.write(f"{eid} 9 2 {pg} {face} "+" ".join(map(str,nodes))+"\n")
        eid+=1
    for nodes in volumes:
        f.write(f"{eid} 11 2 201 1 "+" ".join(map(str,nodes))+"\n")
        eid+=1
    f.write("$EndElements\n")

# Convert through the installed gmsh Python module.
code=(
    "import gmsh,sys;"
    "gmsh.initialize();"
    f"gmsh.open(r'{str(msh.resolve())}');"
    f"gmsh.write(r'{str(Path(a.med).resolve())}');"
    "gmsh.finalize()"
)
subprocess.run([sys.executable,"-c",code],check=True)

evidence={
    "source_vol":str(vol_path),
    "surface_section":surface_section,
    "nodes":len(points),
    "tet10_volume_elements":len(volumes),
    "selected_tri6_surface_elements":len(selected_surfaces),
    "selected_face_ids":sorted(SELECTED),
    "selected_face_element_counts":{str(k):seen_face_counts[k] for k in sorted(SELECTED)},
    "physical_groups":{
        "PRESSURE":sorted(PRESSURE),
        "SUPPORT_COUNTERBORE":sorted(COUNTER),
        "SUPPORT_RECESS":sorted(RECESS),
        "SUPPORT_LIP":sorted(LIP),
        "SOLID":[1]
    },
    "ordering":{
        "tet10_netgen_mids":["12","31","14","23","24","34"],
        "tet10_gmsh_mids":["12","23","31","14","24","34"],
        "tri6_netgen_mids":["23","31","12"],
        "tri6_gmsh_mids":["12","23","31"]
    },
    "pure_tet10":True,
    "pure_tri6":True,
    "fea_values_invented":False
}
Path(a.evidence).write_text(json.dumps(evidence,indent=2),encoding="utf-8")
print(json.dumps({k:evidence[k] for k in ("nodes","tet10_volume_elements","selected_tri6_surface_elements","pure_tet10","pure_tri6")},indent=2))
