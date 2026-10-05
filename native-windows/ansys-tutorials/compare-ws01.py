#!/usr/bin/env python3
import argparse,json
from pathlib import Path
import ws01_contract as contract
finite=contract.finite_number

ap=argparse.ArgumentParser()
ap.add_argument("--bundle",required=True)
ap.add_argument("--input",required=True)
ap.add_argument("--out",required=True)
ap.add_argument("--reference")
args=ap.parse_args()

# Never leave an earlier successful report at the requested output on failure.
out=Path(args.out)
if out.resolve() in {Path(p).resolve() for p in (args.bundle, args.input, args.reference) if p}:
    raise SystemExit("output must not overwrite input evidence")
out.unlink(missing_ok=True)

bundle=json.load(open(args.bundle,encoding="utf-8-sig"))
inp=json.load(open(args.input,encoding="utf-8-sig"))
f=bundle["fields"]

u=finite(f["displacement"]["total_max"], "total displacement")
vm_nodal=finite(f["von_mises"]["nodal_max"], "nodal von Mises")
vm_raw=finite(f["von_mises"]["raw_elno_max"], "raw von Mises")
yield_mpa=finite(inp["material"]["yield_mpa_for_safety_factor"], "yield strength", positive=True)
sf_nodal=yield_mpa/vm_nodal if vm_nodal>0 else None
sf_raw=yield_mpa/vm_raw if vm_raw>0 else None

reference=None
if args.reference:
    reference=json.load(open(args.reference,encoding="utf-8-sig"))

checks=contract.check_contract(bundle, inp, reference)

ansys_ref={
  "pressure_mpa":1.1,
  "pressure_face_count":17,
  "supports":"4 counterbore + 8 inner recess + 1 lip, frictionless",
  "reported_minimum_safety_factor":"slightly greater than 1.0",
  "exact_numeric_deformation_in_available_reference":None,
  "exact_numeric_von_mises_in_available_reference":None,
}
comparison={
  "same_geometry_and_load_definition":all(checks[k] for k in ("exact_cad", "scope_binding", "pressure_scope", "pressure")),
  "same_support_intent":checks["support_scope"] and checks["supports"],
  "numeric_safety_factor_above_one_nodal":sf_nodal is not None and sf_nodal>1.0,
  "numeric_safety_factor_above_one_raw_elno":sf_raw is not None and sf_raw>1.0,
  "percent_difference_vs_ansys_deformation":None,
  "percent_difference_vs_ansys_von_mises":None,
  "percent_difference_vs_ansys_safety_factor_nodal":None,
}

if reference:
    rr=reference["reference"]
    ref_u=finite(rr["total_deformation_max_mm"], "reference displacement", positive=True)
    ref_vm=finite(rr["equivalent_stress_max_MPa"], "reference stress", positive=True)
    ref_sf=finite(rr["safety_factor_min"], "reference safety factor", positive=True)
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
      "percent_difference_vs_ansys_safety_factor_nodal":100.0*(sf_nodal-ref_sf)/ref_sf if sf_nodal is not None else None,
    })

tolerance=finite(reference.get("acceptance",{}).get("tolerance_pct",5.0), "tolerance", positive=True) if reference else None
errors=[comparison[k] for k in ("percent_difference_vs_ansys_deformation", "percent_difference_vs_ansys_von_mises", "percent_difference_vs_ansys_safety_factor_nodal")]
comparison["within_snapshot_tolerance"] = all(e is not None and abs(e)<=tolerance for e in errors) if reference and all(checks.values()) else None
comparison["evidence_checks"] = checks
comparison["evidence_status"] = "PASS" if all(checks.values()) else "BLOCKED"
comparison["benchmark_equivalence"] = "NOT_ESTABLISHED"
comparison["reference_is_mesh_converged"] = False
comparison["evidence_limit"] = "Checks validate supplied metadata, not independent solver execution or CAD-to-result identity. The tutorial snapshot does not establish converged cross-solver equivalence."

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
Path(args.out).write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
print(json.dumps(result,indent=2,allow_nan=False))
if not all(checks.values()):
    raise SystemExit(2)
