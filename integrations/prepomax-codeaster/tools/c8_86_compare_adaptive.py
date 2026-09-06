#!/usr/bin/env python3
import hashlib, json, math, pathlib, re, sys
root=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else 'artifact/c8-86')
ref_root=pathlib.Path(sys.argv[2] if len(sys.argv)>2 else 'artifact/c8-83-ref')

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def table(text,marker,header):
    pos=text.find(marker)
    if pos<0: raise SystemExit('missing '+marker)
    lines=text[pos:].splitlines(); key=';'.join(header); hi=next((i for i,l in enumerate(lines) if l.strip()==key),None)
    if hi is None: raise SystemExit('missing header '+marker)
    rows={}
    for line in lines[hi+1:]:
        if rows and (not line.strip() or line.startswith('PPM_') or 'ASTER 17.' in line): break
        p=[x.strip() for x in line.split(';')]
        if len(p)!=len(header):
            if rows: break
            continue
        try: n=int(p[0]); vals=[float(x.replace('D','E')) for x in p[1:]]
        except ValueError:
            if rows: break
            continue
        if not all(math.isfinite(x) for x in vals): raise SystemExit(f'nonfinite {marker} at {n}')
        rows[n]=vals
    if not rows: raise SystemExit('empty '+marker)
    return rows

def parse_case(study, traction_ev):
    resu=study/'astermax_c862_static.resu'; mess=study/'astermax_c862_static.mess'; mail=study/'astermax_c862_static.mail'; rmed=study/'astermax_c862_static.rmed'
    for p in (resu,mess,mail,rmed):
        if not p.is_file() or p.stat().st_size==0: raise SystemExit('missing '+str(p))
    if re.search(r'<F>|ERREUR FATALE|FATAL_ERROR',mess.read_text(errors='replace'),re.I): raise SystemExit('solver fatal '+str(study))
    text=resu.read_text(errors='replace'); depl=table(text,'PPM_DEPL',['NOEUD','DX','DY','DZ']); sn=table(text,'PPM_STRESS_N',['NOEUD','SIXX','SIYY','SIZZ']); ss=table(text,'PPM_STRESS_S',['NOEUD','SIXY','SIYZ','SIXZ']); reac=table(text,'PPM_REACTION',['NOEUD','DX','DY','DZ'])
    disp={n:math.sqrt(sum(x*x for x in v)) for n,v in depl.items()}; un=max(disp,key=disp.get)
    def vm(n):
        sx,sy,sz=sn[n]; xy,yz,xz=ss[n]
        return math.sqrt(.5*((sx-sy)**2+(sy-sz)**2+(sz-sx)**2)+3*(xy*xy+yz*yz+xz*xz))
    mises={n:vm(n) for n in set(sn).intersection(ss)}; vn=max(mises,key=mises.get)
    tev=json.loads(traction_ev.read_text()); resultant=float(tev['integrated_resultant_n']); reaction=[sum(v[i] for v in reac.values()) for i in range(3)]; residual=[reaction[0]+resultant,reaction[1],reaction[2]]; rnorm=math.sqrt(sum(x*x for x in residual))
    if rnorm>1e-3: raise SystemExit(f'reaction residual {rnorm} N')
    return {'nodes':len(depl),'umax_mm':disp[un],'umax_node':un,'mises_max_mpa':mises[vn],'mises_max_node':vn,'reaction_residual_n':rnorm,'resu_sha256':sha(resu),'rmed_sha256':sha(rmed),'mail_sha256':sha(mail)}

family=json.loads((root/'C8.86_MESH_FAMILY.json').read_text(encoding='utf-8-sig'))
if not family.get('consumer_multi_roi_refinement_verified'): raise SystemExit('mesh refinement not verified')
base=parse_case(root/'baseline'/'study',root/'baseline'/'C8.86_SURFACE_TRACTION.json')
adapt=parse_case(root/'adaptive'/'study',root/'adaptive'/'C8.86_SURFACE_TRACTION.json')
refq=json.loads((ref_root/'C8.83_CONVERGENCE_QUALIFICATION.json').read_text(encoding='utf-8-sig'))
ref=next(x for x in refq['levels'] if x['name']=='fine')
ref_u=float(ref['disp_max_mm']); ref_s=float(ref['mises_max_mpa']); ref_e=int(ref['elements'])
base_e=int(next(x for x in family['levels'] if x['name']=='baseline')['elements']); adapt_e=int(next(x for x in family['levels'] if x['name']=='adaptive')['elements'])
rel=lambda a,b:abs(a-b)/max(abs(b),1e-30)
beu=rel(base['umax_mm'],ref_u); aeu=rel(adapt['umax_mm'],ref_u); bes=rel(base['mises_max_mpa'],ref_s); aes=rel(adapt['mises_max_mpa'],ref_s)
ev={'schema':'astermax.c8.86.multi-roi-adaptive-qualification.v1','solver':'Code_Aster 17.4.0','unit_system':'mm-N-MPa','baseline_global_maxh_mm':40.0,'adaptive_global_maxh_mm':40.0,'adaptive_local_h_mm':12.0,'baseline':base,'adaptive':adapt,'reference_global25':{'elements':ref_e,'umax_mm':ref_u,'mises_max_mpa':ref_s,'source_workflow':34033613470},'baseline_errors_vs_global25':{'umax_relative':beu,'mises_relative':bes},'adaptive_errors_vs_global25':{'umax_relative':aeu,'mises_relative':aes},'adaptive_elements':adapt_e,'baseline_elements':base_e,'global25_reference_elements':ref_e,'dof_proxy_reduction_vs_global25':1-adapt_e/ref_e,'adaptive_mesh_is_local_not_global':adapt_e<ref_e,'umax_accuracy_improved':aeu<beu,'mises_accuracy_improved':aes<bes,'reaction_balance_verified':base['reaction_residual_n']<=1e-3 and adapt['reaction_residual_n']<=1e-3,'consumer_multi_roi_refinement_verified':True,'native_femeshrefinement_binding_verified':False,'mesh_adaptation_verified':True,'industrial_validation':False,'ansys_equivalence':False}
ev['adaptive_efficiency_admitted']=ev['adaptive_mesh_is_local_not_global'] and ev['umax_accuracy_improved'] and ev['mises_accuracy_improved'] and ev['reaction_balance_verified']
(root/'C8.86_ADAPTIVE_QUALIFICATION.json').write_text(json.dumps(ev,indent=2),encoding='utf-8')
print(json.dumps(ev,indent=2))
