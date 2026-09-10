#!/usr/bin/env python3
import argparse, json, re, hashlib, sys
from pathlib import Path

def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def parse_mail(path):
    lines=[x.strip() for x in Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]
    nodes={}; elems={}; groups={}; mode=None; gname=None
    i=0
    while i < len(lines):
        s=lines[i]
        if s=='COOR_3D': mode='nodes'; i+=1; continue
        if s=='HEXA8': mode='elems'; i+=1; continue
        if s=='FINSF': mode=None; i+=1; continue
        if s.startswith('GROUP_NO'):
            m=re.search(r'NOM\s*=\s*([^\s]+)',s); gname=m.group(1) if m else None; mode='group'; groups[gname]=[]; i+=1; continue
        if s=='FIN': break
        if mode=='nodes':
            p=s.split(); nodes[int(p[0].lstrip('Nn'))]=[float(p[1]),float(p[2]),float(p[3])]
        elif mode=='elems':
            p=s.split(); elems[int(p[0].lstrip('Mm'))]=[int(x.lstrip('Nn')) for x in p[1:9]]
        elif mode=='group' and gname:
            groups[gname].extend(int(x.lstrip('Nn')) for x in s.split())
        i+=1
    return {'nodes':nodes,'elements':elems,'groups':{k:sorted(v) for k,v in groups.items()}}

def parse_comm(path):
    t=Path(path).read_text(encoding='utf-8')
    analysis='MECA_STATIQUE' if 'MECA_STATIQUE' in t else 'UNKNOWN'
    model='3D' if re.search(r"MODELISATION\s*=\s*['\"]3D['\"]",t) else 'UNKNOWN'
    fixed=[]
    for m in re.finditer(r"DDL_IMPO\s*=\s*_F\((.*?)\)",t,re.S):
        b=m.group(1); g=re.search(r"GROUP_NO\s*=\s*['\"]([^'\"]+)",b)
        if g and all(re.search(rf"{d}\s*=\s*0(?:\.0+)?",b) for d in ('DX','DY','DZ')): fixed.append(g.group(1))
    loads=[]
    for m in re.finditer(r"FORCE_NODALE\s*=\s*_F\((.*?)\)",t,re.S):
        b=m.group(1); g=re.search(r"GROUP_NO\s*=\s*['\"]([^'\"]+)",b)
        if not g: continue
        comp={k:float(v) for k,v in re.findall(r"(FX|FY|FZ)\s*=\s*([-+0-9.eE]+)",b)}
        loads.append({'group':g.group(1),'fx':comp.get('FX',0.0),'fy':comp.get('FY',0.0),'fz':comp.get('FZ',0.0)})
    return {'analysis':analysis,'modelisation':model,'fixed_groups':sorted(fixed),'loads':loads}

def norm_nodes(d): return {int(k):[round(float(x),12) for x in v] for k,v in d.items()}
def norm_elems(d): return {int(k):[int(x) for x in v] for k,v in d.items()}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--native',required=True); ap.add_argument('--mail',required=True); ap.add_argument('--comm',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    n=json.loads(Path(a.native).read_text(encoding='utf-8')); m=parse_mail(a.mail); c=parse_comm(a.comm)
    checks={}
    checks['units_mm_n_mpa']=n.get('units')=='mm-N-MPa'
    checks['nodes_equal']=norm_nodes(n['nodes'])==norm_nodes(m['nodes'])
    checks['connectivity_equal']=norm_elems(n['elements'])==norm_elems(m['elements'])
    checks['fixed_group_equal']=sorted(n['groups']['FIXED'])==m['groups'].get('FIXED',[])
    checks['load_group_equal']=sorted(n['groups']['LOAD'])==m['groups'].get('LOAD',[])
    checks['analysis_equal']=c['analysis']==n.get('analysis')=='MECA_STATIQUE'
    checks['modelisation_equal']=c['modelisation']==n.get('modelisation')=='3D'
    checks['fixed_bc_equal']=c['fixed_groups']==['FIXED']
    exp=n['load']; got=c['loads'][0] if len(c['loads'])==1 else {}
    checks['load_vector_equal']=got.get('group')=='LOAD' and all(abs(got.get(k,9e99)-float(exp[k]))<=1e-12 for k in ('fx','fy','fz'))
    out={'release':'C9.86','title':'FeModel to Code_Aster Semantic Equivalence Gate','checks':checks,'passed':sum(bool(x) for x in checks.values()),'total':len(checks),'pass':all(checks.values()),'native_manifest_sha256':sha256(a.native),'mail_sha256':sha256(a.mail),'comm_sha256':sha256(a.comm),'truth_boundary':'Validates independent semantic reconstruction for units contract, nodes, HEXA8 connectivity, FIXED/LOAD groups, 3D static analysis, fixed XYZ BC and nodal load vector. Physical material constants/sections and automatic production exporter wiring remain NOT_YET_WIRED.','fea_values_invented':False,'fresh_solver_run':'NOT_RUN'}
    Path(a.out).write_text(json.dumps(out,indent=2),encoding='utf-8'); print(json.dumps(out,indent=2)); return 0 if out['pass'] else 2
if __name__=='__main__': sys.exit(main())
