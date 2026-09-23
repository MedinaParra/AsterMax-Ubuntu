#!/usr/bin/env python3
import argparse, json, math, os

p=argparse.ArgumentParser()
p.add_argument("--bundle", required=True)
p.add_argument("--model-evidence", required=True)
p.add_argument("--out", required=True)
a=p.parse_args()

with open(a.bundle,encoding="utf-8") as f: result=json.load(f)
with open(a.model_evidence,encoding="utf-8") as f: model=json.load(f)

disp=float(result["fields"]["displacement"]["total_max"])
vm_nodal=float(result["fields"]["von_mises"]["nodal_max"])
vm_raw=float(result["fields"]["von_mises"]["raw_elno_max"])
yield_mpa=float(model["material"]["yield_MPa"])
sf_nodal=yield_mpa/vm_nodal if vm_nodal>0 else math.inf
sf_raw=yield_mpa/vm_raw if vm_raw>0 else math.inf

report={
  "case":"ANSYS Mechanical WS01.1 Mechanical Basics",
  "comparison_basis":{
    "geometry":"exact Cap_fillets.stp",
    "load":"1.1 MPa on 17 exterior surfaces",
    "material":"Aluminum Alloy, E=71000 MPa, nu=0.33, tensile yield=280 MPa",
    "supports":"frictionless normal constraints on 4 counterbores + 8 recess faces + 1 lip face",
    "ansys_documented_numeric_reference":{
      "minimum_safety_factor":"slightly greater than 1.0",
      "total_deformation_mm":None,
      "equivalent_stress_mpa":None
    },
    "mesh_note":"ANSYS workshop baseline does not publish a numeric mesh size; AsterMax uses the declared mesh size from model evidence."
  },
  "astermax_code_aster":{
    "total_deformation_max_mm":disp,
    "von_mises_nodal_averaged_max_mpa":vm_nodal,
    "von_mises_raw_elno_max_mpa":vm_raw,
    "safety_factor_from_nodal_vm":sf_nodal,
    "safety_factor_from_raw_elno_vm":sf_raw,
    "mesh":model["mesh"],
    "integrity":result.get("integrity",{})
  },
  "comparison":{
    "safety_factor_directionally_consistent_with_ansys":sf_nodal>1.0,
    "numeric_deformation_difference_pct":None,
    "numeric_stress_difference_pct":None,
    "reason_numeric_difference_unavailable":"The supplied/public workshop states safety factor qualitatively but does not publish baseline deformation or stress maxima.",
  },
  "pass_integrity":(
      model.get("fea_values_invented") is False and
      result.get("integrity",{}).get("fea_values_invented") is False and
      result.get("integrity",{}).get("solver_output_modified") is False and
      math.isfinite(disp) and disp>=0 and math.isfinite(vm_nodal) and vm_nodal>0
  )
}

os.makedirs(os.path.dirname(os.path.abspath(a.out)),exist_ok=True)
with open(a.out,"w",encoding="utf-8") as f: json.dump(report,f,indent=2)
print(json.dumps(report,indent=2))
if not report["pass_integrity"]:
    raise SystemExit("WS01.1 integrity comparison failed")
