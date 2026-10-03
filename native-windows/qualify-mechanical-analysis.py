#!/usr/bin/env python3
"""AsterMax mechanical qualification gate.

This gate evaluates whether a real solver result is trustworthy for engineering
review. It deliberately separates numerical/physical qualification from
cross-solver benchmark equivalence.
"""
import argparse, json, math, re
from pathlib import Path

def pct_delta(a,b):
    if b == 0:
        return None
    return 100.0*(a-b)/b

def norm3(v):
    return math.sqrt(sum(float(x)*float(x) for x in v))

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
    if re.search(r"\bARRET\s+NORMAL\b", mess_text, re.IGNORECASE):
        f.append(finding("SOLVER_TERMINATION","PASS",
                         "Code_Aster .mess attests ARRET NORMAL."))
    else:
        f.append(finding("SOLVER_TERMINATION","BLOCK",
                         "Code_Aster .mess does not attest ARRET NORMAL; solver output is not admissible as a completed analysis."))
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
    f.append(finding("SOLVER_TERMINATION","WARN",
        "No Code_Aster .mess file was supplied; normal solver termination cannot be attested."))
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
reaction_moment=reaction.get("moment_about_origin_n_mm")
expected=analysis.get("expected_external_resultant_n")
expected_moment=analysis.get("expected_external_moment_n_mm")
external_resultant_complete=analysis.get("external_resultant_complete", True)
if reaction_vec is not None:
    f.append(finding("REACTION_EVIDENCE","PASS","Real REAC_NODA resultant is present.",
                     reaction_resultant_n=reaction_vec,
                     reaction_moment_about_origin_n_mm=reaction_moment))
else:
    f.append(finding("REACTION_EVIDENCE","WARN","No REAC_NODA resultant is present in the result bundle."))

equilibrium=None
moment_equilibrium=None
if expected is not None and external_resultant_complete is False:
    f.append(finding("GLOBAL_EQUILIBRIUM","WARN",
        "The applied-load force/moment resultant is intentionally incomplete (for example gravity/rotation body loads are present); global equilibrium is not declared closed.",
        partial_expected_external_resultant_n=expected,
        partial_expected_external_moment_n_mm=expected_moment,
        external_resultant_note=analysis.get("external_resultant_note")))
elif reaction_vec is not None and expected is not None:
    residual=[float(reaction_vec[i])+float(expected[i]) for i in range(3)]
    denom=max(norm3(expected),1e-12)
    residual_pct=100.0*norm3(residual)/denom
    equilibrium={"expected_external_resultant_n":expected,"reaction_resultant_n":reaction_vec,
                 "residual_n":residual,"residual_pct":residual_pct,
                 "acceptance":{"pass_pct":1.0,"warn_pct":5.0}}
    if residual_pct <= 1.0:
        lvl="PASS"
    elif residual_pct <= 5.0:
        lvl="WARN"
    else:
        lvl="BLOCK"
    f.append(finding("GLOBAL_EQUILIBRIUM",lvl,f"Global force equilibrium residual = {residual_pct:.4g}%.",**equilibrium))

    if reaction_moment is not None and expected_moment is not None:
        moment_residual=[float(reaction_moment[i])+float(expected_moment[i]) for i in range(3)]
        # Relative moment residual is normalized by the expected applied moment,
        # with a 1 N*mm floor so a nominal zero-moment case still has a finite,
        # documented absolute scale instead of division by zero.
        moment_denom=max(norm3(expected_moment),1.0)
        moment_residual_pct=100.0*norm3(moment_residual)/moment_denom
        moment_equilibrium={
            "origin_mm":[0.0,0.0,0.0],
            "expected_external_moment_n_mm":expected_moment,
            "reaction_moment_n_mm":reaction_moment,
            "residual_n_mm":moment_residual,
            "residual_pct":moment_residual_pct,
            "normalization_floor_n_mm":1.0,
            "acceptance":{"pass_pct":1.0,"warn_pct":5.0}
        }
        if moment_residual_pct <= 1.0:
            moment_lvl="PASS"
        elif moment_residual_pct <= 5.0:
            moment_lvl="WARN"
        else:
            moment_lvl="BLOCK"
        f.append(finding("GLOBAL_MOMENT_EQUILIBRIUM",moment_lvl,
                         f"Global moment equilibrium residual = {moment_residual_pct:.4g}% about the global origin.",
                         **moment_equilibrium))
    elif expected_moment is not None:
        f.append(finding("GLOBAL_MOMENT_EQUILIBRIUM","WARN",
                         "Applied-load moment was supplied but REAC_NODA moment evidence is unavailable."))
    elif reaction_moment is not None:
        f.append(finding("GLOBAL_MOMENT_EQUILIBRIUM","WARN",
                         "Reaction moment is available, but no independently assembled applied-load moment was supplied; moment equilibrium is not closed."))
elif expected is not None:
    f.append(finding("GLOBAL_EQUILIBRIUM","WARN","Applied-load resultant was supplied but reaction evidence is unavailable."))
elif reaction_vec is not None:
    f.append(finding("GLOBAL_EQUILIBRIUM","WARN","Reaction resultant is available, but no independently assembled applied-load resultant was supplied; equilibrium is not closed."))

convergence=None
if conv:
    rows=[x for x in conv.get("rows",[]) if x.get("state")=="SOLVED"]
    if len(rows)>=2:
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
    if vm is not None and u is not None and "equivalent_stress_max_MPa" in rr and "total_deformation_max_mm" in rr:
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
    "status":status,
    "solver_state":"SOLVED_AUTHENTIC" if not any(x["code"]=="REAL_SOLVER_EVIDENCE" and x["level"]=="BLOCK" for x in f) else "UNTRUSTED",
    "engineering_qualification":status,
    "benchmark_equivalence":"SEPARATE_NOT_INFERRED",
    "findings":f,
    "equilibrium":equilibrium,
    "moment_equilibrium":moment_equilibrium,
    "convergence":convergence,
    "benchmark":benchmark,
    "integrity":{"fea_values_invented":False}
}
Path(args.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))
if blocks:
    raise SystemExit(2)
