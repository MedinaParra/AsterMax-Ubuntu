#!/usr/bin/env python3
import json, pathlib, re

root = pathlib.Path(__file__).resolve().parent
mail = root / 'step_mm.mail'
comm = root / 'step_mm.comm'
pre = root / 'C8_40_PRE_SOLVE.json'

e = json.loads(pre.read_text(encoding='utf-8'))
count = int(e['load_nodes'])
if count < 1:
    raise SystemExit('No load nodes available')
force_per_node = float(e['nominal_resultant_N']) / count

# Keep only the volume mesh plus node groups in the Code_Aster MAIL file.
# The imported STEP face triangulation remains measured/provenanced in PRE_SOLVE,
# but nodal loading avoids coupling the first solver qualification to skin-element semantics.
lines = mail.read_text(encoding='utf-8').splitlines()
out=[]
i=0
while i < len(lines):
    s=lines[i].strip()
    if s == 'TRIA3':
        i += 1
        while i < len(lines) and lines[i].strip() != 'FINSF':
            i += 1
        if i < len(lines): i += 1
        continue
    if s.startswith('GROUP_MA NOM=LOAD_FACE'):
        i += 1
        while i < len(lines) and lines[i].strip() != 'FINSF':
            i += 1
        if i < len(lines): i += 1
        continue
    out.append(lines[i]); i += 1
mail.write_text('\n'.join(out)+'\n', encoding='utf-8')

text = comm.read_text(encoding='utf-8')
old = "load=AFFE_CHAR_MECA(MODELE=model,DDL_IMPO=_F(GROUP_NO='FIXED',DX=0.0,DY=0.0,DZ=0.0),PRES_REP=_F(GROUP_MA='LOAD_FACE',PRES=5.0))"
new = "load=AFFE_CHAR_MECA(MODELE=model,DDL_IMPO=_F(GROUP_NO='FIXED',DX=0.0,DY=0.0,DZ=0.0),FORCE_NODALE=_F(GROUP_NO='LOADN',FX=%.17g))" % force_per_node
if old not in text and new not in text:
    raise SystemExit('Expected load anchor not found in generated COMM')
text = text.replace(old, new)
comm.write_text(text, encoding='utf-8')

e['solver_load_application'] = 'equal nodal FX over geometric x=100 face node group'
e['solver_force_per_load_node_N'] = force_per_node
e['solver_force_sum_N'] = force_per_node * count
e['pressure_MPa'] = 5.0  # nominal axial stress oracle, not the solver load primitive in C8.40.1
pre.write_text(json.dumps(e, indent=2), encoding='utf-8')
print(json.dumps({'load_nodes':count,'force_per_node_N':force_per_node,'sum_N':force_per_node*count}, indent=2))
