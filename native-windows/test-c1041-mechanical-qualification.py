#!/usr/bin/env python3
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
GATE=ROOT/"qualify-mechanical-analysis.py"
CASE_COUNT=0

def run_case(bundle, analysis, expect_code, expected_status, mess_text="ARRET NORMAL\naucune alarme\n",
             convergence=None):
    global CASE_COUNT
    CASE_COUNT += 1
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        bp=td/"bundle.json"; ap=td/"analysis.json"; mp=td/"case.mess"; op=td/"out.json"
        bp.write_text(json.dumps(bundle),encoding="utf-8")
        ap.write_text(json.dumps(analysis),encoding="utf-8")
        mp.write_text(mess_text,encoding="utf-8")
        cmd=[sys.executable,str(GATE),"--bundle",str(bp),"--analysis",str(ap),
             "--mess",str(mp),"--out",str(op)]
        if convergence is not None:
            cp=td/"convergence.json"
            cp.write_text(json.dumps(convergence),encoding="utf-8")
            cmd += ["--convergence",str(cp)]
        p=subprocess.run(cmd,text=True,capture_output=True)
        if p.returncode!=expect_code:
            raise AssertionError(f"return code {p.returncode} != {expect_code}\nSTDOUT={p.stdout}\nSTDERR={p.stderr}")
        out=json.loads(op.read_text(encoding="utf-8"))
        if out["engineering_qualification"]!=expected_status:
            raise AssertionError(f"qualification {out['engineering_qualification']} != {expected_status}")
        assert out["status"] in ("PASS", "FAIL", "BLOCKED", "NOT_RUN")
        assert out["solver_state"] == "SOURCE_DECLARED_NOT_INDEPENDENTLY_VERIFIED"
        return out

base={
  "schema":"astermax-results-bundle/v0",
  "source":{"kind":"REAL_CODE_ASTER_MED","file":"case.rmed","size_bytes":10000},
  "units":{"length":"mm","force":"N","stress":"MPa"},
  "mesh":{"element_type":"TETRA10","element_types":["TETRA10"],"node_count":100,"element_count":50},
  "fields":{
    "displacement":{"total_max":0.1},
    "von_mises":{"nodal_max":100.0},
    "reaction":{"resultant_n":[0.0,0.0,-1000.0],"resultant_magnitude_n":1000.0}
  },
  "integrity":{
    "fea_values_invented":False,
    "von_mises_component_first_ansys_parity":True,
    "reaction_resultant_from_real_reac_noda":True
  }
}
analysis={
  "scope_binding":{"mode":"topology_fingerprint","verified":True},
  "expected_external_resultant_n":[0.0,0.0,1000.0],
  "external_resultant_complete":True,
  "external_resultant_independent":True
}
convergence_ok={
  "rows":[
    {"state":"SOLVED","mesh":"2mm","total_deformation_max_mm":0.1000,"von_mises_nodal_max_mpa":100.0},
    {"state":"SOLVED","mesh":"1mm","total_deformation_max_mm":0.1020,"von_mises_nodal_max_mpa":105.0}
  ]
}
out=run_case(base,analysis,0,"ENGINEERING_QUALIFIED",convergence=convergence_ok)
eq=[x for x in out["findings"] if x["code"]=="GLOBAL_EQUILIBRIUM"][0]
assert eq["level"]=="PASS" and abs(eq["residual_pct"])<1e-12
assert any(x["code"]=="MESH_CONVERGENCE" and x["level"]=="PASS" for x in out["findings"])

body_analysis=json.loads(json.dumps(analysis))
body_analysis["external_resultant_complete"]=False
body_analysis["external_resultant_note"]="gravity/rotation body loads not independently integrated"
body=run_case(base,body_analysis,0,"SOLVED_WITH_ENGINEERING_WARNINGS",convergence=convergence_ok)
assert any(x["code"]=="GLOBAL_EQUILIBRIUM" and x["level"]=="WARN" for x in body["findings"])
assert body["equilibrium"] is None

