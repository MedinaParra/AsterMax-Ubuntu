"""Self-contained browser viewer for the verified AsterMax Windows demo.

The viewer has no CDN/runtime dependency.  Geometry and verified nodal fields are
embedded into one HTML document so the evidence bundle remains portable and can be
opened by a normal Windows browser.  It is a presentation layer only: no FEA physics
is recomputed in JavaScript.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from .bolt_pretension import BoltPretensionConnector
from .gapped_joint_vtk import gapped_joint_nodal_fields
from .gapped_preloaded_joint import GappedPreloadedJointResult
from .gmsh_ascii import TetraMesh


class BrowserViewerError(ValueError):
    """Raised when trusted result data cannot be represented by the demo viewer."""


def _json_safe(value):
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def write_self_contained_viewer(
    path: str | Path,
    mesh: TetraMesh,
    connectors: Sequence[BoltPretensionConnector],
    result: GappedPreloadedJointResult,
    summary: Mapping,
    *,
    summary_sha256: str,
) -> Path:
    """Write a deterministic offline HTML viewer for already-verified FEA evidence."""
    if len(summary_sha256) != 64 or any(c not in "0123456789abcdef" for c in summary_sha256.lower()):
        raise BrowserViewerError("summary_sha256 must be a hexadecimal SHA-256 digest")
    fields = gapped_joint_nodal_fields(mesh, connectors, result)
    scalar_names = (
        "initial_gap_mm", "final_gap_mm", "support_state", "bolt_axial_force_N",
        "bolt_load_share", "contact_pressure_MPa", "friction_utilization",
        "contact_normal_force_N", "friction_limit_N",
    )
    missing = [name for name in scalar_names if name not in fields]
    if missing:
        raise BrowserViewerError("viewer is missing required verified fields: " + ", ".join(missing))

    payload = {
        "case": _json_safe(dict(summary)),
        "summary_sha256": summary_sha256.lower(),
        "unit_system": "mm-N-MPa",
        "nodes": _json_safe(mesh.nodes),
        "elements": _json_safe(mesh.elements),
        "fields": {name: _json_safe(fields[name]) for name in scalar_names},
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    html = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AsterMax Verified Engineering Viewer</title>
<style>
:root{font-family:Segoe UI,Arial,sans-serif;background:#0d1117;color:#e6edf3}*{box-sizing:border-box}
body{margin:0;display:grid;grid-template-columns:320px 1fr;height:100vh;overflow:hidden}.side{padding:18px;background:#161b22;border-right:1px solid #30363d;overflow:auto}.main{position:relative}.brand{font-size:24px;font-weight:700}.sub{color:#8b949e;margin:4px 0 18px}.card{background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:12px;margin:10px 0}.ok{color:#3fb950;font-weight:700}.metric{display:flex;justify-content:space-between;gap:12px;margin:7px 0}.metric span:first-child{color:#8b949e}.hash{font:11px Consolas,monospace;word-break:break-all;color:#79c0ff}.controls label{display:block;color:#8b949e;margin:10px 0 4px}select,input{width:100%;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:8px}canvas{width:100%;height:100%;display:block}.legend{position:absolute;right:18px;bottom:18px;background:#161b22dd;border:1px solid #30363d;border-radius:8px;padding:10px;min-width:180px}.bar{height:12px;border-radius:6px;background:linear-gradient(90deg,#2f81f7,#3fb950,#d29922,#f85149);margin:6px 0}.tip{position:absolute;left:18px;bottom:18px;color:#8b949e;background:#161b22cc;padding:8px;border-radius:6px}.badge{display:inline-block;padding:3px 7px;border-radius:12px;background:#238636;color:white;font-size:12px}</style></head>
<body><aside class="side"><div class="brand">AsterMax</div><div class="sub">Verified Engineering Viewer</div>
<div class="card"><div class="metric"><span>Evidence</span><span class="ok">VERIFIED INPUT</span></div><div class="metric"><span>Case</span><span id="caseId"></span></div><div class="metric"><span>Units</span><span>mm-N-MPa</span></div><div class="metric"><span>Solver</span><span id="solver"></span></div><div class="metric"><span>Support loss</span><span id="support"></span></div></div>
<div class="card"><div>Summary SHA-256</div><div id="sha" class="hash"></div></div>
<div class="card controls"><label>Result field</label><select id="field"></select><label>Deformation scale</label><input id="scale" type="range" min="0" max="20" step="0.5" value="6"><div class="metric"><span>Scale</span><span id="scaleText">6x</span></div></div>
<div class="card"><div class="metric"><span>Total normal force</span><span id="normal"></span></div><div class="metric"><span>Friction capacity</span><span id="friction"></span></div><div class="metric"><span>Max free residual</span><span id="residual"></span></div></div>
<div class="card"><span class="badge">Presentation only</span><p class="sub">The browser does not solve or modify physics. Values are embedded from the verified evidence bundle.</p></div></aside>
<main class="main"><canvas id="view"></canvas><div class="legend"><div id="legendName"></div><div class="bar"></div><div class="metric"><span id="minv"></span><span id="maxv"></span></div></div><div class="tip">Drag: rotate · Wheel: zoom · Field menu: verified result</div></main>
<script id="astermax-data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('astermax-data').textContent), C=D.case;
const fmt=(v,n=3)=>Number.isFinite(Number(v))?Number(v).toFixed(n):'—';
document.getElementById('caseId').textContent=C.case_id||'—';document.getElementById('sha').textContent=D.summary_sha256;
document.getElementById('solver').textContent=C.solver_converged?'CONVERGED':'NOT CONVERGED';document.getElementById('support').textContent=fmt(100*(C.support_loss_fraction||0),1)+'%';
document.getElementById('normal').textContent=fmt(C.total_normal_contact_force_N)+' N';document.getElementById('friction').textContent=fmt(C.total_friction_capacity_N)+' N';document.getElementById('residual').textContent=fmt(C.free_residual_max_N,6)+' N';
const field=document.getElementById('field');Object.keys(D.fields).forEach(k=>{let o=document.createElement('option');o.value=k;o.textContent=k;field.appendChild(o)});field.value='contact_pressure_MPa';
const canvas=document.getElementById('view'),ctx=canvas.getContext('2d');let ax=-.65,ay=.65,zoom=150,drag=false,lx=0,ly=0;
const disp=()=>{const s=Number(document.getElementById('scale').value),u=[];let raw=C.final_gap_mm||[];for(let i=0;i<D.nodes.length;i++)u.push([0,0,(i>=3&&i-3<raw.length)?(raw[i-3]-(C.initial_gap_mm||[])[i-3])*s:0]);return u};
function rot(p){let[x,y,z]=p,cy=Math.cos(ay),sy=Math.sin(ay),cx=Math.cos(ax),sx=Math.sin(ax);let x1=cy*x+sy*z,z1=-sy*x+cy*z;return[x1,cx*y-sx*z1,sx*y+cx*z1]}
function color(t){t=Math.max(0,Math.min(1,t));let stops=[[47,129,247],[63,185,80],[210,153,34],[248,81,73]],q=t*3,i=Math.min(2,Math.floor(q)),f=q-i,a=stops[i],b=stops[i+1];return `rgb(${a.map((v,j)=>Math.round(v+(b[j]-v)*f)).join(',')})`}
function draw(){let r=canvas.getBoundingClientRect();canvas.width=Math.max(1,r.width*devicePixelRatio);canvas.height=Math.max(1,r.height*devicePixelRatio);ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);ctx.clearRect(0,0,r.width,r.height);let vals=D.fields[field.value],finite=vals.filter(v=>v!==null&&Number.isFinite(v)),mn=Math.min(...finite),mx=Math.max(...finite);if(!finite.length){mn=0;mx=1}document.getElementById('legendName').textContent=field.value;document.getElementById('minv').textContent=fmt(mn);document.getElementById('maxv').textContent=fmt(mx);let du=disp(),pts=D.nodes.map((p,i)=>{let q=[p[0]+du[i][0],p[1]+du[i][1],p[2]+du[i][2]],a=rot(q);return[a[0]*zoom+r.width/2,-a[1]*zoom+r.height/2,a[2]]});let faces=[];for(const e of D.elements){for(const f of [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]){let ids=f.map(k=>e[k]);faces.push({ids,z:ids.reduce((s,i)=>s+pts[i][2],0)/3})}}faces.sort((a,b)=>a.z-b.z);for(const f of faces){let vv=f.ids.map(i=>vals[i]).filter(v=>v!==null&&Number.isFinite(v)),v=vv.length?vv.reduce((a,b)=>a+b,0)/vv.length:mn,t=(mx===mn)?0.5:(v-mn)/(mx-mn);ctx.beginPath();f.ids.forEach((i,k)=>{let p=pts[i];k?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])});ctx.closePath();ctx.fillStyle=vv.length?color(t):'#30363d';ctx.globalAlpha=.72;ctx.fill();ctx.globalAlpha=1;ctx.strokeStyle='#8b949e';ctx.lineWidth=.8;ctx.stroke()} }
canvas.onmousedown=e=>{drag=true;lx=e.clientX;ly=e.clientY};window.onmouseup=()=>drag=false;window.onmousemove=e=>{if(!drag)return;ay+=(e.clientX-lx)*.008;ax+=(e.clientY-ly)*.008;lx=e.clientX;ly=e.clientY;draw()};canvas.onwheel=e=>{e.preventDefault();zoom*=e.deltaY>0?.9:1.1;draw()};field.onchange=draw;document.getElementById('scale').oninput=e=>{document.getElementById('scaleText').textContent=e.target.value+'x';draw()};window.onresize=draw;draw();
</script></body></html>'''.replace("__DATA__", data.replace("</", "<\\/"))
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return destination
