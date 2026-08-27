from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .fea.selections import SurfaceSignature, inspect_step_surfaces
from .project import AsterMaxProject, sha256_file, write_project


def _gmsh():
    try:
        import gmsh  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("gmsh is required for CAD face picking") from exc
    return gmsh


def _face_display_triangles(step_path: str | Path, target_size_mm: float) -> dict[int, list[list[list[float]]]]:
    path = Path(step_path).resolve()
    gmsh = _gmsh()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_face_picker")
        gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise RuntimeError(f"face picker requires exactly one STEP solid; found {len(volumes)}")
        gmsh.option.setNumber("Mesh.MeshSizeMin", float(target_size_mm))
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(target_size_mm))
        gmsh.model.mesh.setOrder(1)
        gmsh.model.mesh.generate(2)
        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        xyz = np.asarray(coords, dtype=float).reshape((-1, 3))
        coord_by_tag = {int(tag): xyz[i].tolist() for i, tag in enumerate(node_tags)}
        faces: dict[int, list[list[list[float]]]] = {}
        for dim, tag in gmsh.model.getEntities(2):
            if dim != 2:
                continue
            tris: list[list[list[float]]] = []
            types, _, node_blocks = gmsh.model.mesh.getElements(2, int(tag))
            for etype, block in zip(types, node_blocks):
                props = gmsh.model.mesh.getElementProperties(int(etype))
                n_per = int(props[3])
                arr = np.asarray(block, dtype=np.int64).reshape((-1, n_per))
                # For both TRI3 and TRI6, first three nodes are the geometric corners.
                if n_per >= 3 and str(props[0]).lower().startswith("triangle"):
                    for conn in arr:
                        tris.append([coord_by_tag[int(conn[0])], coord_by_tag[int(conn[1])], coord_by_tag[int(conn[2])]])
            if tris:
                faces[int(tag)] = tris
        return faces
    finally:
        gmsh.finalize()


def build_project_from_face_fingerprints(
    step_path: str | Path,
    project_path: str | Path,
    support_fingerprint: str,
    load_fingerprint: str,
    *,
    mesh_size_mm: float = 15.0,
    young_modulus_mpa: float = 200000.0,
    poisson_ratio: float = 0.30,
    resultant_n: tuple[float, float, float] = (0.0, -1000.0, 0.0),
) -> AsterMaxProject:
    step = Path(step_path).resolve()
    project_file = Path(project_path).resolve()
    surfaces = [sig for _, sig in inspect_step_surfaces(step)]
    support = [s for s in surfaces if s.fingerprint_sha256 == support_fingerprint]
    load = [s for s in surfaces if s.fingerprint_sha256 == load_fingerprint]
    if len(support) != 1 or len(load) != 1:
        raise RuntimeError("picker fingerprints must resolve to exactly one CAD surface each")
    try:
        geometry_step = str(step.relative_to(project_file.parent))
    except ValueError:
        geometry_step = str(step)
    project = AsterMaxProject(
        schema="AsterMaxProjectV1",
        geometry_step=geometry_step,
        length_unit="mm",
        mesh_family="TET10",
        mesh_size_mm=float(mesh_size_mm),
        young_modulus_mpa=float(young_modulus_mpa),
        poisson_ratio=float(poisson_ratio),
        support=support[0],
        load_surface=load[0],
        resultant_n=tuple(float(v) for v in resultant_n),
        geometry_sha256=sha256_file(step),
    )
    write_project(project_file, project)
    return project


