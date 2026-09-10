import argparse, json, re, hashlib, sys
from pathlib import Path

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm_id(s):
    s=str(s).strip(); m=re.fullmatch(r'[NM](\d+)',s,re.I)
    return int(m.group(1)) if m else int(s)

def parse_mail(path):
    lines=[x.strip() for x in Path(path).read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    nodes={}; elems={}; groups={}; i=0
    while i<len(lines):
        t=lines[i]
        if t=='COOR_3D':
            i+=1
            while i<len(lines) and lines[i]!='FINSF':
                p=lines[i].split(); nodes[norm_id(p[0])]=tuple(float(v.replace('D','E')) for v in p[1:4]); i+=1
        elif t=='HEXA8':
            i+=1
            while i<len(lines) and lines[i]!='FINSF':
                p=lines[i].split(); elems[norm_id(p[0])]=tuple(norm_id(v) for v in p[1:9]); i+=1
        elif t=='GROUP_NO':
            i+=1; p=lines[i].replace('=',' = ').split(); ids=[]
            if len(p)>=3 and p[0].upper()=='NOM' and p[1]=='=': name=p[2]; i+=1
            else: name=p[0]; ids += [norm_id(v) for v in p[1:]]; i+=1
            while i<len(lines) and lines[i]!='FINSF': ids += [norm_id(v) for v in lines[i].split()]; i+=1
            groups[name]=tuple(ids)
        i+=1
    return nodes, elems, groups

def close(a,b,tol=1e-10): return abs(a-b)<=tol*max(1.0,abs(a),abs(b))
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--model',required=True); ap.add_argument('--mail',required=True); ap.add_argument('--comm',required=True); ap.add_argument('--adapter',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    model=json.loads(Path(a.model).read_text(encoding='utf-8-sig')); adapter=json.loads(Path(a.adapter).read_text(encoding='utf-8-sig')); comm=Path(a.comm).read_text(encoding='utf-8-sig')
    nodes,elems,groups=parse_mail(a.mail)
    en={int(n['id']):(float(n['x']),float(n['y']),float(n['z'])) for n in model['mesh']['nodes']}; ee={int(e['id']):tuple(int(x) for x in e['nodes']) for e in model['mesh']['elements']}; eg={k:tuple(int(x) for x in v) for k,v in model['mesh']['node_groups'].items()}
    mat=model['materials'][0]; sup=model['supports'][0]; load=model['loads'][0]; ln=eg[load['group']]; fx=float(load['fx_total_n'])/len(ln); fy=float(load['fy_total_n'])/len(ln); fz=float(load['fz_total_n'])/len(ln)
    em=re.search(r'ELAS\s*=\s*_F\s*\(\s*E\s*=\s*([-+0-9.EeDd]+)\s*,\s*NU\s*=\s*([-+0-9.EeDd]+)',comm,re.I|re.S)
    lm=re.search(r"FORCE_NODALE\s*=\s*_F\s*\(\s*GROUP_NO='([^']+)'\s*,\s*FX=([-+0-9.EeDd]+)\s*,\s*FY=([-+0-9.EeDd]+)\s*,\s*FZ=([-+0-9.EeDd]+)",comm,re.I|re.S)
    bm=re.search(r"DDL_IMPO\s*=\s*_F\s*\(\s*GROUP_NO='([^']+)'\s*,\s*DX=([-+0-9.EeDd]+)\s*,\s*DY=([-+0-9.EeDd]+)\s*,\s*DZ=([-+0-9.EeDd]+)",comm,re.I|re.S)
    c={}
    c['unit_contract']=model.get('unit_system')=='MM_N_S_MPA' and adapter.get('unit_system')=='MM_N_S_MPA'; c['static_3d']='MECA_STATIQUE' in comm and "MODELISATION='3D'" in comm
    c['nodes_exact']=nodes==en; c['elements_exact']=elems==ee; c['groups_exact']=groups==eg
    c['material_exact']=bool(em) and close(float(em.group(1)),float(mat['young_modulus_mpa'])) and close(float(em.group(2)),float(mat['poisson']))
    c['fixed_bc_exact']=bool(bm) and bm.group(1)==sup['group'] and all(close(float(bm.group(i)),float(v)) for i,v in zip((2,3,4),(sup['dx'],sup['dy'],sup['dz'])))
    c['nodal_load_exact']=bool(lm) and lm.group(1)==load['group'] and all(close(float(lm.group(i)),v) for i,v in zip((2,3,4),(fx,fy,fz)))
    c['total_load_conserved']=bool(lm) and all(close(float(lm.group(i))*len(ln),float(v)) for i,v in zip((2,3,4),(load['fx_total_n'],load['fy_total_n'],load['fz_total_n'])))
    c['adapter_hashes']=adapter.get('mail_sha256')==sha(a.mail) and adapter.get('comm_sha256')==sha(a.comm)
    c['no_solver_claim']=adapter.get('solver_execution')=='NOT_RUN' and adapter.get('result_claim')=='NONE'
    report={'schema':'astermax-c987-production-export-fidelity/v1','passed':all(c.values()),'checks':c,'hashes':{'model':sha(a.model),'mail':sha(a.mail),'comm':sha(a.comm),'adapter':sha(a.adapter)},'scope':{'exporter':'native-windows/Export-AsterMaxCodeAster.ps1','solver_run':'NOT_RUN','fea_result_claim':'NONE','section_semantics':'HEXA8 solid: no separate shell/beam section required'},'known_gap':'Native FeModel material-object extraction is not yet wired into the production contract.'}
    Path(a.out).write_text(json.dumps(report,indent=2,sort_keys=True),encoding='utf-8'); print(json.dumps(report,indent=2)); return 0 if report['passed'] else 2
if __name__=='__main__': sys.exit(main())
