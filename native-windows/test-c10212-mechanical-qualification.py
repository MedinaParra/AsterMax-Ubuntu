#!/usr/bin/env python3
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
GATE=ROOT/"qualify-mechanical-analysis.py"

def run_case(bundle, analysis, expect_code, expected_status, mess_text="ARRET NORMAL\naucune alarme\n",
             convergence=None):
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

manifest=json.loads((ROOT/"patch-chain.json").read_text(encoding="utf-8"))
entry=[x for x in manifest["patches"] if x["id"]=="patch-c10212-mechanical-qualification"]
assert len(entry)==1
assert entry[0]["file"]=="patch-c10212-mechanical-qualification.ps1"
scope_entry=[x for x in manifest["patches"] if x["id"]=="patch-c10213-scope-fingerprint"]
assert len(scope_entry)==1
assert scope_entry[0]["file"]=="patch-c10213-scope-fingerprint.ps1"
defaults_entry=[x for x in manifest["patches"] if x["id"]=="patch-c10214-tutorial1-defaults"]
assert len(defaults_entry)==1
assert defaults_entry[0]["file"]=="patch-c10214-tutorial1-defaults.ps1"
surface_entry=[x for x in manifest["patches"] if x["id"]=="patch-c10215-surface-mechanics"]
assert len(surface_entry)==1
body_entry=[x for x in manifest["patches"] if x["id"]=="patch-c10216-body-loads"]
assert len(body_entry)==1
assert body_entry[0]["file"]=="patch-c10216-body-loads.ps1"
traction_entry=[x for x in manifest["patches"] if x["id"]=="patch-c10217-surface-traction"]
assert len(traction_entry)==1
assert traction_entry[0]["file"]=="patch-c10217-surface-traction.ps1"
defaults_patch=(ROOT/"patch-c10214-tutorial1-defaults.ps1").read_text(encoding="utf-8")
assert "ASTERMAX_TUTORIAL1_DEFAULTS" in defaults_patch
assert "_secondOrder = true;" in defaults_patch
assert "_midsideNodesOnGeometry = false;" in defaults_patch
assert "WARN:linear_structural_solid_elements=" in defaults_patch
assert "readiness_warnings" in defaults_patch
scope_patch=(ROOT/"patch-c10213-scope-fingerprint.ps1").read_text(encoding="utf-8")
assert "mesh.nodesets=" in scope_patch
assert "mesh.elementsets=" in scope_patch
assert "mesh.surfaces=" in scope_patch
assert "model_fingerprint_mesh_scope" in scope_patch

ui=(ROOT/"AsterMaxMechanicalQualification.cs").read_text(encoding="utf-8")
assert "REAL_CODE_ASTER_MED" in ui
assert "von_mises_component_first_ansys_parity" in ui
assert "REAC_NODA resultant" in ui

bridge=(ROOT/"bridge-c964-med-results.py").read_text(encoding="utf-8")
assert 'optional_med_field_path(h, "REAC_NODA"' in bridge
assert '"reaction_resultant_from_real_reac_noda"' in bridge

print(json.dumps({"status":"PASS","cases":6,"patch_chain":True,"ui_contract":True,
                  "reaction_bridge_contract":True,"tutorial1_defaults":True,
                  "convergence_required_for_full_qualification":True,
                  "fea_values_invented":False},indent=2))
