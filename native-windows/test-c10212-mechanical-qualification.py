#!/usr/bin/env python3
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
GATE=ROOT/"qualify-mechanical-analysis.py"

def run_case(bundle, analysis, expect_code, expected_status):
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        bp=td/"bundle.json"; ap=td/"analysis.json"; op=td/"out.json"
        bp.write_text(json.dumps(bundle),encoding="utf-8")
        ap.write_text(json.dumps(analysis),encoding="utf-8")
        p=subprocess.run([sys.executable,str(GATE),"--bundle",str(bp),"--analysis",str(ap),"--out",str(op)],
                         text=True,capture_output=True)
        if p.returncode!=expect_code:
            raise AssertionError(f"return code {p.returncode} != {expect_code}\nSTDOUT={p.stdout}\nSTDERR={p.stderr}")
        out=json.loads(op.read_text(encoding="utf-8"))
        if out["status"]!=expected_status:
            raise AssertionError(f"status {out['status']} != {expected_status}")
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
  "expected_external_resultant_n":[0.0,0.0,1000.0]
}
out=run_case(base,analysis,0,"ENGINEERING_QUALIFIED")
eq=[x for x in out["findings"] if x["code"]=="GLOBAL_EQUILIBRIUM"][0]
assert eq["level"]=="PASS" and abs(eq["residual_pct"])<1e-12

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

print(json.dumps({"status":"PASS","cases":3,"fea_values_invented":False},indent=2))
