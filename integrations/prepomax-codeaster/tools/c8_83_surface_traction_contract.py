#!/usr/bin/env python3
"""C8.83 harness-only distributed surface traction transform.

Takes the generated Code_Aster MAIL/COMM study from the admitted C8.82f pipeline,
extracts the x=max boundary of TETRA10 as TRIA6, verifies its geometric area,
and replaces the single +X nodal load with FORCE_FACE whose integral is exactly
the requested resultant. This is deliberately a qualification seam, not a claim
that the product's native Surface/STLoad binding is already qualified.
"""
import argparse, hashlib, json, math, pathlib, re

EDGE_MID = {(0,1):4,(1,2):5,(0,2):6,(0,3):7,(1,3):8,(2,3):9}
FACES = ((0,1,2),(0,1,3),(0,2,3),(1,2,3))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def parse_mail(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    nodes, tets, mode = {}, [], None
    for raw in lines:
        s = raw.strip()
        if s == "COOR_3D": mode = "nodes"; continue
        if s == "TETRA10": mode = "tets"; continue
        if s in ("FINSF", "FIN"): mode = None; continue
        if not s or s.startswith("%"): continue
        parts = s.split()
        if mode == "nodes" and len(parts) >= 4:
            try: nodes[parts[0]] = tuple(float(x.replace("D","E")) for x in parts[1:4])
            except ValueError: pass
        elif mode == "tets" and len(parts) >= 11:
            tets.append((parts[0], parts[1:11]))
    if not nodes or not tets:
        raise SystemExit(f"could not parse COOR_3D/TETRA10 from {path}")
    return lines, nodes, tets

def tri_area(nodes, tri):
    a,b,c = (nodes[x] for x in tri[:3])
    u = tuple(b[i]-a[i] for i in range(3))
    v = tuple(c[i]-a[i] for i in range(3))
    cr = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    return 0.5*math.sqrt(sum(x*x for x in cr))

def boundary_xmax(nodes, tets):
    xs=[p[0] for p in nodes.values()]
    xmax=max(xs); extent=max(xs)-min(xs); tol=max(1e-9, extent*1e-10)
    candidates={}; adjacency={}
    for elem, ids in tets:
        for f in FACES:
            corners=tuple(ids[i] for i in f); key=tuple(sorted(corners))
            adjacency[key]=adjacency.get(key,0)+1
            if all(abs(nodes[n][0]-xmax)<=tol for n in corners):
                a,b,c=f
                def mid(i,j): return ids[EDGE_MID[tuple(sorted((i,j)))]]
                candidates[key]=(elem,(ids[a],ids[b],ids[c],mid(a,b),mid(b,c),mid(a,c)))
    faces=[v for k,v in candidates.items() if adjacency.get(k)==1]
    if not faces: raise SystemExit("no external TETRA10 face found on x=max")
    for _,tri in faces:
        if any(abs(nodes[n][0]-xmax)>tol for n in tri):
            raise SystemExit("TRIA6 midside node is not on x=max; element ordering assumption rejected")
    return xmax,tol,faces

def append_surface(mail_path, faces):
    original=mail_path.read_text(encoding="utf-8", errors="replace")
    if "NOM=S_LOAD_XMAX" in original: raise SystemExit("study already contains C8.83 surface group")
    idx=original.rfind("\nFIN")
    if idx<0: raise SystemExit("MAIL final FIN marker missing")
    names=[f"ST{i+1}" for i in range(len(faces))]
    block=["TRIA6"]
    for name,(_,tri) in zip(names,faces): block.append(" "+name+" "+" ".join(tri))
    block += ["FINSF", "GROUP_MA NOM=S_LOAD_XMAX"]
    for i in range(0,len(names),8): block.append(" "+" ".join(names[i:i+8]))
    block.append("FINSF")
    mail_path.write_text(original[:idx]+"\n"+"\n".join(block)+original[idx:],encoding="utf-8")

def replace_load(comm_path, traction):
    text=comm_path.read_text(encoding="utf-8", errors="replace")
    pat=r"FORCE_NODALE=\(\s*_F\(GROUP_NO=['\"]N_LOAD_XMAX_NODE['\"],\s*FX=([+\-0-9.eEdD]+)\)\)"
    m=re.search(pat,text)
    if not m: raise SystemExit("expected single nodal +X load not found in COMM")
    old=float(m.group(1).replace("D","E"))
    repl="FORCE_FACE=(_F(GROUP_MA='S_LOAD_XMAX', FX={:.17g}))".format(traction)
    text2=re.sub(pat,repl,text,count=1)
    if "FORCE_NODALE" in text2: raise SystemExit("nodal load still active after transform")
    comm_path.write_text(text2,encoding="utf-8")
    return old

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("study",type=pathlib.Path); ap.add_argument("--resultant-n",type=float,default=1000.0); ap.add_argument("--evidence",type=pathlib.Path); a=ap.parse_args()
    if not math.isfinite(a.resultant_n) or a.resultant_n<=0: raise SystemExit("resultant must be finite and >0")
    mail=a.study/"astermax_c862_static.mail"; comm=a.study/"astermax_c862_static.comm"
    if not mail.is_file() or not comm.is_file(): raise SystemExit("study MAIL/COMM missing")
    original_mail_sha=sha(mail); original_comm_sha=sha(comm)
    _,nodes,tets=parse_mail(mail); xmax,tol,faces=boundary_xmax(nodes,tets)
    areas=[tri_area(nodes,tri) for _,tri in faces]
    if any((not math.isfinite(x) or x<=0) for x in areas): raise SystemExit("invalid boundary face area")
    total=sum(areas); traction=a.resultant_n/total; integrated=traction*total
    if abs(integrated-a.resultant_n)>1e-9: raise SystemExit("surface traction integration gate failed")
    append_surface(mail,faces); old_nodal=replace_load(comm,traction)
    transformed=mail.read_text(encoding="utf-8",errors="replace")
    if "GROUP_MA NOM=S_LOAD_XMAX" not in transformed: raise SystemExit("transformed MAIL surface contract missing")
    ev={"schema":"astermax.c8.83.distributed-surface-traction.v1","load_model":"uniform global +X FORCE_FACE on x=max boundary","source_load_model":"single FORCE_NODALE on N_LOAD_XMAX_NODE","source_nodal_fx_n":old_nodal,"target_resultant_n":a.resultant_n,"xmax_mm":xmax,"xmax_tolerance_mm":tol,"surface_group":"S_LOAD_XMAX","tria6_face_count":len(faces),"surface_area_mm2":total,"traction_fx_n_per_mm2":traction,"traction_fx_mpa":traction,"integrated_resultant_n":integrated,"resultant_error_n":integrated-a.resultant_n,"original_mail_sha256":original_mail_sha,"transformed_mail_sha256":sha(mail),"original_comm_sha256":original_comm_sha,"transformed_comm_sha256":sha(comm),"product_surface_traction_binding_verified":False,"qualification_surface_transform_verified":True,"industrial_validation":False,"ansys_equivalence":False}
    evidence=a.evidence or a.study.parent/"C8.83_SURFACE_TRACTION.json"; evidence.write_text(json.dumps(ev,indent=2),encoding="utf-8"); print(json.dumps(ev,indent=2))
if __name__=="__main__": main()
