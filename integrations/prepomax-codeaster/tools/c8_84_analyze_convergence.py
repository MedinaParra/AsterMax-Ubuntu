#!/usr/bin/env python3
import csv, hashlib, json, math, pathlib, re, sys
root=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else 'artifact/c8-84'); levels=['coarse','medium','fine']; requested={'coarse':25,'medium':18,'fine':14}
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
def mail_quality(path):
    lines=path.read_text(encoding='utf-8',errors='replace').splitlines(); nodes={};tets=[];mode=None
    for raw in lines:
        s=raw.strip()
        if s=='COOR_3D': mode='n';continue
        if s=='TETRA10': mode='t';continue
        if s in ('FINSF','FIN'): mode=None;continue
        p=s.split()
        if mode=='n' and len(p)>=4:
            try:nodes[p[0]]=tuple(float(x.replace('D','E')) for x in p[1:4])
            except:pass
        elif mode=='t' and len(p)>=11:tets.append(p[1:11])
    if not nodes or not tets:raise SystemExit('MAIL volume parse failed')
    q=[]; vols=[]
    for ids in tets:
        pts=[nodes[x] for x in ids[:4]];a,b,c,d=pts; sub=lambda x,y:tuple(x[i]-y[i] for i in range(3)); ab,ac,ad=sub(b,a),sub(c,a),sub(d,a)
        cr=(ac[1]*ad[2]-ac[2]*ad[1],ac[2]*ad[0]-ac[0]*ad[2],ac[0]*ad[1]-ac[1]*ad[0]); vol=abs(sum(ab[i]*cr[i] for i in range(3)))/6; vols.append(vol)
        es=sum(sum((pts[i][k]-pts[j][k])**2 for k in range(3)) for i in range(4) for j in range(i+1,4)); v=12*(3*vol)**(2/3)/es if vol>0 and es>0 else 0;q.append(v if math.isfinite(v) else 0)
    q.sort(); pct=lambda p:q[min(len(q)-1,max(0,int(round((len(q)-1)*p))))]
    return {'tetra10_count':len(tets),'mean_ratio_proxy_min':q[0],'mean_ratio_proxy_p05':pct(.05),'mean_ratio_proxy_median':pct(.5),'degenerate_corner_tets':sum(v<=1e-12 for v in vols)}
