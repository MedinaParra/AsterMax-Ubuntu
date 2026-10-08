import sys,pathlib,json,re
for p in ['/usr/lib/freecad/lib','/usr/local/lib/freecad/lib','/usr/lib/freecad-python3/lib']:
    sys.path.insert(0,p)
import FreeCAD as App
import Part
root=pathlib.Path.cwd()
out=root/'step-output';out.mkdir(exist_ok=True)
macro=root/'engineering/fabian/Fabian_V4.FCMacro'
exec(compile(macro.read_text(),str(macro),'exec'),globals())
objects=[o for o in doc.Objects if hasattr(o,'Shape') and not o.Shape.isNull() and (
 re.fullmatch(r'L[12]_P\d+_M[123]',o.Name) or o.Name.startswith(('LongitudinalL','UL','ExtremoL','PasadoresL')))]
assert len([o for o in objects if re.fullmatch(r'L[12]_P\d+_M[123]',o.Name)])==20
invalid=[o.Name for o in objects if not o.Shape.isValid()]
if invalid:raise RuntimeError('Invalid shapes: '+str(invalid))
step=out/'Fabian_Modularizacion_V4_PRELIMINAR.step'
Part.export(objects,str(step))
assert step.stat().st_size>1000
doc.saveAs(str(out/'Fabian_Modularizacion_V4_PRELIMINAR.FCStd'))
shape=Part.Shape();shape.read(str(step))
assert not shape.isNull() and shape.isValid()
report={'status':'GEOMETRY_EXPORT_VALIDATED_NOT_DESIGN_APPROVAL',
 'freecad_version':App.Version(),'exported_objects':len(objects),
 'concrete_modules':20,'source_solids':sum(len(o.Shape.Solids) for o in objects),
 'reimported_solids':len(shape.Solids),'step_bytes':step.stat().st_size,
 'scope':'V4 macro including proposed reinforcement; source library excluded',
 'limitations':['not structural approval','positions and bend radius proposed','no lifting anchors or new joint definitions','steel crossings and cover not fully checked','no FEA']}
assert report['source_solids']==report['reimported_solids'],report
(out/'EXPORT_CHECK.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