no_conv=run_case(base,analysis,0,"SOLVED_WITH_ENGINEERING_WARNINGS")
assert any(x["code"]=="MESH_CONVERGENCE" and x["level"]=="WARN" for x in no_conv["findings"])

warn=json.loads(json.dumps(base))
warn["mesh"]["element_type"]="TETRA4"
warn["mesh"]["element_types"]=["TETRA4"]
warn_analysis={"scope_binding":{"mode":"raw_face_index_only","verified":False}}
out=run_case(warn,warn_analysis,0,"SOLVED_WITH_ENGINEERING_WARNINGS")
assert any(x["code"]=="STRUCTURAL_ELEMENT_ORDER" and x["level"]=="WARN" for x in out["findings"])
assert any(x["code"]=="GLOBAL_EQUILIBRIUM" and x["level"]=="WARN" for x in out["findings"])

bad=json.loads(json.dumps(base))
bad["units"]["length"]="m"
out=run_case(bad,analysis,2,"BLOCKED")
assert any(x["code"]=="UNIT_CONTRACT" and x["level"]=="BLOCK" for x in out["findings"])

mesh_bad=run_case(
    base, analysis, 2, "BLOCKED",
    mess_text="ALARME: la maille T10 est trop distordue\nLe jacobien change de signe.\n"
)
assert any(x["code"]=="SOLVER_MESH_QUALITY" and x["level"]=="BLOCK" for x in mesh_bad["findings"])


# C10.41: exercise the failures reproduced before repair.
for field in ("displacement", "von_mises"):
    bad=json.loads(json.dumps(base)); bad["fields"].pop(field)
    run_case(bad, analysis, 2, "BLOCKED", convergence=convergence_ok)
for value in (False, None):
    bad=json.loads(json.dumps(base))
    bad["integrity"]["reaction_resultant_from_real_reac_noda"]=value
    run_case(bad, analysis, 2, "BLOCKED", convergence=convergence_ok)
for value in ([0, 0], [0, 0, float("nan")], [0, 0, float("inf")], [0, 0, True]):
    bad=json.loads(json.dumps(base)); bad["fields"]["reaction"]["resultant_n"]=value
    run_case(bad, analysis, 2, "BLOCKED", convergence=convergence_ok)
    bad_analysis=json.loads(json.dumps(analysis)); bad_analysis["expected_external_resultant_n"]=value
    run_case(base, bad_analysis, 2, "BLOCKED", convergence=convergence_ok)
for value in (0, -1, float("nan"), float("inf")):
    bad_conv=json.loads(json.dumps(convergence_ok))
    bad_conv["rows"][0]["total_deformation_max_mm"]=value
    run_case(base, analysis, 2, "BLOCKED", convergence=bad_conv)
for residual, level, status, code in ((10, "PASS", "ENGINEERING_QUALIFIED", 0),
                                    (50, "WARN", "SOLVED_WITH_ENGINEERING_WARNINGS", 0),
                                    (51, "BLOCK", "BLOCKED", 2)):
    bad=json.loads(json.dumps(base)); bad["fields"]["reaction"]["resultant_n"]=[0,0,-1000+residual]
    result=run_case(bad,analysis,code,status,convergence=convergence_ok)
    assert any(x["code"]=="GLOBAL_EQUILIBRIUM" and x["level"]==level for x in result["findings"])
unattested=json.loads(json.dumps(analysis))
unattested.pop("external_resultant_complete")
run_case(base, unattested, 0, "SOLVED_WITH_ENGINEERING_WARNINGS", convergence=convergence_ok)
unattested=json.loads(json.dumps(analysis))
unattested.pop("external_resultant_independent")
run_case(base, unattested, 0, "SOLVED_WITH_ENGINEERING_WARNINGS", convergence=convergence_ok)
print(f"PASS: {CASE_COUNT} qualification fixture cases; not solver certification")
