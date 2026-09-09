import json,re,sys,math
from pathlib import Path
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
resu=root/'cantilever.resu'; mess=root/'cantilever.mess'; rmed=root/'cantilever.rmed'
checks=[]
def gate(name,passed,evidence): checks.append({'name':name,'pass':bool(passed),'evidence':str(evidence)})
for p in (resu,mess,rmed):
    gate(f'{p.suffix[1:]}_exists',p.exists(),p)
    if p.exists(): gate(f'{p.suffix[1:]}_nonempty',p.stat().st_size>32,p.stat().st_size)
rt=resu.read_text(errors='ignore') if resu.exists() else ''
mt=mess.read_text(errors='ignore') if mess.exists() else ''
dy=[]
for line in rt.splitlines():
    if not line.startswith('FREE_FACE_DISPLAC'):
        continue
    nums=re.findall(r'[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?',line)
    if len(nums)>=3: dy.append(float(nums[-2]))
P=100.0; L=100.0; E=210000.0; b=10.0; h=10.0
I=b*h**3/12.0
reference=-(P*L**3)/(3.0*E*I)
solver=sum(dy)/len(dy) if dy else None
rel=abs(solver-reference)/abs(reference) if solver is not None else None
spread=max(dy)-min(dy) if dy else None
gate('free_face_dy_extracted',solver is not None,f'count={len(dy)} mean_dy_mm={solver} values={dy}')
gate('cantilever_tip_matches_euler_bernoulli_15pct',rel is not None and rel<=0.15,f'solver={solver}; analytical={reference}; rel_error={rel}; tol=0.15')
gate('solver_no_fatal_marker',not re.search(r'(^|\n)\s*!?\s*<F(?:>|_)',mt), 'no fatal Code_Aster marker')
gate('solver_normal_stop','ARRET NORMAL' in mt and 'TOTAL_JOB' in mt,'ARRET NORMAL + TOTAL_JOB')
gate('mesh_declared_80_hexa8','HEXA8' in mt and (' 80' in mt or '80' in mt),'expected 80 HEXA8 structured solid mesh')
manifest={
 'release':'C9.81','benchmark_id':'B02','title':'Cantilever Bending Independent Physics Gate',
 'solver_execution':'RUN','unit_system':'mm-N-MPa',
 'scientific_integrity':{'fea_values_invented':False,'ansys_values_invented':False,'analytical_values_are_fea_output':False},
 'contract':{'geometry_mm':{'L':L,'b':b,'h':h},'material':{'E_MPa':E,'nu':0.30},'load':{'FY_total_N':-P},'bc':'x=0 fixed','mesh':'20x2x2 HEXA8 = 80 elements','predeclared_tip_deflection_tolerance_relative':0.15},
 'analytical_reference':{'kind':'Euler-Bernoulli cantilever tip deflection','I_mm4':I,'tip_dy_mm':reference},
 'solver_observation':{'free_face_dy_values_mm':dy,'mean_tip_dy_mm':solver,'relative_error_vs_analytical':rel,'free_face_spread_mm':spread,'rmed_bytes':rmed.stat().st_size if rmed.exists() else 0},
 'ansys_reference_state':'MISSING_OR_UNVERIFIED','ansys_equivalence':'NOT_PROVEN',
 'checks_total':len(checks),'checks_passed':sum(c['pass'] for c in checks),'all_checks_pass':all(c['pass'] for c in checks),'checks':checks}
(root/'C9.81_B02_VALIDATION.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
if not manifest['all_checks_pass']: sys.exit(2)
