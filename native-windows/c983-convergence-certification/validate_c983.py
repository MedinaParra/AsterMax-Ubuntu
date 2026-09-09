from pathlib import Path
import argparse, json, math, re, sys

p=argparse.ArgumentParser()
p.add_argument('--root',required=True)
p.add_argument('--cases',nargs='+',required=True)
a=p.parse_args()
root=Path(a.root)
analytical=-100.0*100.0**3/(3.0*210000.0*(10.0*10.0**3/12.0))

# C9.83 acceptance is declared in code before the new ultra-fine solve is observed.
ACCEPT={
  'load_conservation_abs_N_max':1e-10,
  'last_step_relative_change_max':0.05,
  'ultrafine_error_vs_euler_bernoulli_max':0.02,
  'coarse_to_ultrafine_error_reduction_min':0.90,
  'observed_order_min':0.50,
  'observed_order_max':3.50,
}

def parse_dy(path):
    lines=Path(path).read_text(encoding='utf-8',errors='ignore').splitlines()
    values=[]; in_table=False
    for line in lines:
        s=line.strip()
        if re.search(r'\bDX\b.*\bDY\b.*\bDZ\b',s):
            in_table=True; continue
        if in_table:
            nums=re.findall(r'[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?',s)
            if len(nums)>=3:
                try: values.append(float(nums[-2]))
                except ValueError: pass
            elif values and not s:
                break
    if not values: raise RuntimeError(f'No DY values parsed from {path}')
    return values

def sha_file(path):
    import hashlib
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

obs=[]
for name in a.cases:
    d=root/name
    meta=json.loads((d/f'{name}.json').read_text())
    resu=d/f'{name}.resu'; mess=d/f'{name}.mess'; rmed=d/f'{name}.rmed'; mail=d/f'{name}.mail'; comm=d/f'{name}.comm'
    vals=parse_dy(resu); mean=sum(vals)/len(vals); err=abs(mean-analytical)/abs(analytical)
    text=mess.read_text(encoding='utf-8',errors='ignore')
    obs.append({
      'name':name,'nx':meta['nx'],'ny':meta['ny'],'nz':meta['nz'],'nodes':meta['nodes'],'elements':meta['elements'],
      'intended_fixed_nodes':meta['fixed_nodes'],'mail_fixed_nodes':meta.get('mail_fixed_nodes'),
      'intended_load_nodes':meta['load_nodes'],'mail_load_nodes':meta.get('mail_load_nodes'),
      'load_per_node_N':meta['load_per_node_N'],'applied_total_load_N':meta.get('applied_total_load_N'),
      'load_conservation_error_N':meta.get('load_conservation_error_N'),
      'sampled_tip_nodes':len(vals),'mean_tip_dy_mm':mean,'free_face_spread_mm':max(vals)-min(vals),
      'relative_error_vs_analytical':err,'normal_stop':'ARRET NORMAL' in text,
      'rmed_bytes':rmed.stat().st_size if rmed.exists() else 0,
      'input_sha256':{'mail':sha_file(mail),'comm':sha_file(comm)}
    })

checks=[]
def ck(name,passed,evidence): checks.append({'name':name,'pass':bool(passed),'evidence':evidence})
for o in obs:
    ck(f"{o['name']}_normal_stop",o['normal_stop'],o['normal_stop'])
    ck(f"{o['name']}_rmed_nonempty",o['rmed_bytes']>0,o['rmed_bytes'])
    ck(f"{o['name']}_fixed_group_preserved",o['mail_fixed_nodes']==o['intended_fixed_nodes'],[o['mail_fixed_nodes'],o['intended_fixed_nodes']])
    ck(f"{o['name']}_load_group_preserved",o['mail_load_nodes']==o['intended_load_nodes'],[o['mail_load_nodes'],o['intended_load_nodes']])
    ck(f"{o['name']}_probe_matches_load_group",o['sampled_tip_nodes']==o['intended_load_nodes'],[o['sampled_tip_nodes'],o['intended_load_nodes']])
    ck(f"{o['name']}_total_load_conserved",o['applied_total_load_N'] is not None and abs(o['applied_total_load_N']+100.0)<=ACCEPT['load_conservation_abs_N_max'],o['applied_total_load_N'])

ck('four_refinement_levels',len(obs)==4,len(obs))
ck('mesh_size_strictly_increases',all(obs[i+1]['elements']>obs[i]['elements'] for i in range(len(obs)-1)),[o['elements'] for o in obs])
ck('errors_strictly_decrease',all(obs[i+1]['relative_error_vs_analytical']<obs[i]['relative_error_vs_analytical'] for i in range(len(obs)-1)),[o['relative_error_vs_analytical'] for o in obs])

last_change=abs(obs[-1]['mean_tip_dy_mm']-obs[-2]['mean_tip_dy_mm'])/abs(obs[-1]['mean_tip_dy_mm'])
reduction=(obs[0]['relative_error_vs_analytical']-obs[-1]['relative_error_vs_analytical'])/obs[0]['relative_error_vs_analytical']
ck('fine_to_ultrafine_change_le_5pct',last_change<=ACCEPT['last_step_relative_change_max'],last_change)
ck('ultrafine_error_vs_euler_bernoulli_le_2pct',obs[-1]['relative_error_vs_analytical']<=ACCEPT['ultrafine_error_vs_euler_bernoulli_max'],obs[-1]['relative_error_vs_analytical'])
ck('coarse_to_ultrafine_error_reduction_ge_90pct',reduction>=ACCEPT['coarse_to_ultrafine_error_reduction_min'],reduction)

# Uniform refinement factor r=2 in x,y,z. Estimate p from the three finest displacement values.
r=2.0
phi1=obs[-3]['mean_tip_dy_mm']; phi2=obs[-2]['mean_tip_dy_mm']; phi3=obs[-1]['mean_tip_dy_mm']
d12=abs(phi1-phi2); d23=abs(phi2-phi3)
p_obs=math.log(d12/d23)/math.log(r) if d12>0 and d23>0 else float('nan')
ck('observed_order_finite_positive',math.isfinite(p_obs) and ACCEPT['observed_order_min']<=p_obs<=ACCEPT['observed_order_max'],p_obs)

richardson=None; gci=None
if math.isfinite(p_obs) and p_obs>0 and abs(r**p_obs-1.0)>1e-15:
    richardson=phi3+(phi3-phi2)/(r**p_obs-1.0)
    gci=1.25*abs((phi3-phi2)/phi3)/(r**p_obs-1.0)

report={
  'release':'C9.83','benchmark_id':'B02-FOUR-LEVEL-CONVERGENCE-CERTIFICATION',
  'solver_execution':'RUN','unit_system':'mm-N-MPa',
  'scientific_integrity':{'fea_values_invented':False,'tolerances_relaxed_after_failure':False,'previous_c982_5pct_gate_retained':True},
  'analytical_tip_dy_mm':analytical,'predeclared_acceptance':ACCEPT,'observations':obs,
  'last_step_relative_change':last_change,'coarse_to_ultrafine_error_reduction':reduction,
  'observed_order_p':p_obs,'richardson_extrapolated_tip_dy_mm':richardson,'gci_ultrafine_fraction':gci,
  'checks_total':len(checks),'checks_passed':sum(c['pass'] for c in checks),'all_checks_pass':all(c['pass'] for c in checks),'checks':checks,
  'ansys_equivalence':'NOT_PROVEN','ansys_reference_present':False
}
(root/'C9.83-CONVERGENCE-CERTIFICATION.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
sys.exit(0 if report['all_checks_pass'] else 1)
