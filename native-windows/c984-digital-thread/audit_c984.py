from pathlib import Path
import argparse, hashlib, json, re, sys

SCHEMA='astermax-solver-evidence/v1'
UNITS={'length':'mm','force':'N','stress':'MPa'}

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def canonical_sha(obj):
    raw=json.dumps(obj,sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(raw).hexdigest()

def parse_group(lines,name):
    head=re.compile(r'^GROUP_NO\s+NOM\s*=\s*'+re.escape(name)+r'\s*$',re.I)
    for i,line in enumerate(lines):
        if head.match(line.strip()):
            ids=[]
            for raw in lines[i+1:]:
                if raw.strip().upper()=='FINSF': return ids
                ids += [int(x[1:]) for x in re.findall(r'\bN\d+\b',raw,re.I)]
    raise RuntimeError(f'GROUP_NO {name} missing')

def parse_mail(path):
    lines=path.read_text(encoding='utf-8').splitlines()
    nodes=[]; elems=[]; mode=None
    for raw in lines:
        s=raw.strip(); u=s.upper()
        if u=='COOR_3D': mode='nodes'; continue
        if u=='HEXA8': mode='elems'; continue
        if u in ('FINSF','FIN'):
            mode=None; continue
        if mode=='nodes' and re.match(r'^N\d+\s',s,re.I): nodes.append(int(s.split()[0][1:]))
        if mode=='elems' and re.match(r'^E\d+\s',s,re.I): elems.append(int(s.split()[0][1:]))
    fixed=parse_group(lines,'FIXED'); load=parse_group(lines,'LOAD')
    return {'nodes':len(nodes),'elements':len(elems),'fixed_nodes':len(fixed),'load_nodes':len(load),
            'fixed_group_sha256':canonical_sha(fixed),'load_group_sha256':canonical_sha(load)}

def parse_comm(path):
    s=path.read_text(encoding='utf-8')
    em=re.search(r'ELAS=_F\(E=([-+0-9.eE]+),NU=([-+0-9.eE]+)\)',s)
    fm=re.search(r"FORCE_NODALE=_F\(GROUP_NO='LOAD',FY=([-+0-9.eE]+)\)",s)
    bc=bool(re.search(r"GROUP_NO='FIXED'.*DX=0\.0,DY=0\.0,DZ=0\.0",s))
    if not em or not fm: raise RuntimeError('Material or nodal load not parseable')
    return {'E_MPa':float(em.group(1)),'nu':float(em.group(2)),'load_per_node_N':float(fm.group(1)),
            'fixed_xyz_zero':bc,'modelisation_3D':"MODELISATION='3D'" in s,'solver':'MECA_STATIQUE' if 'MECA_STATIQUE' in s else 'UNKNOWN'}

def file_record(path): return {'path':path.name,'bytes':path.stat().st_size,'sha256':sha256(path)}

def build(case_dir,name):
    mail=case_dir/f'{name}.mail'; comm=case_dir/f'{name}.comm'; export=case_dir/f'{name}.export'; meta_path=case_dir/f'{name}.json'
    for p in (mail,comm,export,meta_path):
        if not p.exists(): raise RuntimeError(f'Missing input {p}')
    mesh=parse_mail(mail); deck=parse_comm(comm); meta=json.loads(meta_path.read_text())
    total=deck['load_per_node_N']*mesh['load_nodes']
    contract={'benchmark':'B02-CANTILEVER','units':UNITS,'geometry_mm':{'L':100.0,'H':10.0,'W':10.0},
              'material':{'E_MPa':deck['E_MPa'],'nu':deck['nu']},'mesh':mesh,
              'boundary_conditions':{'FIXED_xyz_zero':deck['fixed_xyz_zero']},
              'loads':{'LOAD_FY_per_node_N':deck['load_per_node_N'],'LOAD_total_FY_N':total},
              'analysis':{'modelisation_3D':deck['modelisation_3D'],'solver':deck['solver']}}
    inputs=[file_record(x) for x in (mail,comm,export,meta_path)]
    outputs=[]
    for suffix in ('mess','resu','rmed'):
        p=case_dir/f'{name}.{suffix}'
        if not p.exists() or p.stat().st_size==0: raise RuntimeError(f'Missing/non-empty solver output required: {p}')
        outputs.append(file_record(p))
    mess=(case_dir/f'{name}.mess').read_text(encoding='utf-8',errors='ignore')
    if 'ARRET NORMAL' not in mess: raise RuntimeError('Code_Aster normal-stop evidence missing')
    checks={
      'units_mm_N_MPa':meta.get('units')=='mm-N-MPa',
      'mesh_counts_match_generator':mesh['nodes']==meta.get('nodes') and mesh['elements']==meta.get('elements'),
      'fixed_group_count_matches_generator':mesh['fixed_nodes']==meta.get('fixed_nodes'),
      'load_group_count_matches_generator':mesh['load_nodes']==meta.get('load_nodes'),
      'total_load_conserved':abs(total-float(meta.get('total_load_N',999)))<=1e-10,
      'fixed_xyz_zero':deck['fixed_xyz_zero'],
      'static_3d':deck['modelisation_3D'] and deck['solver']=='MECA_STATIQUE',
      'normal_stop':True,
      'rmed_nonempty':next(x['bytes'] for x in outputs if x['path'].endswith('.rmed'))>0
    }
    if not all(checks.values()): raise RuntimeError('Semantic audit failed: '+json.dumps(checks))
    evidence={'schema':SCHEMA,'release':'C9.84','scope':'benchmark-contract -> Code_Aster deck -> solver outputs',
      'native_femodel_contract_status':'NOT_YET_WIRED','scientific_integrity':{'fea_values_invented':False,'ansys_values_invented':False},
      'contract':contract,'checks':checks,'input_files':inputs,'output_files':outputs}
    evidence['model_contract_sha256']=canonical_sha(contract)
    evidence['solver_input_bundle_sha256']=canonical_sha(inputs)
    evidence['result_bundle_sha256']=canonical_sha(outputs)
    return evidence

def verify(manifest_path,case_dir):
    m=json.loads(manifest_path.read_text())
    errors=[]
    if m.get('schema')!=SCHEMA: errors.append('schema')
    if canonical_sha(m.get('contract'))!=m.get('model_contract_sha256'): errors.append('contract_hash')
    for section in ('input_files','output_files'):
        for rec in m.get(section,[]):
            p=case_dir/rec['path']
            if not p.exists(): errors.append('missing:'+rec['path']); continue
            if p.stat().st_size!=rec['bytes']: errors.append('bytes:'+rec['path'])
            if sha256(p)!=rec['sha256']: errors.append('sha256:'+rec['path'])
    if canonical_sha(m.get('input_files'))!=m.get('solver_input_bundle_sha256'): errors.append('input_bundle_hash')
    if canonical_sha(m.get('output_files'))!=m.get('result_bundle_sha256'): errors.append('result_bundle_hash')
    return errors

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('create'); c.add_argument('--case-dir',required=True); c.add_argument('--name',required=True); c.add_argument('--out',required=True)
    v=sub.add_parser('verify'); v.add_argument('--case-dir',required=True); v.add_argument('--manifest',required=True)
    a=ap.parse_args()
    if a.cmd=='create':
        m=build(Path(a.case_dir),a.name); Path(a.out).write_text(json.dumps(m,indent=2),encoding='utf-8'); print(json.dumps(m,indent=2)); return 0
    errors=verify(Path(a.manifest),Path(a.case_dir)); print(json.dumps({'verified':not errors,'errors':errors},indent=2)); return 0 if not errors else 2
if __name__=='__main__': sys.exit(main())
