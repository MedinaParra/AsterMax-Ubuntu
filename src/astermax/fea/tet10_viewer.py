from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from .solver import Tet10LinearStaticResult
from .tet10_postprocess import tet10_hotspot


@dataclass(frozen=True)
class Tet10OfflineViewerManifest:
    schema_version: str
    result_class: str
    units: dict[str, str]
    element_family: str
    node_count: int
    tet10_count: int
    boundary_tri6_count: int
    rendered_triangle_count: int
    stress_location: str
    nodal_stress_smoothing: bool
    hotspot_von_mises_mpa: float | None
    payload_sha256: str
    html_sha256: str
    converged_claim: bool
    industrial_validation_claim: bool


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_tet10_boundary_tri6(elements: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Extract boundary quadratic faces in Gmsh TET10 node order.

    Returned TRI6 faces use (corner0, corner1, corner2, mid01, mid12, mid20).
    A face shared by two cells is internal; more than two owners fails closed.
    """
    elems = np.asarray(elements, dtype=np.int64)
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("TET10 elements must have shape (m, 10)")

    # Gmsh TET10: vertices 0..3; edges 01,12,20,03,23,13 -> nodes 4..9.
    face_local = (
        (0, 2, 1, 6, 5, 4),
        (0, 1, 3, 4, 9, 7),
        (1, 2, 3, 5, 8, 9),
        (2, 0, 3, 6, 7, 8),
    )
    owners: dict[tuple[int, int, int], list[tuple[tuple[int, ...], int]]] = {}
    for cell_index, conn in enumerate(elems):
        if len(set(int(value) for value in conn)) != 10:
            raise ValueError("TET10 connectivity must contain ten distinct nodes")
        for local in face_local:
            oriented = tuple(int(conn[i]) for i in local)
            key = tuple(sorted(oriented[:3]))
            owners.setdefault(key, []).append((oriented, cell_index))

    faces: list[tuple[int, ...]] = []
    cell_owner: list[int] = []
    for key in sorted(owners):
        refs = owners[key]
        if len(refs) > 2:
            raise ValueError("Non-manifold quadratic face has more than two TET10 owners")
        if len(refs) == 1:
            face, owner = refs[0]
            faces.append(face)
            cell_owner.append(owner)
    return np.asarray(faces, dtype=np.int64), np.asarray(cell_owner, dtype=np.int64)


def linearize_tri6_faces(
    faces6: np.ndarray,
    owners: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Subdivide every TRI6 into four TRI3 patches using its midside nodes."""
    faces = np.asarray(faces6, dtype=np.int64)
    owner = np.asarray(owners, dtype=np.int64)
    if faces.ndim != 2 or faces.shape[1] != 6:
        raise ValueError("faces6 must have shape (n, 6)")
    if owner.shape != (faces.shape[0],):
        raise ValueError("owners must have one entry per TRI6")

    triangles: list[tuple[int, int, int]] = []
    tri_owner: list[int] = []
    for face, cell in zip(faces, owner):
        a, b, c, ab, bc, ca = (int(v) for v in face)
        triangles.extend(
            [
                (a, ab, ca),
                (ab, b, bc),
                (ca, bc, c),
                (ab, bc, ca),
            ]
        )
        tri_owner.extend([int(cell)] * 4)
    return np.asarray(triangles, dtype=np.int64), np.asarray(tri_owner, dtype=np.int64)


def build_tet10_viewer_payload(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
    *,
    result_class: str = "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
    converged_claim: bool = False,
    industrial_validation_claim: bool = False,
) -> dict:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    u = np.asarray(result.displacement_mm, dtype=float)
    vm_ip = np.asarray(result.integration_point_von_mises_mpa, dtype=float)
    stress_ip = np.asarray(result.integration_point_stress_mpa, dtype=float)

    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("TET10 elements must have shape (m, 10)")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("TET10 connectivity contains an out-of-range node index")
    if u.shape != nodes.shape:
        raise ValueError("displacement field must match node shape")
    if vm_ip.shape != (elems.shape[0], 4):
        raise ValueError("integration-point von Mises field must have shape (m, 4)")
    if stress_ip.shape != (elems.shape[0], 4, 6):
        raise ValueError("integration-point stress field must have shape (m, 4, 6)")
    if not all(np.all(np.isfinite(value)) for value in (nodes, u, vm_ip, stress_ip)):
        raise ValueError("TET10 viewer refuses non-finite geometry or solver fields")

    boundary6, boundary_owner = extract_tet10_boundary_tri6(elems)
    surface, surface_owner = linearize_tri6_faces(boundary6, boundary_owner)
    u_mag = np.linalg.norm(u, axis=1)
    vm_max = np.max(vm_ip, axis=1) if vm_ip.size else np.empty((0,), dtype=float)
    hotspot = tet10_hotspot(nodes, elems, result)

    payload = {
        "schema_version": "AsterMaxTet10OfflineViewerPayloadV1",
        "geometry": {
            "coordinates_mm": nodes.tolist(),
            "surface_triangles": surface.tolist(),
            "surface_owner_tet10": surface_owner.tolist(),
            "boundary_tri6": boundary6.tolist(),
        },
        "deformation": {
            "U_mm": u.tolist(),
            "U_MAG_mm": u_mag.tolist(),
        },
        "fields": {
            "U_MAG_mm": {
                "label": "Displacement magnitude",
                "location": "POINT",
                "unit": "mm",
                "values": u_mag.tolist(),
            },
            "VON_MISES_MAX_MPa": {
                "label": "Max integration-point von Mises stress",
                "location": "CELL",
                "unit": "MPa",
                "values": vm_max.tolist(),
            },
            "IP_VON_MISES_MPa": {
                "label": "Integration-point von Mises stress",
                "location": "INTEGRATION_POINT",
                "unit": "MPa",
                "values": vm_ip.tolist(),
            },
        },
        "hotspot": hotspot,
        "provenance": {
            "result_class": str(result_class),
            "element_family": "TET10_QUADRATIC",
            "stress_location": "INTEGRATION_POINT",
            "nodal_stress_smoothing": False,
            "converged_claim": bool(converged_claim),
            "industrial_validation_claim": bool(industrial_validation_claim),
            "units": {"length": "mm", "force": "N", "stress": "MPa"},
            "note": "TRI6 faces are subdivided only for rendering. Solver geometry, displacements and integration-point stresses remain unchanged.",
        },
        "counts": {
            "nodes": int(nodes.shape[0]),
            "tet10": int(elems.shape[0]),
            "boundary_tri6": int(boundary6.shape[0]),
            "rendered_triangles": int(surface.shape[0]),
        },
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    payload["payload_sha256"] = _sha256_bytes(canonical)
    return payload


def _html_document(payload: dict) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>AsterMax TET10 Offline Result Viewer</title>
<style>
html,body{{margin:0;height:100%;background:#0b1020;color:#e7ecf5;font-family:Segoe UI,Arial,sans-serif;overflow:hidden}}
#app{{display:grid;grid-template-columns:1fr 340px;height:100%}}#stage{{position:relative;min-width:0}}canvas{{width:100%;height:100%;display:block;background:linear-gradient(#111a31,#080c17)}}
#hud{{position:absolute;left:16px;top:14px;background:#0b1020df;border:1px solid #38445e;border-radius:8px;padding:10px 12px;font-size:13px;pointer-events:none}}#panel{{padding:18px;background:#10172a;border-left:1px solid #34405a;overflow:auto}}
h2{{margin:0 0 4px;font-size:20px}}.sub{{color:#9dabca;font-size:12px;margin-bottom:16px}}label{{display:block;font-size:12px;color:#aebbd5;margin:14px 0 6px}}select,input,button{{width:100%;box-sizing:border-box}}select,button{{background:#1b2742;color:#eef3ff;border:1px solid #425170;border-radius:6px;padding:8px}}button{{cursor:pointer;margin-top:7px}}input[type=range]{{accent-color:#8aa4ff}}
.kpi{{display:grid;grid-template-columns:1fr auto;gap:7px;font-size:12px;padding:10px 0;border-top:1px solid #2d3850}}.muted{{color:#98a5be}}#legend{{height:14px;border-radius:4px;background:linear-gradient(90deg,hsl(240 80% 52%),hsl(180 80% 50%),hsl(60 85% 52%),hsl(0 85% 52%));margin-top:8px}}#legendText{{display:flex;justify-content:space-between;font-size:11px;color:#c7d0e2}}.badge{{display:inline-block;padding:4px 7px;border-radius:5px;background:#293754;color:#dbe7ff;font-weight:600;font-size:11px;word-break:break-word}}.ok{{color:#9fe3b0}}.no{{color:#ffb3b3}}code{{font-size:10px;word-break:break-all;color:#aab8d4}}
</style></head><body><div id=\"app\"><div id=\"stage\"><canvas id=\"c\"></canvas><div id=\"hud\"><strong>AsterMax PMV · TET10</strong><br><span id=\"hudField\"></span><br><span id=\"hudScale\"></span><br><span id=\"hudHotspot\"></span></div></div>
<aside id=\"panel\"><h2>TET10 Result Viewer</h2><div class=\"sub\">Offline · quadratic mesh · provenance-safe</div><div class=\"badge\" id=\"classBadge\"></div>
<label>Result field</label><select id=\"field\"><option value=\"VON_MISES_MAX_MPa\">Max IP von Mises stress</option><option value=\"U_MAG_mm\">Displacement magnitude</option></select>
<label>Deformation scale <span id=\"scaleValue\"></span></label><input id=\"scale\" type=\"range\" min=\"0\" max=\"100\" step=\"1\" value=\"1\"><button id=\"autoScale\">Auto deformation scale</button><button id=\"resetView\">Reset camera</button>
<label><input id=\"wire\" type=\"checkbox\" checked style=\"width:auto\"> Show undeformed wireframe</label><label>Legend</label><div id=\"legend\"></div><div id=\"legendText\"><span id=\"minVal\"></span><span id=\"maxVal\"></span></div>
<div class=\"kpi\"><span class=\"muted\">Nodes</span><span id=\"nodes\"></span><span class=\"muted\">TET10</span><span id=\"cells\"></span><span class=\"muted\">Boundary TRI6</span><span id=\"tri6\"></span><span class=\"muted\">Rendered TRI3</span><span id=\"tris\"></span><span class=\"muted\">Stress location</span><span>Integration point</span><span class=\"muted\">Nodal stress smoothing</span><span>NO</span><span class=\"muted\">Converged claim</span><span id=\"conv\"></span><span class=\"muted\">Industrial validation</span><span id=\"industrial\"></span></div>
<label>Payload SHA-256</label><code id=\"hash\"></code><p class=\"sub\">The hotspot marker is the maximum raw integration-point von Mises value. TRI6 subdivision and deformation scale affect display only.</p></aside></div>
<script id=\"astermax-data\" type=\"application/json\">{data}</script><script>
(()=>{{'use strict';const D=JSON.parse(document.getElementById('astermax-data').textContent),c=document.getElementById('c'),ctx=c.getContext('2d');const P=D.geometry.coordinates_mm,U=D.deformation.U_mm,T=D.geometry.surface_triangles,O=D.geometry.surface_owner_tet10;let field='VON_MISES_MAX_MPa',yaw=-.65,pitch=.42,zoom=1,deform=1,drag=false,lastX=0,lastY=0,W=0,H=0,S=1;
const geom=(()=>{{let lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity],center=[0,0,0];for(const p of P)for(let k=0;k<3;k++){{lo[k]=Math.min(lo[k],p[k]);hi[k]=Math.max(hi[k],p[k]);center[k]+=p[k]/P.length}}return{{diag:Math.hypot(hi[0]-lo[0],hi[1]-lo[1],hi[2]-lo[2]),center}}}})(),diag=geom.diag,baseCenter=geom.center,maxU=Math.max(...D.deformation.U_MAG_mm,0);
function rotate(p){{let x=p[0]-baseCenter[0],y=p[1]-baseCenter[1],z=p[2]-baseCenter[2],cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch),x1=cy*x-sy*y,y1=sy*x+cy*y;return[x1,cp*y1-sp*z,sp*y1+cp*z]}}function points(scale){{return P.map((p,i)=>rotate([p[0]+U[i][0]*scale,p[1]+U[i][1]*scale,p[2]+U[i][2]*scale]))}}function vals(){{return D.fields[field].values}}function range(){{let a=Infinity,b=-Infinity;for(const x of vals()){{a=Math.min(a,x);b=Math.max(b,x)}}return[isFinite(a)?a:0,isFinite(b)?b:0]}}function color(v,a,b,alpha=.92){{const t=b>a?Math.max(0,Math.min(1,(v-a)/(b-a))):.5;return`hsla(${{240*(1-t)}},82%,54%,${{alpha}})`}}
function drawMesh(q,stroke){{for(const tri of T){{ctx.beginPath();for(let j=0;j<3;j++){{const p=q[tri[j]],x=W/2+p[0]*S,y=H/2-p[1]*S;j?ctx.lineTo(x,y):ctx.moveTo(x,y)}}ctx.closePath();ctx.strokeStyle=stroke;ctx.lineWidth=.7;ctx.stroke()}}}}function hotspotPoint(){{if(!D.hotspot)return null;const a=D.hotspot.coordinates_mm,b=D.hotspot.displaced_coordinates_mm;return rotate([a[0]+(b[0]-a[0])*deform,a[1]+(b[1]-a[1])*deform,a[2]+(b[2]-a[2])*deform])}}
function draw(){{const r=c.getBoundingClientRect();W=r.width;H=r.height;ctx.clearRect(0,0,W,H);S=Math.min(W,H)*.68/Math.max(diag,1e-12)*zoom;const q=points(deform),rv=range(),v=vals(),order=T.map((tri,i)=>[i,(q[tri[0]][2]+q[tri[1]][2]+q[tri[2]][2])/3]).sort((a,b)=>a[1]-b[1]);for(const item of order){{const i=item[0],tri=T[i];let s=D.fields[field].location==='CELL'?v[O[i]]:(v[tri[0]]+v[tri[1]]+v[tri[2]])/3;ctx.beginPath();for(let j=0;j<3;j++){{const p=q[tri[j]],x=W/2+p[0]*S,y=H/2-p[1]*S;j?ctx.lineTo(x,y):ctx.moveTo(x,y)}}ctx.closePath();ctx.fillStyle=color(s,rv[0],rv[1]);ctx.fill();ctx.strokeStyle='rgba(8,12,22,.40)';ctx.lineWidth=.45;ctx.stroke()}}if(document.getElementById('wire').checked)drawMesh(points(0),'rgba(230,236,250,.42)');const hp=hotspotPoint();if(hp){{ctx.beginPath();ctx.arc(W/2+hp[0]*S,H/2-hp[1]*S,6,0,Math.PI*2);ctx.fillStyle='#fff';ctx.fill();ctx.lineWidth=2;ctx.strokeStyle='#111';ctx.stroke()}}document.getElementById('minVal').textContent=rv[0].toPrecision(5)+' '+D.fields[field].unit;document.getElementById('maxVal').textContent=rv[1].toPrecision(5)+' '+D.fields[field].unit;document.getElementById('hudField').textContent=D.fields[field].label+' ['+D.fields[field].unit+']';document.getElementById('hudScale').textContent='Deformation display scale: '+deform.toFixed(1)+'x';document.getElementById('hudHotspot').textContent=D.hotspot?'Hotspot: '+D.hotspot.von_mises_mpa.toPrecision(6)+' MPa @ element '+D.hotspot.element_index+', IP '+D.hotspot.integration_point_index:'Hotspot: n/a'}}
function resize(){{const r=c.getBoundingClientRect(),d=devicePixelRatio||1;c.width=Math.max(1,Math.round(r.width*d));c.height=Math.max(1,Math.round(r.height*d));ctx.setTransform(d,0,0,d,0,0);draw()}}function setScale(v){{deform=Number(v);document.getElementById('scale').value=String(Math.max(0,Math.min(100,Math.round(deform))));document.getElementById('scaleValue').textContent=deform.toFixed(1)+'x';draw()}}
document.getElementById('field').onchange=e=>{{field=e.target.value;draw()}};document.getElementById('scale').oninput=e=>setScale(e.target.value);document.getElementById('autoScale').onclick=()=>setScale(maxU>0?Math.max(1,Math.min(100,.18*diag/maxU)):1);document.getElementById('resetView').onclick=()=>{{yaw=-.65;pitch=.42;zoom=1;draw()}};document.getElementById('wire').onchange=draw;c.addEventListener('pointerdown',e=>{{drag=true;lastX=e.clientX;lastY=e.clientY;c.setPointerCapture(e.pointerId)}});c.addEventListener('pointermove',e=>{{if(!drag)return;yaw+=(e.clientX-lastX)*.009;pitch=Math.max(-1.45,Math.min(1.45,pitch+(e.clientY-lastY)*.009));lastX=e.clientX;lastY=e.clientY;draw()}});c.addEventListener('pointerup',()=>drag=false);c.addEventListener('wheel',e=>{{e.preventDefault();zoom*=Math.exp(-e.deltaY*.001);zoom=Math.max(.2,Math.min(5,zoom));draw()}},{{passive:false}});
document.getElementById('classBadge').textContent=D.provenance.result_class;document.getElementById('nodes').textContent=D.counts.nodes;document.getElementById('cells').textContent=D.counts.tet10;document.getElementById('tri6').textContent=D.counts.boundary_tri6;document.getElementById('tris').textContent=D.counts.rendered_triangles;document.getElementById('hash').textContent=D.payload_sha256;const cv=document.getElementById('conv'),iv=document.getElementById('industrial');cv.textContent=D.provenance.converged_claim?'YES':'NO';cv.className=D.provenance.converged_claim?'ok':'no';iv.textContent=D.provenance.industrial_validation_claim?'YES':'NO';iv.className=D.provenance.industrial_validation_claim?'ok':'no';setScale(1);new ResizeObserver(resize).observe(c);resize()}})();
</script></body></html>"""


def write_tet10_offline_viewer_html(
    path: str | Path,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
    *,
    result_class: str = "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
    converged_claim: bool = False,
    industrial_validation_claim: bool = False,
) -> Tet10OfflineViewerManifest:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_tet10_viewer_payload(
        nodes_mm,
        elements,
        result,
        result_class=result_class,
        converged_claim=converged_claim,
        industrial_validation_claim=industrial_validation_claim,
    )
    encoded = _html_document(payload).encode("utf-8")
    output.write_bytes(encoded)
    hotspot = payload["hotspot"]
    manifest = Tet10OfflineViewerManifest(
        schema_version="AsterMaxTet10OfflineViewerEvidenceV1",
        result_class=result_class,
        units={"length": "mm", "force": "N", "stress": "MPa"},
        element_family="TET10_QUADRATIC",
        node_count=int(payload["counts"]["nodes"]),
        tet10_count=int(payload["counts"]["tet10"]),
        boundary_tri6_count=int(payload["counts"]["boundary_tri6"]),
        rendered_triangle_count=int(payload["counts"]["rendered_triangles"]),
        stress_location="INTEGRATION_POINT",
        nodal_stress_smoothing=False,
        hotspot_von_mises_mpa=None if hotspot is None else float(hotspot["von_mises_mpa"]),
        payload_sha256=str(payload["payload_sha256"]),
        html_sha256=_sha256_bytes(encoded),
        converged_claim=bool(converged_claim),
        industrial_validation_claim=bool(industrial_validation_claim),
    )
    output.with_suffix(output.suffix + ".manifest.json").write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest
