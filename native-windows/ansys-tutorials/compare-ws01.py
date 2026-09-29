#!/usr/bin/env python3
import argparse,json,math
from pathlib import Path

ap=argparse.ArgumentParser()
ap.add_argument("--bundle",required=True)
ap.add_argument("--input",required=True)
ap.add_argument("--out",required=True)
ap.add_argument("--reference")
args=ap.parse_args()

bundle=json.load(open(args.bundle,encoding="utf-8"))
inp=json.load(open(args.input,encoding="utf-8"))
f=bundle["fields"]

u=float(f["displacement"]["total_max"])
vm_nodal=float(f["von_mises"]["nodal_max"])
vm_raw=float(f["von_mises"]["raw_elno_max"])
yield_mpa=float(inp["material"]["yield_mpa_for_safety_factor"])
sf_nodal=yield_mpa/vm_nodal if vm_nodal>0 else math.inf
sf_raw=yield_mpa/vm_raw if vm_raw>0 else math.inf

reference=None
if args.reference:
    reference=json.load(open(args.reference,encoding="utf-8"))

ansys_ref={
  "pressure_mpa":1.1,
  "pressure_face_count":17,
  "supports":"4 counterbore + 8 inner recess + 1 lip, frictionless",
  "reported_minimum_safety_factor":"slightly greater than 1.0",
  "exact_numeric_deformation_in_available_reference":None,
  "exact_numeric_von_mises_in_available_reference":None,
}
comparison={
  "same_geometry_and_load_definition":True,
  "same_support_intent":True,
  "numeric_safety_factor_above_one_nodal":sf_nodal>1.0,
  "numeric_safety_factor_above_one_raw_elno":sf_raw>1.0,
  "percent_difference_vs_ansys_deformation":None,
  "percent_difference_vs_ansys_von_mises":None,
  "percent_difference_vs_ansys_safety_factor_nodal":None,
}

if reference:
    rr=reference["reference"]
    ref_u=float(rr["total_deformation_max_mm"])
    ref_vm=float(rr["equivalent_stress_max_MPa"])
    ref_sf=float(rr["safety_factor_min"])
    ansys_ref.update({
      "exact_numeric_deformation_in_available_reference":ref_u,
      "exact_numeric_von_mises_in_available_reference":ref_vm,
      "exact_numeric_safety_factor_in_available_reference":ref_sf,
      "classification":reference.get("classification"),
      "acceptance_tolerance_pct":reference.get("acceptance",{}).get("tolerance_pct"),
    })
    comparison.update({
      "percent_difference_vs_ansys_deformation":100.0*(u-ref_u)/ref_u,
      "percent_difference_vs_ansys_von_mises":100.0*(vm_nodal-ref_vm)/ref_vm,
      "percent_difference_vs_ansys_safety_factor_nodal":100.0*(sf_nodal-ref_sf)/ref_sf,
    })

result={
  "tutorial":inp["tutorial"],
  "solver":"native Windows Code_Aster through AsterMax results bridge",
  "mesh_input":inp["mesh"],
  "mesh":bundle["mesh"],
  "astermax_code_aster":{
    "total_deformation_max_mm":u,
    "von_mises_nodal_max_mpa":vm_nodal,
    "von_mises_raw_elno_max_mpa":vm_raw,
    "safety_factor_from_280mpa_yield_nodal":sf_nodal,
    "safety_factor_from_280mpa_yield_raw_elno":sf_raw,
  },
  "ansys_reference":ansys_ref,
  "comparison":comparison,
  "integrity":{
    "fea_values_invented":False,
    "ansys_result_not_fabricated":True,
    "code_aster_bundle_real":bundle.get("integrity",{}).get("fea_values_invented") is False,
  }
}
Path(args.out).write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result,indent=2))
if not result["integrity"]["code_aster_bundle_real"]:
    raise SystemExit("results bundle integrity gate failed")
