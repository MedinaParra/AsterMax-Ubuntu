"""Self-contained HTML viewer for verified linear-static STEP results.

Presentation only: embeds solved mesh, displacement vectors and element stresses.
No FEA physics is recomputed in JavaScript. Units: mm, N, MPa.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from .global_static import GlobalStaticResult
from .postprocess import displacement_vectors, element_von_mises


class StaticResultViewerError(ValueError):
    pass


def write_static_result_viewer(
    path: str | Path,
    nodes: Sequence[Sequence[float]],
    elements: Sequence[Sequence[int]],
    result: GlobalStaticResult,
    summary: Mapping,
    *,
    summary_sha256: str,
) -> Path:
    if len(summary_sha256) != 64 or any(c not in "0123456789abcdef" for c in summary_sha256.lower()):
        raise StaticResultViewerError("summary_sha256 must be a hexadecimal SHA-256 digest")
    if not nodes or any(len(p) != 3 for p in nodes):
        raise StaticResultViewerError("viewer requires 3D nodes")
    if len(elements) != len(result.element_results):
        raise StaticResultViewerError("viewer element/result count mismatch")
    for e in elements:
        if len(e) != 4 or any(i < 0 or i >= len(nodes) for i in e):
            raise StaticResultViewerError("viewer requires valid TET4 connectivity")

    disp = displacement_vectors(result, len(nodes))
    vm = element_von_mises(result)
    stress = [list(map(float, er.stress)) for er in result.element_results]
    payload = {
        "summary": dict(summary),
        "summary_sha256": summary_sha256.lower(),
        "nodes": [list(map(float, p)) for p in nodes],
        "elements": [list(map(int, e)) for e in elements],
        "displacement_mm": [list(map(float, u)) for u in disp],
        "von_mises_MPa": list(map(float, vm)),
        "stress_MPa": stress,
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    html = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AsterMax STEP FEA Viewer</title><style>
:root{font-family:Segoe UI,Arial,sans-serif;background:#0d1117;color:#e6edf3}*{box-sizing:border-box}body{margin:0;height:100vh;display:grid;grid-template-columns:330px 1fr;overflow:hidden}.side{background:#161b22;border-right:1px solid #30363d;padding:18px;overflow:auto}.brand{font-size:25px;font-weight:700}.sub{color:#8b949e}.card{background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:12px;margin:10px 0}.metric{display:flex;justify-content:space-between;gap:12px;margin:7px 0}.metric span:first-child{color:#8b949e}.ok{color:#3fb950;font-weight:700}.hash{font:11px Consolas,monospace;color:#79c0ff;word-break:break-all}label{display:block;color:#8b949e;margin:10px 0 4px}select,input{width:100%;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:8px}.main{position:relative}canvas{width:100%;height:100%;display:block}.legend{position:absolute;right:18px;bottom:18px;background:#161b22dd;border:1px solid #30363d;border-radius:8px;padding:10px;min-width:190px}.bar{height:12px;border-radius:6px;background:linear-gradient(90deg,#2f81f7,#3fb950,#d29922,#f85149);margin:6px 0}.tip{position:absolute;left:18px;bottom:18px;background:#161b22cc;color:#8b949e;padding:8px;border-radius:6px}</style></head><body>
<aside class="side"><div class="brand">AsterMax</div><div class="sub">STEP → Mesh → FEA → Evidence</div><div class="card"><div class="metric"><span>Status</span><span class="ok">VERIFIED PIPELINE</span></div><div class="metric"><span>Units</span><span id="units"></span></div><div class="metric"><span>Nodes</span><span id="nodes"></span></div><div class="metric"><span>TET4</span><span id="tets"></span></div><div class="metric"><span>STEP unit</span><span id="stepunit"></span></div></div><div class="card"><div>Summary SHA-256</div><div id="sha" class="hash"></div></div><div class="card"><label>Result field</label><select id="field"><option value="von_mises_MPa">von_mises_MPa</option><option value="sigma_x_MPa">sigma_x_MPa</option><option value="sigma_y_MPa">sigma_y_MPa</option><option value="sigma_z_MPa">sigma_z_MPa</option></select><label>Deformation scale</label><input id="scale" type="range" min="0" max="100" step="1" value="20"><div class="metric"><span>Scale</span><span id="scaleText">20x</span></div></div><div class="card"><div class="metric"><span>Max displacement</span><span id="umax"></span></div><div class="metric"><span>Max Von Mises</span><span id="vmmax"></span></div><div class="metric"><span>Free residual</span><span id="residual"></span></div><div class="metric"><span>Applied force</span><span id="force"></span></div></div><div class="card"><div class="sub">Presentation only. Geometry, displacements and stresses are embedded from the solved evidence bundle; the browser performs no FEA solve.</div></div></aside>
<main class="main"><canvas id="view"></canvas><div class="legend"><div id="legendName"></div><div class="bar"></div><div class="metric"><span id="minv"></span><span id="maxv"></span></div></div><div class="tip">Drag: rotate · Wheel: zoom · Slider: deformation</div></main><script id="astermax-data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('astermax-data').textContent),S=D.summary,fmt=(v,n=4)=>Number(v).toFixed(n);document.getElementById('units').textContent=S.unit_system;document.getElementById('nodes').textContent=S.node_count;document.getElementById('tets').textContent=S.tet4_count;document.getElementById('stepunit').textContent=S.step_unit;document.getElementById('sha').textContent=D.summary_sha256;document.getElementById('umax').textContent=fmt(S.max_displacement_mm,6)+' mm';document.getElementById('vmmax').textContent=fmt(S.max_element_von_mises_MPa,3)+' MPa';document.getElementById('residual').textContent=fmt(S.free_residual_max_N,8)+' N';document.getElementById('force').textContent=S.recovered_applied_force_N.map(v=>fmt(v,2)).join(', ')+' N';
const canvas=document.getElementById('view'),ctx=canvas.getContext('2d'),field=document.getElementById('field');let ax=-.55,ay=.7,zoom=55,drag=false,lx=0,ly=0;const values=()=>field.value==='von_mises_MPa'?D.von_mises_MPa:D.stress_MPa.map(s=>s[field.value==='sigma_x_MPa'?0:field.value==='sigma_y_MPa'?1:2]);function rot(p){let[x,y,z]=p,cy=Math.cos(ay),sy=Math.sin(ay),cx=Math.cos(ax),sx=Math.sin(ax),x1=cy*x+sy*z,z1=-sy*x+cy*z;return[x1,cx*y-sx*z1,sx*y+cx*z1]}function color(t){t=Math.max(0,Math.min(1,t));const a=[[47,129,247],[63,185,80],[210,153,34],[248,81,73]],q=t*3,i=Math.min(2,Math.floor(q)),f=q-i;return `rgb(${a[i].map((v,j)=>Math.round(v+(a[i+1][j]-v)*f)).join(',')})`}function draw(){let r=canvas.getBoundingClientRect();canvas.width=Math.max(1,r.width*devicePixelRatio);canvas.height=Math.max(1,r.height*devicePixelRatio);ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);ctx.clearRect(0,0,r.width,r.height);let sc=Number(document.getElementById('scale').value),pts=D.nodes.map((p,i)=>rot([p[0]+D.displacement_mm[i][0]*sc,p[1]+D.displacement_mm[i][1]*sc,p[2]+D.displacement_mm[i][2]*sc])).map(p=>[p[0]*zoom+r.width/2,-p[1]*zoom+r.height/2,p[2]]),vals=values(),mn=Math.min(...vals),mx=Math.max(...vals);document.getElementById('legendName').textContent=field.value;document.getElementById('minv').textContent=fmt(mn,3);document.getElementById('maxv').textContent=fmt(mx,3);let faces=[];D.elements.forEach((e,ei)=>[[0,1,2],[0,1,3],[0,2,3],[1,2,3]].forEach(f=>{let ids=f.map(k=>e[k]);faces.push({ids,ei,z:ids.reduce((s,i)=>s+pts[i][2],0)/3})}));faces.sort((a,b)=>a.z-b.z);for(const f of faces){let t=mx===mn?.5:(vals[f.ei]-mn)/(mx-mn);ctx.beginPath();f.ids.forEach((i,k)=>k?ctx.lineTo(pts[i][0],pts[i][1]):ctx.moveTo(pts[i][0],pts[i][1]));ctx.closePath();ctx.fillStyle=color(t);ctx.globalAlpha=.72;ctx.fill();ctx.globalAlpha=1;ctx.strokeStyle='#8b949e';ctx.lineWidth=.65;ctx.stroke()}}canvas.onmousedown=e=>{drag=true;lx=e.clientX;ly=e.clientY};window.onmouseup=()=>drag=false;window.onmousemove=e=>{if(!drag)return;ay+=(e.clientX-lx)*.008;ax+=(e.clientY-ly)*.008;lx=e.clientX;ly=e.clientY;draw()};canvas.onwheel=e=>{e.preventDefault();zoom*=e.deltaY>0?.9:1.1;draw()};field.onchange=draw;document.getElementById('scale').oninput=e=>{document.getElementById('scaleText').textContent=e.target.value+'x';draw()};window.onresize=draw;draw();
</script></body></html>'''.replace("__DATA__", data.replace("</", "<\\/"))
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return destination
