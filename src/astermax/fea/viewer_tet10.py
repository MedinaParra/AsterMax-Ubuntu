from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from .solver import Tet10LinearStaticResult


@dataclass(frozen=True)
class Tet10OfflineViewerManifest:
    schema_version: str
    result_class: str
    units: dict[str, str]
    node_count: int
    tet10_count: int
    boundary_tri6_count: int
    rendered_triangle_count: int
    integration_points_per_element: int
    stress_representation: str
    payload_sha256: str
    html_sha256: str
    converged_claim: bool
    industrial_validation_claim: bool


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_surface_tri6(elements: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Extract boundary TRI6 faces from Gmsh-order TET10 connectivity.

    The returned TRI6 order is ``corner0, corner1, corner2, mid01, mid12,
    mid20``.  Internal faces are removed by their three corner-node identity.
    Non-manifold faces fail closed.
    """
    elems = np.asarray(elements, dtype=np.int64)
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10)")

    # Gmsh TET10: 0..3 corners; 4=01, 5=12, 6=20, 7=03, 8=23, 9=13.
    face_local = (
        (0, 2, 1, 6, 5, 4),
        (0, 1, 3, 4, 9, 7),
        (1, 2, 3, 5, 8, 9),
        (2, 0, 3, 6, 7, 8),
    )
    owners: dict[tuple[int, int, int], list[tuple[tuple[int, ...], int]]] = {}
    for cell_index, conn in enumerate(elems):
        if len(set(int(value) for value in conn[:4])) != 4:
            raise ValueError("TET10 corner connectivity must contain four distinct nodes")
        if len(set(int(value) for value in conn)) != 10:
            raise ValueError("TET10 connectivity must contain ten distinct nodes")
        for local in face_local:
            face = tuple(int(conn[i]) for i in local)
            key = tuple(sorted(face[:3]))
            owners.setdefault(key, []).append((face, cell_index))

    boundary: list[tuple[int, ...]] = []
    cell_owner: list[int] = []
    for key in sorted(owners):
        refs = owners[key]
        if len(refs) > 2:
            raise ValueError("non-manifold TRI6 face has more than two TET10 owners")
        if len(refs) == 1:
            face, owner = refs[0]
            boundary.append(face)
            cell_owner.append(owner)
    return np.asarray(boundary, dtype=np.int64), np.asarray(cell_owner, dtype=np.int64)


def subdivide_tri6(tri6: np.ndarray, owner: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Render a TRI6 with its midside nodes as four linear display triangles."""
    faces = np.asarray(tri6, dtype=np.int64)
    cell_owner = np.asarray(owner, dtype=np.int64)
    if faces.ndim != 2 or faces.shape[1] != 6:
        raise ValueError("tri6 must have shape (n, 6)")
    if cell_owner.shape != (faces.shape[0],):
        raise ValueError("owner must have one TET10 index per TRI6")

    triangles: list[list[int]] = []
    owners: list[int] = []
    for face, tet_index in zip(faces, cell_owner):
        a, b, c, ab, bc, ca = (int(value) for value in face)
        triangles.extend(
            [
                [a, ab, ca],
                [ab, b, bc],
                [ca, bc, c],
                [ab, bc, ca],
            ]
        )
        owners.extend([int(tet_index)] * 4)
    return np.asarray(triangles, dtype=np.int64), np.asarray(owners, dtype=np.int64)


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
    ip_stress = np.asarray(result.integration_point_stress_mpa, dtype=float)
    ip_vm = np.asarray(result.integration_point_von_mises_mpa, dtype=float)

    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10)")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contains an out-of-range node index")
    if u.shape != nodes.shape:
        raise ValueError("displacement field must match node shape")
    if ip_stress.shape != (elems.shape[0], 4, 6):
        raise ValueError("integration-point stress must have shape (m, 4, 6)")
    if ip_vm.shape != (elems.shape[0], 4):
        raise ValueError("integration-point von Mises must have shape (m, 4)")
    if not all(np.all(np.isfinite(value)) for value in (nodes, u, ip_stress, ip_vm)):
        raise ValueError("viewer refuses non-finite geometry or solver fields")

    boundary_tri6, boundary_owner = extract_surface_tri6(elems)
    display_triangles, display_owner = subdivide_tri6(boundary_tri6, boundary_owner)
    u_mag = np.linalg.norm(u, axis=1)
    ip_max = np.max(ip_vm, axis=1) if ip_vm.size else np.zeros(elems.shape[0], dtype=float)
    ip_mean = np.mean(ip_vm, axis=1) if ip_vm.size else np.zeros(elems.shape[0], dtype=float)

    payload = {
        "schema_version": "AsterMaxTet10OfflineViewerPayloadV1",
        "geometry": {
            "coordinates_mm": nodes.tolist(),
            "boundary_tri6": boundary_tri6.tolist(),
            "surface_triangles": display_triangles.tolist(),
            "surface_owner_tet10": display_owner.tolist(),
            "rendering_note": "Each TRI6 is subdivided through its quadratic midside nodes; no corner-only reduction is used.",
        },
        "deformation": {
            "U_mm": u.tolist(),
            "U_MAG_mm": u_mag.tolist(),
        },
        "integration_point_fields": {
            "natural_point_count": 4,
            "STRESS_IP4_MPa": ip_stress.tolist(),
            "VON_MISES_IP4_MPa": ip_vm.tolist(),
        },
        "fields": {
            "U_MAG_mm": {
                "label": "Displacement magnitude",
                "location": "POINT",
                "unit": "mm",
                "values": u_mag.tolist(),
            },
            "VON_MISES_IP_MAX_MPa": {
                "label": "von Mises - max of 4 integration points",
                "location": "TET10_DERIVED_FROM_INTEGRATION_POINTS",
                "unit": "MPa",
                "values": ip_max.tolist(),
            },
            "VON_MISES_IP_MEAN_MPa": {
                "label": "von Mises - mean of 4 integration points",
                "location": "TET10_DERIVED_FROM_INTEGRATION_POINTS",
                "unit": "MPa",
                "values": ip_mean.tolist(),
            },
        },
        "provenance": {
            "result_class": str(result_class),
            "converged_claim": bool(converged_claim),
            "industrial_validation_claim": bool(industrial_validation_claim),
            "units": {"length": "mm", "force": "N", "stress": "MPa"},
            "stress_representation": "FOUR_INTEGRATION_POINTS_PRESERVED_NO_NODAL_SMOOTHING",
            "note": "Deformation scale changes display coordinates only. Stress contours are explicit element summaries of the four preserved integration-point values, never nodal extrapolation.",
        },
        "counts": {
            "nodes": int(nodes.shape[0]),
            "tet10": int(elems.shape[0]),
            "boundary_tri6": int(boundary_tri6.shape[0]),
            "rendered_triangles": int(display_triangles.shape[0]),
            "integration_points_per_element": 4,
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    payload["payload_sha256"] = _sha256_bytes(canonical)
    return payload


def _html_document(payload: dict) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>AsterMax TET10 Result Viewer</title>
<style>
html,body{{margin:0;height:100%;background:#0b1020;color:#e7ecf5;font-family:Segoe UI,Arial,sans-serif;overflow:hidden}}#app{{display:grid;grid-template-columns:1fr 350px;height:100%}}#stage{{position:relative;min-width:0}}canvas{{width:100%;height:100%;display:block;background:linear-gradient(#111a31,#080c17)}}#hud{{position:absolute;left:16px;top:14px;background:#0b1020dd;border:1px solid #38445e;border-radius:8px;padding:10px 12px;font-size:13px;pointer-events:none}}#panel{{padding:18px;background:#10172a;border-left:1px solid #34405a;overflow:auto}}h2{{margin:0 0 4px;font-size:20px}}.sub{{color:#9dabca;font-size:12px;margin-bottom:15px}}label{{display:block;font-size:12px;color:#aebbd5;margin:14px 0 6px}}select,input,button{{width:100%;box-sizing:border-box}}select,button{{background:#1b2742;color:#eef3ff;border:1px solid #425170;border-radius:6px;padding:8px}}button{{cursor:pointer;margin-top:7px}}input[type=range]{{accent-color:#8aa4ff}}.badge{{display:inline-block;padding:4px 7px;border-radius:5px;background:#553a16;color:#ffd38a;font-weight:600;font-size:11px;word-break:break-word}}.kpi{{display:grid;grid-template-columns:1fr auto;gap:7px;font-size:12px;padding:10px 0;border-top:1px solid #2d3850}}.muted{{color:#98a5be}}#legend{{height:14px;border-radius:4px;background:linear-gradient(90deg,hsl(240 80% 52%),hsl(180 80% 50%),hsl(60 85% 52%),hsl(0 85% 52%));margin-top:8px}}#legendText{{display:flex;justify-content:space-between;font-size:11px;color:#c7d0e2}}code{{font-size:10px;word-break:break-all;color:#aab8d4}}.warning{{font-size:11px;line-height:1.45;background:#201b13;border:1px solid #5b4827;border-radius:6px;padding:9px;color:#ffdba0}}
</style></head><body><div id=\"app\"><div id=\"stage\"><canvas id=\"c\"></canvas><div id=\"hud\"><strong>AsterMax TET10</strong><br><span id=\"hudField\"></span><br><span id=\"hudScale\"></span></div></div><aside id=\"panel\"><h2>Quadratic Result Viewer</h2><div class=\"sub\">Offline · TET10/TRI6 · provenance-safe</div><div class=\"badge\" id=\"classBadge\"></div><label>Result field</label><select id=\"field\"><option value=\"VON_MISES_IP_MAX_MPa\">von Mises - IP maximum</option><option value=\"VON_MISES_IP_MEAN_MPa\">von Mises - IP mean</option><option value=\"U_MAG_mm\">Displacement magnitude</option></select><label>Deformation scale <span id=\"scaleValue\"></span></label><input id=\"scale\" type=\"range\" min=\"0\" max=\"100\" step=\"1\" value=\"1\"><button id=\"autoScale\">Auto deformation scale</button><button id=\"resetView\">Reset camera</button><label><input id=\"wire\" type=\"checkbox\" checked style=\"width:auto\"> Show undeformed quadratic-edge subdivision</label><label>Legend</label><div id=\"legend\"></div><div id=\"legendText\"><span id=\"minVal\"></span><span id=\"maxVal\"></span></div><div class=\"kpi\"><span class=\"muted\">Nodes</span><span id=\"nodes\"></span><span class=\"muted\">TET10</span><span id=\"cells\"></span><span class=\"muted\">Boundary TRI6</span><span id=\"faces\"></span><span class=\"muted\">Gauss IP / TET10</span><span>4</span><span class=\"muted\">Converged</span><span id=\"conv\"></span><span class=\"muted\">Industrial validation</span><span id=\"industrial\"></span></div><div class=\"warning\">Stress is preserved at four integration points per TET10. Displayed stress contours are explicitly max/mean summaries of those values; AsterMax does not manufacture nodal stress in this gate.</div><label>Payload SHA-256</label><code id=\"hash\"></code><p class=\"sub\">Mouse drag: orbit · wheel: zoom. Deformation amplification is display-only.</p></aside></div><script id=\"astermax-data\" type=\"application/json\">{data}</script>
<script>(()=>{{'use strict';const D=JSON.parse(document.getElementById('astermax-data').textContent),c=document.getElementById('c'),ctx=c.getContext('2d');const P=D.geometry.coordinates_mm,U=D.deformation.U_mm,T=D.geometry.surface_triangles,O=D.geometry.surface_owner_tet10;let field='VON_MISES_IP_MAX_MPa',yaw=-.65,pitch=.42,zoom=1,deform=1,drag=false,lastX=0,lastY=0,W=0,H=0,S=1;const geom=(()=>{{let lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity],center=[0,0,0];for(const p of P)for(let k=0;k<3;k++){{lo[k]=Math.min(lo[k],p[k]);hi[k]=Math.max(hi[k],p[k]);center[k]+=p[k]/P.length}}return{{diag:Math.hypot(hi[0]-lo[0],hi[1]-lo[1],hi[2]-lo[2]),center}}}})(),diag=geom.diag,baseCenter=geom.center,maxU=Math.max(...D.deformation.U_MAG_mm,0);function vals(){{return D.fields[field].values}}function range(){{const v=vals();let a=Infinity,b=-Infinity;for(const x of v){{a=Math.min(a,x);b=Math.max(b,x)}}return[isFinite(a)?a:0,isFinite(b)?b:0]}}function color(v,a,b,alpha=.93){{const t=b>a?Math.max(0,Math.min(1,(v-a)/(b-a))):.5,h=240*(1-t);return`hsla(${{h}},82%,54%,${{alpha}})`}}function points(scale){{return P.map((p,i)=>[p[0]+U[i][0]*scale,p[1]+U[i][1]*scale,p[2]+U[i][2]*scale]).map(p=>{{let x=p[0]-baseCenter[0],y=p[1]-baseCenter[1],z=p[2]-baseCenter[2],cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch),x1=cy*x-sy*y,y1=sy*x+cy*y;return[x1,cp*y1-sp*z,sp*y1+cp*z]}})}}function drawMesh(q,stroke){{for(const tri of T){{ctx.beginPath();for(let j=0;j<3;j++){{const p=q[tri[j]],x=W/2+p[0]*S,y=H/2-p[1]*S;j?ctx.lineTo(x,y):ctx.moveTo(x,y)}}ctx.closePath();ctx.strokeStyle=stroke;ctx.lineWidth=.65;ctx.stroke()}}}}function draw(){{const r=c.getBoundingClientRect();W=r.width;H=r.height;ctx.clearRect(0,0,W,H);S=Math.min(W,H)*.68/Math.max(diag,1e-12)*zoom;const q=points(deform),rv=range(),v=vals(),order=T.map((tri,i)=>[i,(q[tri[0]][2]+q[tri[1]][2]+q[tri[2]][2])/3]).sort((a,b)=>a[1]-b[1]);for(const item of order){{const i=item[0],tri=T[i];let s;if(D.fields[field].location==='POINT')s=(v[tri[0]]+v[tri[1]]+v[tri[2]])/3;else s=v[O[i]];ctx.beginPath();for(let j=0;j<3;j++){{const p=q[tri[j]],x=W/2+p[0]*S,y=H/2-p[1]*S;j?ctx.lineTo(x,y):ctx.moveTo(x,y)}}ctx.closePath();ctx.fillStyle=color(s,rv[0],rv[1]);ctx.fill();ctx.strokeStyle='rgba(8,12,22,.38)';ctx.lineWidth=.4;ctx.stroke()}}if(document.getElementById('wire').checked)drawMesh(points(0),'rgba(232,238,252,.40)');document.getElementById('minVal').textContent=rv[0].toPrecision(5)+' '+D.fields[field].unit;document.getElementById('maxVal').textContent=rv[1].toPrecision(5)+' '+D.fields[field].unit;document.getElementById('hudField').textContent=D.fields[field].label+' ['+D.fields[field].unit+']';document.getElementById('hudScale').textContent='Deformation display scale: '+deform.toFixed(1)+'x'}}function setScale(v){{deform=Number(v);document.getElementById('scale').value=String(Math.max(0,Math.min(100,Math.round(deform))));document.getElementById('scaleValue').textContent=deform.toFixed(1)+'x';draw()}}function resize(){{const r=c.getBoundingClientRect(),d=devicePixelRatio||1;c.width=Math.max(1,Math.round(r.width*d));c.height=Math.max(1,Math.round(r.height*d));ctx.setTransform(d,0,0,d,0,0);draw()}}document.getElementById('field').onchange=e=>{{field=e.target.value;draw()}};document.getElementById('scale').oninput=e=>setScale(e.target.value);document.getElementById('autoScale').onclick=()=>setScale(maxU>0?Math.max(1,Math.min(100,.18*diag/maxU)):1);document.getElementById('resetView').onclick=()=>{{yaw=-.65;pitch=.42;zoom=1;draw()}};document.getElementById('wire').onchange=draw;c.addEventListener('pointerdown',e=>{{drag=true;lastX=e.clientX;lastY=e.clientY;c.setPointerCapture(e.pointerId)}});c.addEventListener('pointermove',e=>{{if(!drag)return;yaw+=(e.clientX-lastX)*.009;pitch=Math.max(-1.45,Math.min(1.45,pitch+(e.clientY-lastY)*.009));lastX=e.clientX;lastY=e.clientY;draw()}});c.addEventListener('pointerup',()=>drag=false);c.addEventListener('wheel',e=>{{e.preventDefault();zoom*=Math.exp(-e.deltaY*.001);zoom=Math.max(.18,Math.min(8,zoom));draw()}},{{passive:false}});document.getElementById('classBadge').textContent=D.provenance.result_class;document.getElementById('nodes').textContent=D.counts.nodes;document.getElementById('cells').textContent=D.counts.tet10;document.getElementById('faces').textContent=D.counts.boundary_tri6;document.getElementById('conv').textContent=D.provenance.converged_claim?'YES':'NO';document.getElementById('industrial').textContent=D.provenance.industrial_validation_claim?'YES':'NO';document.getElementById('hash').textContent=D.payload_sha256;setScale(1);addEventListener('resize',resize);resize()}})();</script></body></html>"""


def write_tet10_offline_viewer(
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
    payload = build_tet10_viewer_payload(
        nodes_mm,
        elements,
        result,
        result_class=result_class,
        converged_claim=converged_claim,
        industrial_validation_claim=industrial_validation_claim,
    )
    html = _html_document(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    html_hash = _sha256_bytes(output.read_bytes())
    manifest = Tet10OfflineViewerManifest(
        schema_version="AsterMaxTet10OfflineViewerManifestV1",
        result_class=str(result_class),
        units={"length": "mm", "force": "N", "stress": "MPa"},
        node_count=int(payload["counts"]["nodes"]),
        tet10_count=int(payload["counts"]["tet10"]),
        boundary_tri6_count=int(payload["counts"]["boundary_tri6"]),
        rendered_triangle_count=int(payload["counts"]["rendered_triangles"]),
        integration_points_per_element=4,
        stress_representation="FOUR_INTEGRATION_POINTS_PRESERVED_NO_NODAL_SMOOTHING",
        payload_sha256=str(payload["payload_sha256"]),
        html_sha256=html_hash,
        converged_claim=bool(converged_claim),
        industrial_validation_claim=bool(industrial_validation_claim),
    )
    output.with_suffix(output.suffix + ".manifest.json").write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest
