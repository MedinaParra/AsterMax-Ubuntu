from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from .fea.mesh_quality import tetra_mesh_quality
from .fea.viewer_tet10 import extract_surface_tri6, subdivide_tri6


def _metrics(nodes_mm: np.ndarray, elements: np.ndarray) -> dict[str, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    conn = np.asarray(elements, dtype=np.int64)
    if conn.ndim != 2 or conn.shape[1] not in (4, 10):
        raise ValueError("elements must have shape (m, 4) or (m, 10)")
    xyz = nodes[conn[:, :4]]
    e01, e02, e03 = xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0], xyz[:, 3] - xyz[:, 0]
    det = np.einsum("ij,ij->i", e01, np.cross(e02, e03))
    denom = np.linalg.norm(e01, axis=1) * np.linalg.norm(e02, axis=1) * np.linalg.norm(e03, axis=1)
    sj = np.divide(det, denom, out=np.zeros_like(det), where=denom > 0)
    pairs = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    lengths = np.stack([np.linalg.norm(xyz[:, j] - xyz[:, i], axis=1) for i, j in pairs], axis=1)
    shortest, longest = lengths.min(axis=1), lengths.max(axis=1)
    aspect = np.divide(longest, shortest, out=np.full_like(longest, np.inf), where=shortest > 0)
    volume = det / 6.0
    sum_l2 = np.sum(lengths * lengths, axis=1)
    mr = np.zeros_like(volume)
    valid = (volume > 0) & (sum_l2 > 0)
    mr[valid] = 12.0 * np.power(3.0 * volume[valid], 2.0 / 3.0) / sum_l2[valid]
    return {"scaled_jacobian": sj, "mean_ratio": mr, "edge_aspect_ratio": aspect, "determinant": det}