def write_face_picker_html(step_path: str | Path, output_html: str | Path, *, display_mesh_size_mm: float = 12.0) -> dict:
    step = Path(step_path).resolve()
    output = Path(output_html).resolve()
    surfaces = inspect_step_surfaces(step)
    triangles = _face_display_triangles(step, display_mesh_size_mm)
    face_records = []
    for tag, signature in surfaces:
        if tag not in triangles:
            continue
        face_records.append({"cad_tag": tag, "signature": signature.to_dict(), "triangles": triangles[tag]})
    if not face_records:
        raise RuntimeError("no tessellated CAD faces available for picker")
    payload = {
        "schema": "AsterMaxFacePickerPayloadV1",
        "geometry_name": step.name,
        "geometry_sha256": sha256_file(step),
        "length_unit": "mm",
        "faces": face_records,
        "defaults": {"mesh_size_mm": 15.0, "young_modulus_mpa": 200000.0, "poisson_ratio": 0.30, "resultant_n": [0.0, -1000.0, 0.0]},
    }
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).replace("</", "<\\/")
    html = f'''<!doctype html><html><head><meta charset="utf-8"><title>AsterMax CAD Face Picker</title><style>
html,body{{height:100%;margin:0;background:#0b1020;color:#edf2ff;font:14px Segoe UI,Arial}}#app{{height:100%;display:grid;grid-template-columns:1fr 330px}}canvas{{width:100%;height:100%;background:linear-gradient(#16223d,#080c16);display:block}}aside{{padding:16px;background:#10182a;border-left:1px solid #34415f;overflow:auto}}h2{{margin:0 0 4px}}.muted{{color:#9aa9c7}}button,input{{width:100%;box-sizing:border-box;margin:4px 0 10px;padding:8px;background:#1a2743;color:white;border:1px solid #455574;border-radius:5px}}button{{cursor:pointer}}.slot{{padding:9px;border:1px solid #3b4968;border-radius:6px;margin:8px 0;word-break:break-all}}.support{{border-color:#6fb6ff}}.load{{border-color:#ffb36f}}code{{font-size:10px}}#hint{{position:absolute;left:14px;top:12px;background:#0b1020dd;padding:8px;border-radius:6px}}</style></head><body><div id="app"><main style="position:relative"><canvas id="c"></canvas><div id="hint">Click face → assign SUPPORT or LOAD · drag orbit · wheel zoom</div></main><aside><h2>AsterMax PMV</h2><div class="muted">CAD face picker · STEP in mm</div><p id="geom"></p><div class="slot"><b>Selected face</b><div id="sel">none</div></div><button id="support">Assign as Fixed Support</button><button id="load">Assign as Force Surface</button><div class="slot support"><b>SUPPORT</b><div id="sval">not assigned</div></div><div class="slot load"><b>LOAD</b><div id="lval">not assigned</div></div><label>Mesh size [mm]</label><input id="mesh" value="15"><label>E [MPa]</label><input id="E" value="200000"><label>Poisson ν</label><input id="nu" value="0.30"><label>Fx [N]</label><input id="fx" value="0"><label>Fy [N]</label><input id="fy" value="-1000"><label>Fz [N]</label><input id="fz" value="0"><button id="save">Download .astermax project</button><p class="muted">Save the project beside the STEP file. The project embeds the STEP SHA-256 and persistent CAD surface signatures.</p></aside></div><script id="data" type="application/json">{data}</script><script>
(()=>{{const D=JSON.parse(document.getElementById('data').textContent),c=document.getElementById('c'),x=c.getContext('2d');let yaw=-.7,pitch=.45,zoom=1,drag=false,lx=0,ly=0,selected=null,support=null,load=null,projected=[];document.getElementById('geom').textContent=D.geometry_name+' · '+D.faces.length+' CAD faces';const all=[];D.faces.forEach((f,fi)=>f.triangles.forEach(t=>t.forEach(p=>all.push(p))));let ctr=[0,0,0];all.forEach(p=>p.forEach((v,k)=>ctr[k]+=v/all.length));let diag=0;all.forEach(p=>diag=Math.max(diag,Math.hypot(p[0]-ctr[0],p[1]-ctr[1],p[2]-ctr[2])));function rot(p){{let X=p[0]-ctr[0],Y=p[1]-ctr[1],Z=p[2]-ctr[2],cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);let a=cy*X-sy*Y,b=sy*X+cy*Y;return[a,cp*b-sp*Z,sp*b+cp*Z]}}function draw(){{let d=devicePixelRatio||1;c.width=c.clientWidth*d;c.height=c.clientHeight*d;x.setTransform(d,0,0,d,0,0);let W=c.clientWidth,H=c.clientHeight,S=.42*Math.min(W,H)/(diag||1)*zoom;projected=[];let work=[];D.faces.forEach((f,fi)=>f.triangles.forEach(t=>{{let q=t.map(p=>rot(p)),z=q.reduce((a,p)=>a+p[2],0)/3;work.push({{fi,z,q}})}}));work.sort((a,b)=>a.z-b.z);work.forEach(o=>{{let pts=o.q.map(p=>[W/2+p[0]*S,H/2-p[1]*S]);let state=o.fi===support?'support':o.fi===load?'load':o.fi===selected?'selected':'normal';x.beginPath();x.moveTo(...pts[0]);x.lineTo(...pts[1]);x.lineTo(...pts[2]);x.closePath();x.fillStyle=state==='support'?'#2377bddd':state==='load'?'#c56c25dd':state==='selected'?'#8d62d9dd':'#75839aaa';x.fill();x.strokeStyle='#c7d0df66';x.stroke();projected.push({{fi:o.fi,pts,z:o.z}})}})}}function inside(px,py,p){{let [a,b,c0]=p,sg=(p1,p2,p3)=>(p1[0]-p3[0])*(p2[1]-p3[1])-(p2[0]-p3[0])*(p1[1]-p3[1]),d1=sg([px,py],a,b),d2=sg([px,py],b,c0),d3=sg([px,py],c0,a),n=(d1<0)||(d2<0)||(d3<0),q=(d1>0)||(d2>0)||(d3>0);return!(n&&q)}}c.onmousedown=e=>{{drag=true;lx=e.clientX;ly=e.clientY}};window.onmouseup=()=>drag=false;c.onmousemove=e=>{{if(!drag)return;yaw+=(e.clientX-lx)*.008;pitch=Math.max(-1.5,Math.min(1.5,pitch+(e.clientY-ly)*.008));lx=e.clientX;ly=e.clientY;draw()}};c.onwheel=e=>{{e.preventDefault();zoom*=Math.exp(-e.deltaY*.001);draw()}};c.onclick=e=>{{if(Math.abs(e.movementX)+Math.abs(e.movementY)>3)return;let r=c.getBoundingClientRect(),px=e.clientX-r.left,py=e.clientY-r.top,hits=projected.filter(o=>inside(px,py,o.pts));if(!hits.length)return;hits.sort((a,b)=>b.z-a.z);selected=hits[0].fi;document.getElementById('sel').textContent='CAD face '+D.faces[selected].cad_tag+' · '+D.faces[selected].signature.fingerprint_sha256.slice(0,16)+'…';draw()}};document.getElementById('support').onclick=()=>{{if(selected===null)return;support=selected;if(load===support)load=null;sync();draw()}};document.getElementById('load').onclick=()=>{{if(selected===null)return;load=selected;if(support===load)support=null;sync();draw()}};function sync(){{document.getElementById('sval').textContent=support===null?'not assigned':D.faces[support].signature.fingerprint_sha256;document.getElementById('lval').textContent=load===null?'not assigned':D.faces[load].signature.fingerprint_sha256}}document.getElementById('save').onclick=()=>{{if(support===null||load===null){{alert('Assign distinct SUPPORT and LOAD faces first.');return}}let p={{schema:'AsterMaxProjectV1',geometry_step:D.geometry_name,length_unit:'mm',mesh_family:'TET10',mesh_size_mm:+mesh.value,young_modulus_mpa:+E.value,poisson_ratio:+nu.value,support:D.faces[support].signature,load_surface:D.faces[load].signature,resultant_n:[+fx.value,+fy.value,+fz.value],geometry_sha256:D.geometry_sha256}},blob=new Blob([JSON.stringify(p,null,2)+'\n'],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=D.geometry_name.replace(/\.(step|stp)$/i,'')+'.astermax';a.click();URL.revokeObjectURL(a.href)}};window.onresize=draw;draw()}})();</script></body></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return {"schema": payload["schema"], "faces": len(face_records), "triangles": sum(len(f["triangles"]) for f in face_records), "geometry_sha256": payload["geometry_sha256"], "html": str(output)}
