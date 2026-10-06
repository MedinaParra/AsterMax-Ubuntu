#!/usr/bin/env python3
"""AsterMax mechanical qualification gate.

This gate evaluates whether a real solver result is trustworthy for engineering
review. It deliberately separates numerical/physical qualification from
cross-solver benchmark equivalence.
"""
import argparse, hashlib, json, math
from pathlib import Path

def pct_delta(a,b):
    if b == 0:
        return None
    return 100.0*(a-b)/b

def norm3(v):
    return math.hypot(*(float(x) for x in v))

def finite_number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))

def vector3(value):
    return isinstance(value, list) and len(value) == 3 and all(finite_number(x) for x in value)

def finding(code, level, message, **data):
    d={"code":code,"level":level,"message":message}
    d.update(data)
    return d

ap=argparse.ArgumentParser()
ap.add_argument("--bundle",required=True)
ap.add_argument("--analysis")
ap.add_argument("--convergence")
ap.add_argument("--reference")
ap.add_argument("--mess")
ap.add_argument("--out",required=True)
args=ap.parse_args()

bundle=json.loads(Path(args.bundle).read_text(encoding="utf-8-sig"))
analysis=json.loads(Path(args.analysis).read_text(encoding="utf-8-sig")) if args.analysis else {}
conv=json.loads(Path(args.convergence).read_text(encoding="utf-8-sig")) if args.convergence else None
ref=json.loads(Path(args.reference).read_text(encoding="utf-8-sig")) if args.reference else None

mess_text=None
if args.mess:
    mess_path=Path(args.mess)
    if not mess_path.exists():
        raise SystemExit("Code_Aster .mess evidence file is missing: "+str(mess_path))
    mess_text=mess_path.read_text(encoding="utf-8",errors="replace")

f=[]
integrity=bundle.get("integrity",{})
source=bundle.get("source",{})
units=bundle.get("units",{})
mesh=bundle.get("mesh",{})
fields=bundle.get("fields",{})

# Structural observables must exist before a manifest can be qualified.
# These checks validate supplied evidence; they do not attest solver execution.
for field, key in (("displacement", "total_max"), ("von_mises", "nodal_max")):
    value=(fields.get(field) or {}).get(key)
    if not finite_number(value) or value < 0:
        f.append(finding("STRUCTURAL_RESULT_"+field.upper(), "BLOCK",
                         "Required structural maximum is missing, negative or non-finite."))

if source.get("kind")=="REAL_CODE_ASTER_MED" and integrity.get("fea_values_invented") is False:
    f.append(finding("REAL_SOLVER_EVIDENCE","PASS","Real Code_Aster MED evidence admitted."))
else:
    f.append(finding("REAL_SOLVER_EVIDENCE","BLOCK","Result source/integrity does not prove real Code_Aster evidence."))

if units=={"length":"mm","force":"N","stress":"MPa"}:
    f.append(finding("UNIT_CONTRACT","PASS","Verified mm-N-MPa unit contract."))
else:
    f.append(finding("UNIT_CONTRACT","BLOCK","Unexpected or incomplete unit contract.",units=units))

if integrity.get("von_mises_component_first_ansys_parity") is True:
    f.append(finding("VMIS_COMPONENT_FIRST","PASS","Equivalent stress uses component-first nodal averaging."))
else:
    f.append(finding("VMIS_COMPONENT_FIRST","WARN","Equivalent stress provenance does not prove component-first nodal averaging."))

if mess_text is not None:
    import re
    mesh_alarm_patterns=[
        r"trop\s+distordue",
        r"jacobien[^\n]*(?:signe|n[ée]gatif)",
        r"jacobian[^\n]*(?:sign|negative)",
        r"maille[^\n]*invers",
    ]
    matched=[]
    for pattern in mesh_alarm_patterns:
        if re.search(pattern,mess_text,re.IGNORECASE):
            matched.append(pattern)
    if matched:
        f.append(finding("SOLVER_MESH_QUALITY","BLOCK",
            "Code_Aster message file contains distorted/inverted-element or Jacobian alarm evidence.",
            matched_patterns=matched))
    else:
        f.append(finding("SOLVER_MESH_QUALITY","PASS",
            "Code_Aster message file contains no recognized distorted/inverted-element or Jacobian alarms."))
