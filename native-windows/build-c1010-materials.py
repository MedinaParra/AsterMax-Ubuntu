"""Build a native PrePoMax material library with editable reference elastic models."""
import argparse, json, html
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
rows=[
 ('Aceros','Acero_Estructural_Referencia',210000,0.30,7850,'','Plantilla genérica AsterMax; no representa un grado ni lote certificado.'),
 ('Aceros','Inoxidable_304_Referencia',193000,0.30,8000,'https://www.thyssenkrupp-materials.co.uk/stainless-steel-304-14301.html','E y densidad de ficha del proveedor; Poisson 0,30 es un supuesto editable de esta plantilla.'),
 ('Aceros','Inoxidable_316_Referencia',200000,0.30,8000,'https://www.thyssenkrupp-materials.co.uk/stainless-steel-316-14401.html','E y densidad a 20 °C de ficha del proveedor; Poisson 0,30 es un supuesto editable de esta plantilla.'),
 ('Aluminios','Aluminio_6061_T6_Referencia',68900,0.33,2700,'https://www.aerospacemetals.com/wp-content/uploads/2023/06/Aluminum-6061-T6-6061-T651.pdf','Datos típicos; Poisson estimado en la fuente. No son valores admisibles de diseño.'),
 ('Aluminios','Aluminio_7075_T6_Referencia',71700,0.33,2810,'https://www.aerospacemetals.com/wp-content/uploads/2023/06/Aluminum-7075-T6-7075-T651.pdf','Datos típicos de la ficha; no son valores admisibles de diseño.'),
 ('Titanio','Titanio_Ti6Al4V_Recocido_Referencia',113800,0.342,4430,'https://www.aerospacemetals.com/wp-content/uploads/2023/07/Titanium-Ti-6Al-4V-Grade-5-Annealed.pdf','Grado 5 recocido; propiedades elásticas de referencia de la ficha.')
]
def item(name,tag=None): return dict(Name=name,Active=True,Visible=True,Valid=True,Internal=False,Expanded=True,Items=[],Tag=tag)
root=item('AsterMax_Materiales_Referencia');groups={}
for family,name,e,nu,rho,source,note in rows:
    if family not in groups:
        groups[family]=item(family);root['Items'].append(groups[family])
    description='Elasticidad lineal isotrópica, referencia ambiente. '+note+' Ajustar al material real antes de evaluar el diseño. Fuente: '+(source or 'Plantilla genérica AsterMax')
    material=dict(Name=name,Active=True,Visible=True,Valid=True,Internal=False,TemperatureDependent=False,Description=description,
        Properties=[{'$type':'CaeModel.Elastic, CaeModel','YoungsPoissonsTemp':[[e,nu,20.0]]},
                    {'$type':'CaeModel.Density, CaeModel','DensityTemp':[[rho*1e-12,20.0]]}])
    groups[family]['Items'].append(item(name,material))
(out/'AsterMaxReferenceMaterials.lib').write_text(json.dumps(root,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'Audit').mkdir(exist_ok=True)
report='''<!doctype html><html lang="es"><meta charset="utf-8"><title>AsterMax — Materiales</title>
<style>body{font:16px system-ui;max-width:1150px;margin:35px auto;color:#213043}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #cdd6df;text-align:left}th{background:#eaf1fa}.note{background:#fff3c4;padding:16px}</style>
<h1>Biblioteca de materiales AsterMax C10.10.1</h1><p>Materiales → Biblioteca → seleccionar material → copiar al modelo → guardar → Asignar sección.</p>
<p class="note">Seis referencias elásticas editables. No incluyen plasticidad, rotura ni fatiga. Los supuestos están identificados en cada descripción. Conservar en el modelo solo el material que se utilizará: el puente actual admite un material por cálculo.</p>
<p>Propiedades a temperatura ambiente. La biblioteca nativa usa MPa y ton/mm³; la tabla presenta densidad en kg/m³. La copia al modelo utiliza el conversor de unidades nativo. La densidad queda almacenada; el puente estático actual no utiliza masa ni gravedad.</p>
<table><tr><th>Material</th><th>E (MPa)</th><th>ν</th><th>ρ (kg/m³)</th><th>Referencia / supuesto</th></tr>'''
for family,name,e,nu,rho,source,note in rows:
    ref=('<a href="'+html.escape(source,quote=True)+'">Ficha del proveedor</a>. ') if source else ''
    report+='<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in (name,e,nu,rho))+'<td>'+ref+html.escape(note)+'</td></tr>'
report+='</table><p>Compilación: el verificador carga este archivo con el deserializador nativo, prueba la copia desde el diálogo y comprueba propiedades, conversión de unidades y asignación a una pieza en modelos aislados. Evidencia: Validation/C10.10.1/*.buttons.json.</p></html>'
(out/'Audit'/'MATERIALS.html').write_text(report,encoding='utf-8')
print(json.dumps({'material_count':len(rows),'file':str(out/'AsterMaxReferenceMaterials.lib'),'native_density_unit':'ton/mm3'}))