def _surface_triangles_with_owner(elements: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return display triangles and owning tetra index for TET4 or straight-sided TET10."""
    conn = np.asarray(elements, dtype=np.int64)
    if conn.ndim != 2 or conn.shape[1] not in (4, 10):
        raise ValueError("elements must have shape (m, 4) or (m, 10)")
    if conn.shape[1] == 10:
        tri6, owner = extract_surface_tri6(conn)
        return subdivide_tri6(tri6, owner)

    local_faces = ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))
    owners: dict[tuple[int, int, int], list[tuple[tuple[int, int, int], int]]] = {}
    for cell_index, tet in enumerate(conn):
        if len(set(int(v) for v in tet)) != 4:
            raise ValueError("TET4 connectivity must contain four distinct nodes")
        for local in local_faces:
            face = tuple(int(tet[i]) for i in local)
            key = tuple(sorted(face))
            owners.setdefault(key, []).append((face, cell_index))
    triangles: list[tuple[int, int, int]] = []
    cell_owner: list[int] = []
    for key in sorted(owners):
        refs = owners[key]
        if len(refs) > 2:
            raise ValueError("non-manifold TET4 face has more than two owners")
        if len(refs) == 1:
            face, owner = refs[0]
            triangles.append(face)
            cell_owner.append(owner)
    return np.asarray(triangles, dtype=np.int64), np.asarray(cell_owner, dtype=np.int64)


def build_mesh_inspector_payload(nodes_mm: np.ndarray, elements: np.ndarray) -> dict:
    nodes = np.asarray(nodes_mm, dtype=float)
    conn = np.asarray(elements, dtype=np.int64)
    report = tetra_mesh_quality(nodes, conn)
    m = _metrics(nodes, conn)
    fail = (m["determinant"] <= 1e-14) | (m["scaled_jacobian"] < 0.05) | (m["mean_ratio"] < 0.05) | (m["edge_aspect_ratio"] > 20.0)
    warn = (~fail) & ((m["scaled_jacobian"] < 0.20) | (m["mean_ratio"] < 0.20) | (m["edge_aspect_ratio"] > 8.0))
    status = np.where(fail, "FAIL", np.where(warn, "WARN", "PASS"))
    severity = np.maximum.reduce([
        np.maximum(0.0, (0.20 - m["scaled_jacobian"]) / 0.20),
        np.maximum(0.0, (0.20 - m["mean_ratio"]) / 0.20),
        np.maximum(0.0, (m["edge_aspect_ratio"] - 8.0) / 12.0),
    ])
    worst = int(np.argmax(severity)) if len(severity) else -1
    tris, tri_owner = _surface_triangles_with_owner(conn)
    corner_elements = conn[:, :4]
    centroids = nodes[corner_elements].mean(axis=1)
    payload = {
        "schema": "AsterMaxMeshInspectorV2",
        "policy_source": "tetra_mesh_quality defaults",
        "gate_report": report.__dict__,
        "element_family": "TET10" if conn.shape[1] == 10 else "TET4",
        "nodes_mm": nodes.tolist(),
        "surface_triangles": tris.tolist(),
        "surface_owner": tri_owner.tolist(),
        "corner_elements": corner_elements.tolist(),
        "element_centroids_mm": centroids.tolist(),
        "elements": [
            {
                "index": int(i),
                "status": str(status[i]),
                "severity": float(severity[i]),
                "scaled_jacobian": float(m["scaled_jacobian"][i]),
                "mean_ratio": float(m["mean_ratio"][i]),
                "edge_aspect_ratio": float(m["edge_aspect_ratio"][i]),
            }
            for i in range(len(status))
        ],
        "worst_element_index": worst,
        "claims": {
            "acceptance_driven_by_inspector_ranking": False,
            "volumetric_diagnostic_payload": True,
            "curved_tet10_quality": False,
            "solution_converged": False,
            "industrial_validation": False,
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    payload["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def write_mesh_inspector(path: str | Path, nodes_mm: np.ndarray, elements: np.ndarray) -> dict:
    p = Path(path)
    payload = build_mesh_inspector_payload(nodes_mm, elements)
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    html = f'''<!doctype html><meta charset="utf-8"><title>AsterMax Mesh Inspector</title><style>body{{margin:0;background:#0b1020;color:#eef3ff;font:13px Segoe UI}}#app{{display:grid;grid-template-columns:1fr 380px;height:100vh}}canvas{{width:100%;height:100%}}aside{{padding:16px;background:#111a2d;overflow:auto}}.k{{display:grid;grid-template-columns:1fr auto;gap:8px;padding:5px 0}}table{{width:100%;border-collapse:collapse;font-size:11px}}td,th{{padding:5px;border-bottom:1px solid #2b3852;text-align:right}}th:first-child,td:first-child{{text-align:left}}.PASS{{color:#9fe3ad}}.WARN{{color:#ffd27d}}.FAIL{{color:#ff8e8e}}button,select,input{{width:100%;box-sizing:border-box;margin:5px 0;padding:7px;background:#1c2945;color:white;border:1px solid #435475}}</style><div id="app"><canvas id="c"></canvas><aside><h2>Mesh Inspector V2</h2><div id="gate"></div><div class="k"><span>Element family</span><b id="family"></b><span>Scaled Jacobian min</span><b id="sj"></b><span>Mean ratio min</span><b id="mr"></b><span>Edge aspect max</span><b id="ar"></b><span>Worst element</span><b id="worst"></b></div><select id="metric"><option value="status">PASS / WARN / FAIL</option><option value="scaled_jacobian">Scaled Jacobian</option><option value="mean_ratio">Mean ratio</option><option value="edge_aspect_ratio">Edge aspect ratio</option></select><label>Section axis</label><select id="axis"><option>X</option><option>Y</option><option>Z</option></select><label>Section position</label><input id="clip" type="range" min="0" max="100" value="100"><label>Show worst N tetrahedra</label><input id="worstN" type="range" min="0" max="50" value="0"><button id="focus">Focus worst element</button><table><thead><tr><th>Element</th><th>Status</th><th>SJ</th><th>MR</th><th>AR</th></tr></thead><tbody id="rows"></tbody></table><p>Diagnostic layer only. Acceptance remains governed by the fail-closed mesh-quality gate. Sectioning uses tetra centroids for inspection, not acceptance.</p></aside></div><script id="d" type="application/json">{data}</script><script>(()=>{{const D=JSON.parse(document.getElementById('d').textContent),R=D.gate_report,E=D.elements;gate.innerHTML='<b class="'+R.status+'">'+R.status+'</b> · '+R.element_count+' '+D.element_family;family.textContent=D.element_family;sj.textContent=R.min_scaled_jacobian.toPrecision(5);mr.textContent=R.min_mean_ratio.toPrecision(5);ar.textContent=R.max_edge_aspect_ratio.toPrecision(5);worst.textContent=D.worst_element_index;rows.innerHTML=E.slice().sort((a,b)=>b.severity-a.severity).slice(0,40).map(e=>`<tr><td>${{e.index}}</td><td class="${{e.status}}">${{e.status}}</td><td>${{e.scaled_jacobian.toFixed(3)}}</td><td>${{e.mean_ratio.toFixed(3)}}</td><td>${{e.edge_aspect_ratio.toFixed(2)}}</td></tr>`).join('');const c=document.getElementById('c'),x=c.getContext('2d');let yaw=-.7,pitch=.45,zoom=1,drag=0,lx=0,ly=0,focusIndex=-1;function col(i){{let e=E[i],m=metric.value;if(m==='status')return e.status==='FAIL'?'#ff5757':e.status==='WARN'?'#ffc44d':'#58c97b';let v=m==='edge_aspect_ratio'?Math.min(e[m]/20,1):1-Math.min(Math.max(e[m],0),1);let h=120*(1-v);return `hsl(${{h}} 75% 55%)`}}function visible(i){{let k={{X:0,Y:1,Z:2}}[axis.value],C=D.element_centroids_mm,vals=C.map(q=>q[k]),lo=Math.min(...vals),hi=Math.max(...vals),cut=lo+(hi-lo)*(+clip.value/100);return C[i][k]<=cut}}function drawTet(i,pts,alpha=.9){{const tet=D.corner_elements[i],faces=[[0,2,1],[0,1,3],[1,2,3],[2,0,3]];faces.forEach(f=>{{let t=f.map(j=>tet[j]);x.beginPath();x.moveTo(...pts[t[0]].slice(0,2));x.lineTo(...pts[t[1]].slice(0,2));x.lineTo(...pts[t[2]].slice(0,2));x.closePath();x.fillStyle=col(i);x.globalAlpha=alpha;x.fill();x.globalAlpha=1;x.strokeStyle=i===focusIndex?'#ffffff':'#0a0f18';x.lineWidth=i===focusIndex?2:1;x.stroke()}})}}function draw(){{let r=c.getBoundingClientRect(),d=devicePixelRatio||1;c.width=r.width*d;c.height=r.height*d;x.setTransform(d,0,0,d,0,0);x.fillStyle='#08101d';x.fillRect(0,0,r.width,r.height);let P=D.nodes_mm,T=D.surface_triangles,O=D.surface_owner,center=[0,0,0];if(focusIndex>=0)center=D.element_centroids_mm[focusIndex].slice();else P.forEach(p=>p.forEach((v,k)=>center[k]+=v/P.length));let cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch),pts=P.map(p=>{{let X=p[0]-center[0],Y=p[1]-center[1],Z=p[2]-center[2],a=cy*X-sy*Y,b=sy*X+cy*Y,q=cp*Z-sp*b,z=sp*Z+cp*b;return [r.width/2+a*5*zoom,r.height/2-q*5*zoom,z]}});let order=T.map((t,i)=>[i,(pts[t[0]][2]+pts[t[1]][2]+pts[t[2]][2])/3]).sort((a,b)=>a[1]-b[1]);order.forEach(([i])=>{{if(!visible(O[i]))return;let t=T[i];x.beginPath();x.moveTo(...pts[t[0]].slice(0,2));x.lineTo(...pts[t[1]].slice(0,2));x.lineTo(...pts[t[2]].slice(0,2));x.closePath();x.fillStyle=col(O[i]);x.globalAlpha=.55;x.fill();x.globalAlpha=1;x.strokeStyle='#0a0f18';x.lineWidth=1;x.stroke()}});let n=+worstN.value;if(n>0)E.slice().sort((a,b)=>b.severity-a.severity).slice(0,n).forEach(e=>{{if(visible(e.index))drawTet(e.index,pts,.8)}});if(focusIndex>=0)drawTet(focusIndex,pts,1)}}c.onmousedown=e=>{{drag=1;lx=e.clientX;ly=e.clientY}};onmouseup=()=>drag=0;onmousemove=e=>{{if(drag){{yaw+=(e.clientX-lx)*.01;pitch+=(e.clientY-ly)*.01;lx=e.clientX;ly=e.clientY;draw()}}}};c.onwheel=e=>{{zoom*=Math.exp(-e.deltaY*.001);draw()}};metric.onchange=draw;axis.onchange=draw;clip.oninput=draw;worstN.oninput=draw;focus.onclick=()=>{{focusIndex=D.worst_element_index;zoom=3;draw()}};onresize=draw;draw()}})()</script>'''
    p.write_text(html, encoding="utf-8")
    payload["html_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    return payload