else:
    f.append(finding("SOLVER_MESH_QUALITY","WARN",
        "No Code_Aster .mess file was supplied to the mechanical qualification gate."))

types=mesh.get("element_types") or ([mesh.get("element_type")] if mesh.get("element_type") else [])
types=[x for x in types if x]
if types and all(t=="TETRA10" for t in types):
    f.append(finding("STRUCTURAL_ELEMENT_ORDER","PASS","Quadratic TETRA10 structural solid mesh.",element_types=types))
elif any(t in ("TETRA4","HEXA8") for t in types):
    f.append(finding("STRUCTURAL_ELEMENT_ORDER","WARN","Linear solid elements are accepted for solving but not preferred for stress equivalence.",element_types=types))
else:
    f.append(finding("STRUCTURAL_ELEMENT_ORDER","WARN","Element order/family is not explicitly qualified.",element_types=types))

scope=analysis.get("scope_binding") or {}
mode=scope.get("mode")
if mode in ("topology_fingerprint","exact_cad_sha256_plus_face_manifest","model_fingerprint_mesh_scope") and scope.get("verified") is True:
    f.append(finding("TOPOLOGY_STABLE_SCOPE","PASS","Loads/supports use verified topology-stable scoping.",mode=mode))
elif mode in ("raw_face_index","raw_face_index_only"):
    f.append(finding("TOPOLOGY_STABLE_SCOPE","WARN","Raw CAD face indices are not persistent identity; use topology fingerprints."))
elif scope:
    f.append(finding("TOPOLOGY_STABLE_SCOPE","WARN","Scope binding exists but is not attested as verified topology fingerprints.",scope=scope))
else:
    f.append(finding("TOPOLOGY_STABLE_SCOPE","WARN","No topology-stable scope evidence was supplied to qualification."))

reaction=(fields.get("reaction") or {})
reaction_vec=reaction.get("resultant_n")
expected=analysis.get("expected_external_resultant_n")
external_resultant_complete=analysis.get("external_resultant_complete") is True
if expected is not None and analysis.get("external_resultant_independent") is not True:
    f.append(finding("APPLIED_RESULTANT_PROVENANCE", "WARN",
                     "Independent assembly of the applied resultant has not been attested."))
if reaction_vec is not None and not vector3(reaction_vec):
    f.append(finding("REACTION_EVIDENCE", "BLOCK", "Reaction resultant must contain three finite numbers."))
    reaction_vec=None
elif reaction_vec is not None and integrity.get("reaction_resultant_from_real_reac_noda") is not True:
    f.append(finding("REACTION_EVIDENCE", "BLOCK", "Reaction provenance does not identify real REAC_NODA values."))
    reaction_vec=None
elif reaction_vec is not None:
    f.append(finding("REACTION_EVIDENCE","PASS","Real REAC_NODA resultant is present.",reaction_resultant_n=reaction_vec))
else:
    f.append(finding("REACTION_EVIDENCE","WARN","No REAC_NODA resultant is present in the result bundle."))

equilibrium=None
if expected is not None and not vector3(expected):
    f.append(finding("GLOBAL_EQUILIBRIUM", "BLOCK", "Applied resultant must contain three finite numbers."))
    expected=None
if expected is not None and external_resultant_complete is False:
    f.append(finding("GLOBAL_EQUILIBRIUM","WARN",
        "The applied-load resultant is intentionally incomplete (for example gravity/rotation body loads are present); global equilibrium is not declared closed.",
        partial_expected_external_resultant_n=expected,
        external_resultant_note=analysis.get("external_resultant_note")))
elif reaction_vec is not None and expected is not None:
    residual=[float(reaction_vec[i])+float(expected[i]) for i in range(3)]
    denom=max(norm3(expected),1e-12)
    residual_pct=100.0*norm3(residual)/denom
    equilibrium={"expected_external_resultant_n":expected,"reaction_resultant_n":reaction_vec,
                 "residual_n":residual,"residual_pct":residual_pct}
    if residual_pct <= 1.0:
        lvl="PASS"
    elif residual_pct <= 5.0:
        lvl="WARN"
    else:
        lvl="BLOCK"
    f.append(finding("GLOBAL_EQUILIBRIUM",lvl,f"Global force equilibrium residual = {residual_pct:.4g}%.",**equilibrium))
