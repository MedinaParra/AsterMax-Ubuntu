#!/usr/bin/env python3
import argparse, json, math, os

p=argparse.ArgumentParser()
p.add_argument("--bundle", required=True)
p.add_argument("--model-evidence", required=True)
p.add_argument("--out", required=True)
a=p.parse_args()

with open(a.bundle,encoding="utf-8") as f: result=json.load(f)
with open(a.model_evidence,encoding="utf-8") as f: model=json.load(f)

ANSYS_VM=235.96
ANSYS_U=0.064809
ANSYS_SF=1.1866
TOL_PCT=5.0

def vmises(sx,sy,sz,txy,tyz,txz):
    return math.sqrt(max(0.0,0.5*((sx-sy)**2+(sy-sz)**2+(sz-sx)**2)+3.0*(txy*txy+tyz*tyz+txz*txz)))

disp=float(result["fields"]["displacement"]["total_max"])
vm_scalar_nodal=float(result["fields"]["von_mises"]["nodal_max"])
vm_raw=float(result["fields"]["von_mises"]["raw_elno_max"])

stress=result.get("arrays",{}).get("stress",{})
need=("SIXX","SIYY","SIZZ","SIXY","SIYZ","SIXZ")
missing=[k for k in need if k not in stress]
if missing:
    raise SystemExit("Missing averaged stress components for ANSYS-parity von Mises: "+",".join(missing))
n=len(stress["SIXX"])
if any(len(stress[k])!=n for k in need):
    raise SystemExit("Stress component arrays have inconsistent lengths")

vm_component_first=[]
for i in range(n):
    vm_component_first.append(vmises(*(float(stress[k][i]) for k in need)))

# ANSYS Mechanical higher-order-element parity:
# solver stress data are fundamentally corner-node data; Mechanical derives
# midside stresses from averaged corner values. Therefore a directly supplied
# Code_Aster midside-node SIGM_ELNO value must not decide the benchmark maximum.
# TET10 connectivity stores the four corner nodes first.
connectivity=result.get("arrays",{}).get("connectivity",[])
corner_node_ids=set()
for element in connectivity:
    if len(element) != 10:
        raise SystemExit("ANSYS WS01 parity requires pure TET10 connectivity")
    corner_node_ids.update(int(x) for x in element[:4])
if not corner_node_ids:
    raise SystemExit("No TET10 corner nodes found")

corner_pairs=[(vm_component_first[node_id-1], node_id) for node_id in corner_node_ids]
vm_ansys_parity,vm_ansys_node=max(corner_pairs)
vm_all_nodes=max(vm_component_first)
vm_all_node=vm_component_first.index(vm_all_nodes)+1

yield_mpa=float(model["material"]["yield_MPa"])
sf_parity=yield_mpa/vm_ansys_parity if vm_ansys_parity>0 else math.inf
sf_scalar=yield_mpa/vm_scalar_nodal if vm_scalar_nodal>0 else math.inf
sf_raw=yield_mpa/vm_raw if vm_raw>0 else math.inf

vm_error=100.0*(vm_ansys_parity-ANSYS_VM)/ANSYS_VM
u_error=100.0*(disp-ANSYS_U)/ANSYS_U
sf_error=100.0*(sf_parity-ANSYS_SF)/ANSYS_SF

report={
  "case":"ANSYS Mechanical WS01.1 Mechanical Basics",
  "comparison_basis":{
    "geometry":"exact Cap_fillets.stp",
    "load":"1.1 MPa on 17 exterior surfaces",
    "material":"Aluminum Alloy, E=71000 MPa, nu=0.33, tensile yield=280 MPa",
    "supports":"frictionless normal constraints on 4 counterbores + 8 recess faces + 1 lip face",
    "ansys_reference_classification":"PRE_REFINEMENT_TUTORIAL_SNAPSHOT",
    "ansys_documented_numeric_reference":{
      "equivalent_stress_max_mpa":ANSYS_VM,
      "total_deformation_max_mm":ANSYS_U,
      "minimum_safety_factor":ANSYS_SF,
    },
    "stress_parity_method":"average six stress tensor components at TET10 corner nodes, then compute von Mises; midside stress is derived from corners in ANSYS and cannot govern above the corner maximum",
    "mesh_note":"Quadratic TET10/TRI6 formulation is reproduced. Exact ANSYS run node/element count is not attested because the workshop project database is absent."
  },
  "astermax_code_aster":{
    "total_deformation_max_mm":disp,
    "von_mises_ansys_corner_component_first_max_mpa":vm_ansys_parity,
    "von_mises_ansys_corner_component_first_max_node_id":vm_ansys_node,
    "von_mises_direct_all_nodes_component_first_diagnostic_mpa":vm_all_nodes,
    "von_mises_direct_all_nodes_diagnostic_node_id":vm_all_node,
    "von_mises_scalar_first_nodal_max_mpa":vm_scalar_nodal,
    "von_mises_raw_elno_max_mpa":vm_raw,
    "safety_factor_ansys_parity":sf_parity,
    "safety_factor_scalar_first":sf_scalar,
    "safety_factor_raw_elno":sf_raw,
    "mesh":model["mesh"],
    "integrity":result.get("integrity",{})
  },
  "comparison":{
    "stress_error_pct":vm_error,
    "deformation_error_pct":u_error,
    "safety_factor_error_pct":sf_error,
    "stress_within_5pct":abs(vm_error)<=TOL_PCT,
    "deformation_within_5pct":abs(u_error)<=TOL_PCT,
    "both_primary_results_within_5pct":abs(vm_error)<=TOL_PCT and abs(u_error)<=TOL_PCT,
    "tolerance_pct":TOL_PCT
  },
  "pass_integrity":(
      model.get("fea_values_invented") is False and
      result.get("integrity",{}).get("fea_values_invented") is False and
      result.get("integrity",{}).get("solver_output_modified") is False and
      math.isfinite(disp) and disp>=0 and
      math.isfinite(vm_ansys_parity) and vm_ansys_parity>0
  )
}

os.makedirs(os.path.dirname(os.path.abspath(a.out)),exist_ok=True)
with open(a.out,"w",encoding="utf-8") as f: json.dump(report,f,indent=2)
print(json.dumps(report,indent=2))
if not report["pass_integrity"]:
    raise SystemExit("WS01.1 integrity comparison failed")
