from pathlib import Path
import argparse, json, math, re, sys

p=argparse.ArgumentParser(); p.add_argument('--root',required=True); p.add_argument('--cases',nargs='+',required=True); a=p.parse_args()
root=Path(a.root)
analytical=-100.0*100.0**3/(3.0*210000.0*(10.0*10.0**3/12.0))

def parse_dy(path):
    lines=Path(path).read_text(encoding='utf-8',errors='ignore').splitlines()
    values=[]; in_table=False
    for line in lines:
        s=line.strip()
        if re.search(r'\bDX\b.*\bDY\b.*\bDZ\b',s): in_table=True; continue
        if in_table:
            nums=re.findall(r'[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?',s)
            if len(nums)>=3:
                try: values.append(float(nums[-2]))
                except: pass
            elif values and not s: break
    if not values: raise RuntimeError(f'No DY values parsed from {path}')
    return values

obs=[]
for name in a.cases:
    meta=json.loads((root/name/f'{name}.json').read_text())
    resu=root/name/f'{name}.resu'; mess=root/name/f'{name}.mess'; rmed=root/name/f'{name}.rmed'
    vals=parse_dy(resu); mean=sum(vals)/len(vals); err=abs(mean-analytical)/abs(analytical)
    text=mess.read_text(encoding='utf-8',errors='ignore')
    obs.append({'name':name,'elements':meta['elements'],'nodes':meta['nodes'],'mean_tip_dy_mm':mean,'relative_error_vs_analytical':err,'free_face_spread_mm':max(vals)-min(vals),'normal_stop':'ARRET NORMAL' in text,'rmed_bytes':rmed.stat().st_size if rmed.exists() else 0})

checks=[]
def ck(name,passed,evidence): checks.append({'name':name,'pass':bool(passed),'evidence':evidence})
for o in obs:
    ck(f"{o['name']}_normal_stop",o['normal_stop'],str(o['normal_stop']))
    ck(f"{o['name']}_rmed_nonempty",o['rmed_bytes']>0,str(o['rmed_bytes']))
ck('mesh_size_strictly_increases',all(obs[i+1]['elements']>obs[i]['elements'] for i in range(len(obs)-1)),[o['elements'] for o in obs])
ck('error_reduces_coarse_to_fine',obs[-1]['relative_error_vs_analytical'] < obs[0]['relative_error_vs_analytical'],[o['relative_error_vs_analytical'] for o in obs])
reduction=(obs[0]['relative_error_vs_analytical']-obs[-1]['relative_error_vs_analytical'])/obs[0]['relative_error_vs_analytical'] if obs[0]['relative_error_vs_analytical'] else 0
ck('error_reduction_at_least_50pct',reduction>=0.50,reduction)
change=abs(obs[-1]['mean_tip_dy_mm']-obs[-2]['mean_tip_dy_mm'])/abs(obs[-1]['mean_tip_dy_mm'])
ck('medium_to_fine_change_le_5pct',change<=0.05,change)
ck('fine_error_vs_euler_bernoulli_le_5pct',obs[-1]['relative_error_vs_analytical']<=0.05,obs[-1]['relative_error_vs_analytical'])
report={'release':'C9.82','benchmark_id':'B02-MESH-CONVERGENCE','solver_execution':'RUN','unit_system':'mm-N-MPa','scientific_integrity':{'fea_values_invented':False,'analytical_values_are_fea_output':False},'analytical_tip_dy_mm':analytical,'predeclared_acceptance':{'error_reduction_coarse_to_fine_min':0.50,'medium_to_fine_relative_change_max':0.05,'fine_error_vs_euler_bernoulli_max':0.05},'observations':obs,'error_reduction_fraction':reduction,'medium_to_fine_relative_change':change,'checks_total':len(checks),'checks_passed':sum(c['pass'] for c in checks),'all_checks_pass':all(c['pass'] for c in checks),'checks':checks}
(root/'C9.82-CONVERGENCE-EVIDENCE.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
sys.exit(0 if report['all_checks_pass'] else 1)