elif expected is not None:
    f.append(finding("GLOBAL_EQUILIBRIUM","WARN","Applied-load resultant was supplied but reaction evidence is unavailable."))
elif reaction_vec is not None:
    f.append(finding("GLOBAL_EQUILIBRIUM","WARN","Reaction resultant is available, but no independently assembled applied-load resultant was supplied; equilibrium is not closed."))

convergence=None
if conv:
    rows=[x for x in conv.get("rows",[]) if x.get("state")=="SOLVED"]
    valid_rows=all(finite_number(x.get(k)) and x[k] > 0 for x in rows
                   for k in ("total_deformation_max_mm", "von_mises_nodal_max_mpa"))
    if not valid_rows:
        f.append(finding("MESH_CONVERGENCE", "BLOCK", "Convergence observables must be positive finite numbers."))
    elif len(rows)>=2:
        a,b=rows[-2],rows[-1]
        du=abs(pct_delta(float(b["total_deformation_max_mm"]),float(a["total_deformation_max_mm"])))
        ds=abs(pct_delta(float(b["von_mises_nodal_max_mpa"]),float(a["von_mises_nodal_max_mpa"])))
        convergence={"previous_mesh":a.get("mesh"),"finest_mesh":b.get("mesh"),
                     "deformation_change_pct":du,"stress_change_pct":ds}
        level="PASS" if du<=5.0 and ds<=10.0 else "WARN"
        f.append(finding("MESH_CONVERGENCE",level,
            f"Last mesh change: deformation {du:.3g}%, equivalent stress {ds:.3g}%.",**convergence))
    else:
        f.append(finding("MESH_CONVERGENCE","WARN","Fewer than two solved mesh levels are available."))
else:
    f.append(finding("MESH_CONVERGENCE","WARN",
        "No mesh-convergence evidence was supplied. Results remain usable for review, but are not engineering-qualified by default."))

benchmark=None
if ref:
    rr=ref.get("reference",ref)
    vm=fields.get("von_mises",{}).get("nodal_max")
    u=fields.get("displacement",{}).get("total_max")
    reference_vm=rr.get("equivalent_stress_max_MPa")
    reference_u=rr.get("total_deformation_max_mm")
    if not all(finite_number(x) and x > 0 for x in (reference_vm, reference_u)):
        f.append(finding("BENCHMARK_COMPARISON", "BLOCK", "Reference maxima must be positive finite numbers."))
    elif finite_number(vm) and finite_number(u):
        benchmark={
            "deformation_error_pct":pct_delta(float(u),float(rr["total_deformation_max_mm"])),
            "von_mises_error_pct":pct_delta(float(vm),float(rr["equivalent_stress_max_MPa"])),
            "reference_classification":ref.get("classification")
        }
        f.append(finding("BENCHMARK_COMPARISON","INFO",
            "Benchmark difference is reported separately and does not decide physical validity.",**benchmark))

blocks=[x for x in f if x["level"]=="BLOCK"]
warns=[x for x in f if x["level"]=="WARN"]
if blocks:
    status="BLOCKED"
elif warns:
    status="SOLVED_WITH_ENGINEERING_WARNINGS"
else:
    status="ENGINEERING_QUALIFIED"

report={
    "schema":"astermax-mechanical-qualification/v1",
    "bundle_sha256":hashlib.sha256(Path(args.bundle).read_bytes()).hexdigest(),
    "model_fingerprint_sha256":integrity.get("model_fingerprint_sha256"),
    "status":"BLOCKED" if blocks or warns else "PASS",
    "evidence_status":"BLOCKED" if blocks or warns else "PASS",
    "solver_state":"SOURCE_DECLARED_NOT_INDEPENDENTLY_VERIFIED",
    "engineering_qualification":status,
    "benchmark_equivalence":"SEPARATE_NOT_INFERRED",
    "findings":f,
    "equilibrium":equilibrium,
    "convergence":convergence,
    "benchmark":benchmark,
    "integrity":{"fea_values_invented":False}
}
Path(args.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))
if blocks:
    raise SystemExit(2)
