"""Inventory actual generated sources. Static binding is not functional certification."""
import argparse, csv, html, json, re
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',required=True);a=p.parse_args()
root=Path(a.root);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
files={str(f.relative_to(root)):f.read_text(encoding='utf-8-sig',errors='replace') for f in root.rglob('*.cs') if not any(x in f.parts for x in ('bin','obj','packages'))}
all_code='\n'.join(files.values())
rows=[]
for path,code in files.items():
    if not path.endswith('.Designer.cs'): continue
    for name,kind in re.findall(r'this\.(\w+)\s*=\s*new\s+[\w.]*\.(Button|ToolStripButton|ToolStripMenuItem|ToolStripDropDownButton)\s*\(',code):
        caption=re.search(r'this\.'+re.escape(name)+r'\.Text\s*=\s*"([^"\n]*)"',code)
        binding=re.search(r'this\.'+re.escape(name)+r'\.Click\s*\+=\s*new\s+[\w.]+\(this\.(\w+)\)',code)
        container=bool(re.search(r'this\.'+re.escape(name)+r'\.DropDownItems\.AddRange',code))
        handler=binding.group(1) if binding else ''
        state='CONTENEDOR' if container and not handler else 'ENLACE ESTATICO' if handler else 'REVISAR ENLACE DINAMICO/HEREDADO'
        rows.append(dict(area=path,control=name,label=caption.group(1) if caption else '',type=kind,handler=handler,status=state,execution='NO EJECUTADO'))
ui=files['PrePoMax/Forms/AsterMaxNativeUi.cs']; tab='';ribbon=[]
for line in ui.splitlines():
    m=re.search(r'BuildRibbonPage\("([^"]+)"',line)
    if m: tab=m.group(1)
    m=re.search(r'CommandTile\("([^"]+)",\s*"([^"]+)",\s*\(\)\s*=>\s*(.*)',line)
    if m:
        caption,group,action=m.groups(); action=action.rstrip(',')
        targets=re.findall(r'\b([A-Za-z_]\w*)\s*\(',action)
        missing=[x for x in targets if x not in {'PerformClick'} and not re.search(r'\b(?:public|private|internal|protected)\s+(?:(?:static|async|override|virtual|sealed)\s+)*[\w<>\[\],.?]+\s+'+re.escape(x)+r'\s*\(',all_code)]
        if missing: raise RuntimeError(f'Missing command method: {caption}: {missing}')
        ribbon.append(dict(area=tab,control=group,label=caption,type='CommandTile',handler=action,status='ENLACE ESTATICO',execution='NO EJECUTADO'))
assert len(ribbon)>=36, len(ribbon)
for name,data in [('ALL_BUTTONS.csv',rows),('RIBBON_BUTTONS.csv',ribbon)]:
    with (out/name).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
summary={'source_files':len(files),'source_lines':sum(len(c.splitlines()) for c in files.values()),'native_controls':len(rows),'ribbon_buttons':len(ribbon),'static_audit_only':True,'all_buttons_functionally_validated':False}
(out/'SOURCE_AUDIT.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
def table(data):
    fields=['area','label','control','handler','status','execution']
    return '<table><thead><tr>'+''.join('<th>'+x+'</th>' for x in fields)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(r[x]))+'</td>' for x in fields)+'</tr>' for r in data)+'</tbody></table>'
report='''<!doctype html><html lang="es"><meta charset="utf-8"><title>AsterMax C10.10 — Auditoría</title>
<style>body{font:15px system-ui;color:#213043;background:#f7f9fc;margin:32px}h1{color:#17619a}table{border-collapse:collapse;width:100%;background:white;margin:16px 0}td,th{border:1px solid #d5dce4;padding:8px;text-align:left;vertical-align:top}th{background:#e8eff6}td{overflow-wrap:anywhere}input{padding:12px;width:70%}.warning{padding:18px;background:#fff1b8}code{background:#e4ebf2}li{margin:8px}</style>
<h1>AsterMax C10.10 — Auditoría del código y controles</h1><p>Fecha: 15 septiembre 2026. Inventario del código generado que se compila, incluyendo ventanas nativas y menús.</p>
<p class="warning"><b>Alcance:</b> revisión estática global e inspección dirigida de integración. Un manejador conectado no demuestra que un botón complete su tarea. Las filas NO EJECUTADO no son aprobaciones funcionales. No se certifica ausencia de errores ni equivalencia completa con ANSYS.</p>'''
report+=f'<p><b>{summary["source_files"]}</b> archivos C# · <b>{summary["source_lines"]}</b> líneas · <b>{len(rows)}</b> controles nativos · <b>{len(ribbon)}</b> botones de cinta.</p>'
report+='''<h2>Cambios y hallazgos</h2><ul>
<li>Iconos nativos de colores en todos los botones de cinta; nombres accesibles y tooltips; comando View → Auditoria.</li>
<li>Iconos pequeños en árbol: ? obligatorio pendiente; i información/incompleto; ticket verde configuración validada. Amarillo señala secciones y datos pendientes. No se inventan resultados.</li>
<li>Type Analysis abre el selector/editor nativo. Run solo admite un estudio estático lineal; otros tipos permanecen incompletos para el puente.</li>
<li>Corregido riesgo: el puente etiquetaba cualquier tipo de paso como estático. Ahora rechaza pasos no estáticos/no lineales y apoyos o cargas inactivos/inválidos.</li>
<li>El exportador mantiene un material, un apoyo fijo y una fuerza nodal. No soporta contactos ni sistemas locales. Estados informativos no equivalen a pasos obligatorios.</li>
<li>El ticket verde confirma los criterios descritos en el tooltip. La malla requiere además estudio de convergencia; la estabilidad física no queda certificada por tener un apoyo.</li>
<li>Run todavía es síncrono: pendiente cancelación y ejecución asíncrona. El runtime Code_Aster sigue siendo externo en WSL2.</li>
<li>Asignaciones a regiones PartName requieren revisión: el validador heredado exige ElementSetName. Una sección existente por sí sola no debe obtener ticket verde.</li>
<li>Los resultados Code_Aster se abren en una ventana propia; integración total con el árbol nativo pendiente. Solution no muestra ticket de resultado sin evidencia.</li>
<li>Prueba Windows: inventario de botones con delegado e imagen, capturas por pestaña, árbol/cinta sin superposición, importación STEP y mallado reales. No ejecuta automáticamente comandos de edición o borrado.</li>
<li>Pendientes: pruebas interactivas de cada diálogo, rutas Cancelar, multiselección, DPI, persistencia de cada tipo de entidad y cálculo del proyecto del usuario.</li></ul>
<h2>Inventario completo</h2><input id="filter" placeholder="Buscar botón, ventana, manejador o estado…"><h3>Cinta</h3>'''+table(ribbon)+'<h3>Ventanas y menús nativos</h3>'+table(rows)+'''<script>document.getElementById('filter').oninput=function(){const q=this.value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));};</script></html>'''
(out/'BUTTON_AUDIT.html').write_text(report,encoding='utf-8')
print(json.dumps(summary))
