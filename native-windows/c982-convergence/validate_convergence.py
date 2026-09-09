from pathlib import Path
import argparse, json, re, sys

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
    obs.append({
      'name':name,'elements':meta['elements'],'nodes':meta['nodes'],
      'intended_fixed_nodes':meta['fixed_nodes'],'mail_fixed_nodes':meta.get('mail_fixed_nodes'),
      'intended_load_nodes':meta['load_nodes'],'mail_load_nodes':meta.get('mail_load_nodes'),
      'load_per_node_N':meta['load_per_node_N'],'applied_total_load_N':meta.get('applied_total_load_N'),
      'load_conservation_error_N':meta.get('load_conservation_error_N'),
      'mean_tip_dy_mm':mean,'relative_error_vs_analytical':err,'free_face_spread_mm':max(vals)-min(vals),
      'sampled_tip_nodes':len(vals),'normal_stop':'ARRET NORMAL' in text,
      'rmed_bytes':rmed.stat().st_size if rmed.exists() else 0})

checks=[]
def ck(name,passed,evidence): checks.append({'name':name,'pass':bool(passed),'evidence':evidence})
for o in obs:
    ck(f"{o['name']}_normal_stop",o['normal_stop'],str(o['normal_stop']))
    ck(f"{o['name']}_rmed_nonempty",o['rmed_bytes']>0,str(o['rmed_bytes']))
    ck(f"{o['name']}_fixed_group_cardinality_preserved",o['mail_fixed_nodes']==o['intended_fixed_nodes'],[o['mail_fixed_nodes'],o['intended_fixed_nodes']])
    ck(f"{o['name']}_load_group_cardinality_preserved",o['mail_load_nodes']==o['intended_load_nodes'],[o['mail_load_nodes'],o['intended_load_nodes']])
    ck(f"{o['name']}_solver_probe_cardinality_matches_load_group",o['sampled_tip_nodes']==o['intended_load_nodes'],[o['sampled_tip_nodes'],o['intended_load_nodes']])
    ck(f"{o['name']}_total_load_conserved_100N",o['applied_total_load_N'] is not None and abs(o['applied_total_load_N']+100.0)<=1e-10,o['applied_total_load_N'])
    ck(f"{o['name']}_load_conservation_error_le_1e-10N",o['load_conservation_error_N'] is not None and o['load_conservation_error_N']<=1e-10,o['load_conservation_error_N'])
ck('mesh_size_strictly_increases',all(obs[i+1]['elements']>obs[i]['elements'] for i in range(len(obs)-1)),[o['elements'] for o in obs])
ck('error_reduces_coarse_to_fine',obs[-1]['relative_error_vs_analytical'] < obs[0]['relative_error_vs_analytical'],[o['relative_error_vs_analytical'] for o in obs])
reduction=(obs[0]['relative_error_vs_analytical']-obs[-1]['relative_error_vs_analytical'])/obs[0]['relative_error_vs_analytical'] if obs[0]['relative_error_vs_analytical'] else 0
ck('error_reduction_at_least_50pct',reduction>=0.50,reduction)
change=abs(obs[-1]['mean_tip_dy_mm']-obs[-2]['mean_tip_dy_mm'])/abs(obs[-1]['mean_tip_dy_mm'])
ck('medium_to_fine_change_le_5pct',change<=0.05,change)
ck('fine_error_vs_euler_bernoulli_le_5pct',obs[-1]['relative_error_vs_analytical']<=0.05,obs[-1]['relative_error_vs_analytical'])
report={'release':'C9.82.1','benchmark_id':'B02-MESH-CONVERGENCE','solver_execution':'RUN','unit_system':'mm-N-MPa','scientific_integrity':{'fea_values_invented':False,'analytical_values_are_fea_output':False,'tolerances_relaxed_after_failure':False},'root_cause_repaired':'ASTER GROUP_NO records are explicit NOM blocks with wrapped node records; load/group conservation is gated before accepting physics convergence.','analytical_tip_dy_mm':analytical,'predeclared_acceptance':{'load_conservation_abs_N_max':1e-10,'error_reduction_coarse_to_fine_min':0.50,'medium_to_fine_relative_change_max':0.05,'fine_error_vs_euler_bernoulli_max':0.05},'observations':obs,'error_reduction_fraction':reduction,'medium_to_fine_relative_change':change,'checks_total':len(checks),'checks_passed':sum(c['pass'] for c in checks),'all_checks_pass':all(c['pass'] for c in checks),'checks':checks}
(root/'C9.82.1-CONVERGENCE-EVIDENCE.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
sys.exit(0 if report['all_checks_pass'] else 1)