results=[]
for name in levels:
    d=root/name; study=d/'study'; evp=d/'C8.84_SURFACE_TRACTION.json'
    if not evp.is_file():raise SystemExit(name+': traction evidence missing')
    tev=json.loads(evp.read_text())
    if not tev.get('qualification_surface_transform_verified') or abs(tev.get('integrated_resultant_n',0)-1000)>1e-9:raise SystemExit(name+': resultant gate failed')
    resu=study/'astermax_c862_static.resu';comm=study/'astermax_c862_static.comm';mail=study/'astermax_c862_static.mail';mess=study/'astermax_c862_static.mess';rmed=study/'astermax_c862_static.rmed'
    for p in (resu,comm,mail,mess,rmed):
        if not p.is_file() or p.stat().st_size==0:raise SystemExit(f'{name}: missing {p.name}')
    if re.search(r'<F>|ERREUR FATALE|FATAL_ERROR',mess.read_text(errors='replace'),re.I):raise SystemExit(name+': solver fatal')
    ct=comm.read_text(errors='replace'); mm=re.search(r"FORCE_FACE=\(_F\(GROUP_MA=['\"]S_LOAD_XMAX['\"],\s*FX=([+\-0-9.eEdD]+)\)\)\",ct)
    if not mm:raise SystemExit(name+': FORCE_FACE contract missing')
    if abs(float(mm.group(1).replace('D','E'))-tev['traction_fx_mpa'])>1e-12:raise SystemExit(name+': traction COMM/evidence mismatch')
    text=resu.read_text(errors='replace'); depl=table(text,'PPM_DEPL',['NOEUD','DX','DY','DZ']);sn=table(text,'PPM_STRESS_N',['NOEUD','SIXX','SIYY','SIZZ']);ss=table(text,'PPM_STRESS_S',['NOEUD','SIXY','SIYZ','SIXZ']);reac=table(text,'PPM_REACTION',['NOEUD','DX','DY','DZ'])
    disp={n:math.sqrt(sum(x*x for x in v)) for n,v in depl.items()}; un=max(disp,key=disp.get)
    def vm(n):
        sx,sy,sz=sn[n];xy,yz,xz=ss[n];return math.sqrt(.5*((sx-sy)**2+(sy-sz)**2+(sz-sx)**2)+3*(xy*xy+yz*yz+xz*xz))
    mises={n:vm(n) for n in sn}; vn=max(mises,key=mises.get); reaction=[sum(v[i] for v in reac.values()) for i in range(3)]; resultant=tev['integrated_resultant_n']; residual=[reaction[0]+resultant,reaction[1],reaction[2]]; rnorm=math.sqrt(sum(x*x for x in residual))
    if rnorm>1e-3:raise SystemExit(f'{name}: reaction residual {rnorm} N')
    q=mail_quality(mail)
    if q['degenerate_corner_tets'] or q['mean_ratio_proxy_min']<=0:raise SystemExit(name+': degenerate mesh')
    results.append({'name':name,'requested_maxh_mm':requested[name],'nodes':len(depl),'elements':q['tetra10_count'],'surface_faces_tria6':tev['tria6_face_count'],'surface_area_mm2':tev['surface_area_mm2'],'traction_mpa':tev['traction_fx_mpa'],'integrated_resultant_n':resultant,'disp_max_mm':disp[un],'disp_max_node':un,'mises_max_mpa':mises[vn],'mises_max_node':vn,'reaction_sum_n':reaction,'equilibrium_residual_norm_n':rnorm,'reaction_equilibrium_verified':True,'mesh_quality_proxy':q,'mail_sha256':sha(mail),'comm_sha256':sha(comm),'rmed_sha256':sha(rmed),'resu_sha256':sha(resu)})
if not(results[0]['nodes']<results[1]['nodes']<results[2]['nodes'] and results[0]['elements']<results[1]['elements']<results[2]['elements']):raise SystemExit('mesh family not monotonic')
rel=lambda a,b:abs(b-a)/max(abs(b),1e-30);du=rel(results[1]['disp_max_mm'],results[2]['disp_max_mm']);ds=rel(results[1]['mises_max_mpa'],results[2]['mises_max_mpa']);tol=.05
ev={'schema':'astermax.c8.84a.budget-aware-fine-surface-traction-convergence.v1','solver':'Code_Aster 17.4.0','unit_system':'mm-N-MPa','load_contract':'uniform +X surface traction independently integrated to 1000 N','fine_mesh_strategy':'global MaxH 14 mm selected after 12 mm exceeded the 12-minute generation evidence budget; convergence gate remains unchanged at 5%','levels':results,'fine_pair_displacement_relative_change':du,'fine_pair_mises_relative_change':ds,'convergence_tolerance':tol,'displacement_convergence_admitted':du<=tol,'peak_mises_convergence_admitted':ds<=tol,'solution_convergence_admitted':du<=tol and ds<=tol,'all_reaction_balances_verified':True,'product_surface_traction_binding_verified':False,'qualification_surface_transform_verified':True,'industrial_validation':False,'ansys_equivalence':False}
(root/'C8.84_CONVERGENCE_QUALIFICATION.json').write_text(json.dumps(ev,indent=2),encoding='utf-8')
with (root/'C8.84_CONVERGENCE.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.writer(f);w.writerow(['level','maxh_mm','nodes','tetra10','surface_tria6','surface_area_mm2','traction_mpa','umax_mm','vmmax_mpa','reaction_residual_n']);[w.writerow([x['name'],x['requested_maxh_mm'],x['nodes'],x['elements'],x['surface_faces_tria6'],x['surface_area_mm2'],x['traction_mpa'],x['disp_max_mm'],x['mises_max_mpa'],x['equilibrium_residual_norm_n']]) for x in results]
print(json.dumps(ev,indent=2))
