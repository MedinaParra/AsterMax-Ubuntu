#!/usr/bin/env python3
import argparse, json
from pathlib import Path

ap=argparse.ArgumentParser()
ap.add_argument("--root",required=True)
ap.add_argument("--out",required=True)
args=ap.parse_args()

root=Path(args.root)
rows=[]
for label in ("3mm","2mm","1mm"):
    p=root/f"mesh-{label}"/"ws01-comparison.json"
    if not p.exists():
        rows.append({"mesh":label,"state":"MISSING"})
        continue
    d=json.loads(p.read_text(encoding="utf-8"))
    a=d["astermax_code_aster"]
    c=d["comparison"]
    rows.append({
        "mesh":label,
        "state":"SOLVED",
        "nodes":d["mesh"]["node_count"],
        "elements":d["mesh"]["element_count"],
        "element_type":d["mesh"]["element_type"],
        "total_deformation_max_mm":a["total_deformation_max_mm"],
        "von_mises_nodal_max_mpa":a["von_mises_nodal_max_mpa"],
        "von_mises_raw_elno_max_mpa":a["von_mises_raw_elno_max_mpa"],
        "safety_factor_nodal":a["safety_factor_from_280mpa_yield_nodal"],
        "u_error_pct":c["percent_difference_vs_ansys_deformation"],
        "vm_error_pct":c["percent_difference_vs_ansys_von_mises"],
        "sf_error_pct":c["percent_difference_vs_ansys_safety_factor_nodal"],
    })

solved=[r for r in rows if r["state"]=="SOLVED"]
for i in range(1,len(solved)):
    prev,cur=solved[i-1],solved[i]
    for key,outkey in [
        ("total_deformation_max_mm","u_change_vs_previous_pct"),
        ("von_mises_nodal_max_mpa","vm_change_vs_previous_pct"),
    ]:
        base=prev[key]
        cur[outkey]=100.0*(cur[key]-base)/base if base else None

summary={
    "tutorial":"ANSYS Mechanical WS01.1 Mechanical Basics",
    "study":"TETRA10 mesh convergence",
    "reference":{
        "equivalent_stress_max_MPa":235.96,
        "total_deformation_max_mm":0.064809,
        "safety_factor_min":1.1866,
        "classification":"PRE_REFINEMENT_TUTORIAL_SNAPSHOT"
    },
    "rows":rows,
    "integrity":{"fea_values_invented":False}
}
Path(args.out).write_text(json.dumps(summary,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
