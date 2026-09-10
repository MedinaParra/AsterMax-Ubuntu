#!/usr/bin/env python3
import json, math, pathlib, re, shutil, statistics, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parents[3]
GEN = ROOT / 'generate_step_case.py'
HARNESS = REPO / 'integrations/prepomax-codeaster/harness/astermax_harness.py'
MANIFEST = ROOT / 'step_mm.harness.manifest.json'
ART = REPO / 'artifact/c8-42'
LEVELS = [('coarse', 10.0), ('medium', 7.5), ('fine', 5.0)]
NUM = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$')
NODE = re.compile(r'^(?:N)?(\d+)$', re.I)


def run(*args):
    print('+', ' '.join(map(str,args)), flush=True)
    subprocess.check_call([str(x) for x in args], cwd=str(REPO))


def rows(text, marker, nvals):
    i = text.find(marker)
    if i < 0: raise RuntimeError(marker + ' missing from genuine RESU')
    out=[]; started=False
    for raw in text[i:].splitlines()[1:]:
        line=raw.strip()
        if not line:
            if started: break
            continue
        cols=[c.strip() for c in line.split(';')]
        if not cols or not NODE.fullmatch(cols[0]): continue
        vals=[float(c) for c in cols[1:] if NUM.fullmatch(c)]
        if len(vals) >= nvals:
            out.append((cols[0], vals[:nvals])); started=True
    return out


def patch_generator(original, size):
    s=original
    s=s.replace("Mesh.MeshSizeMin', 7.5", "Mesh.MeshSizeMin', " + str(size))
    s=s.replace("Mesh.MeshSizeMax', 7.5", "Mesh.MeshSizeMax', " + str(size))
    s=s.replace("'mesh_size_mm':7.5", "'mesh_size_mm':" + str(size))
    if s == original and size != 7.5: raise RuntimeError('Mesh-size patch anchors not found')
    GEN.write_text(s, encoding='utf-8')


def admit_case(label, size):
    pre=json.loads((ROOT/'C8_40_PRE_SOLVE.json').read_text())
    text=(ROOT/'step_mm.resu').read_text(encoding='utf-8', errors='replace')
    disp=rows(text,'PPM_DEPL',3); mises=rows(text,'PPM_MISES',1); reac=rows(text,'PPM_REAC',3)
    if len(disp)<4 or len(mises)<4 or len(reac)<3: raise RuntimeError('Incomplete genuine result tables')
    rx=sum(v[0] for _,v in reac); ry=sum(v[1] for _,v in reac); rz=sum(v[2] for _,v in reac)
    applied=float(pre['solver_force_sum_N'])
    eq=abs(rx+applied)/max(abs(applied),1.0); transverse=math.hypot(ry,rz)/max(abs(applied),1.0)
    if eq>5e-3 or transverse>5e-3: raise RuntimeError(f'Equilibrium failed for {label}: x={eq} transverse={transverse}')
    maxdx=max(abs(v[0]) for _,v in disp); expected=float(pre['analytic_axial_displacement_mm']); err=abs(maxdx-expected)/expected
    vm=[v[0] for _,v in mises]
    case={'level':label,'mesh_size_mm':size,'mesh_nodes':pre['mesh_nodes'],'tetra4_elements':pre['tetra4_elements'],'min_tet_abs_volume_mm3':pre['min_tet_abs_volume_mm3'],'max_abs_dx_mm':maxdx,'analytic_dx_mm':expected,'dx_relative_error':err,'reaction_sum_x_N':rx,'equilibrium_relative_error':eq,'transverse_reaction_relative_resultant':transverse,'vmis_median_mpa':statistics.median(vm),'vmis_min_mpa':min(vm),'vmis_max_mpa':max(vm)}
    out=ART/'cases'/label; out.mkdir(parents=True, exist_ok=True)
    (out/'CASE.json').write_text(json.dumps(case,indent=2),encoding='utf-8')
    for name in ['C8_40_PRE_SOLVE.json','step_mm.mail','step_mm.comm','step_mm.mess','step_mm.resu','step_mm.rmed','beam_100x20x10.step']:
        shutil.copy2(ROOT/name,out/name)
    print(json.dumps(case,indent=2), flush=True)
    return case


def main():
    ART.mkdir(parents=True,exist_ok=True); (ART/'cases').mkdir(exist_ok=True)
    original=GEN.read_text(encoding='utf-8')
    cases=[]
    try:
        for label,size in LEVELS:
            patch_generator(original,size)
            for stale in ['step_mm.mess','step_mm.resu','step_mm.rmed']:
                p=ROOT/stale
                if p.exists(): p.unlink()
            run(sys.executable, GEN)
            run(sys.executable, ROOT/'prepare_nodal_load.py')
            run(sys.executable, ROOT/'prepare_reaction_gate.py')
            run(sys.executable, HARNESS, '--manifest', MANIFEST)
            cases.append(admit_case(label,size))
    finally:
        GEN.write_text(original,encoding='utf-8')
    nodes=[c['mesh_nodes'] for c in cases]; elems=[c['tetra4_elements'] for c in cases]
    if not (nodes[0] < nodes[1] < nodes[2] and elems[0] < elems[1] < elems[2]): raise RuntimeError(f'Mesh refinement did not increase resolution: nodes={nodes} elems={elems}')
    dx=[c['max_abs_dx_mm'] for c in cases]; err=[c['dx_relative_error'] for c in cases]
    mf=abs(dx[2]-dx[1])/max(abs(dx[2]),1e-15); cf=abs(dx[2]-dx[0])/max(abs(dx[2]),1e-15)
    if err[2] > err[0]: raise RuntimeError(f'Fine displacement is not closer to analytic oracle: errors={err}')
    if mf > 0.08: raise RuntimeError(f'Displacement not stabilized enough: medium-fine={mf}')
    evidence={'schema':'astermax.c8-42.mesh-convergence.v1','solver':'Code_Aster 17.4.0','cad':'same STEP geometry regenerated/re-imported identically for each level','unit_system':'mm-N-MPa','mesh_levels':cases,'nodes_strictly_increase':True,'elements_strictly_increase':True,'all_reaction_equilibrium_verified':True,'fine_error_not_worse_than_coarse':True,'medium_fine_dx_relative_change':mf,'coarse_fine_dx_relative_change':cf,'mesh_convergence_qualified':True,'industrial_validation':False,'ansys_equivalence':False}
    (ART/'C8_42_MESH_CONVERGENCE.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence,indent=2))

if __name__ == '__main__': main()
