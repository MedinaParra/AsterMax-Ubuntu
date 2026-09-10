#!/usr/bin/env python3
import hashlib, json, math, pathlib, sys

import gmsh

ROOT = pathlib.Path(__file__).resolve().parent
STEP = ROOT / 'beam_100x20x10.step'
MAIL = ROOT / 'step_mm.mail'
COMM = ROOT / 'step_mm.comm'
EXPORT = ROOT / 'step_mm.export'
PRE = ROOT / 'C8_40_PRE_SOLVE.json'

L, W, H = 100.0, 20.0, 10.0
E = 210000.0
NU = 0.30
PRESSURE = 5.0  # MPa = N/mm^2, gives 1000 N over 20x10 mm face
EXPECTED_FORCE_N = PRESSURE * W * H
EXPECTED_DX_MM = EXPECTED_FORCE_N * L / (E * W * H)
TOL = 1.0e-6

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def fmt_group(items, width=8):
    lines=[]
    for i in range(0, len(items), width):
        lines.append(' ' + ' '.join(items[i:i+width]))
    return '\n'.join(lines)

# Pass 1: create canonical STEP in explicit mm geometry.
gmsh.initialize()
gmsh.option.setNumber('General.Terminal', 1)
gmsh.model.add('astermax_c8_40_step_source')
gmsh.model.occ.addBox(0.0, 0.0, 0.0, L, W, H)
gmsh.model.occ.synchronize()
gmsh.write(str(STEP))
gmsh.finalize()

if not STEP.exists() or STEP.stat().st_size < 1000:
    raise SystemExit('STEP generation failed or produced a trivial file')
step_hash = sha256(STEP)

# Pass 2: fresh kernel session, import STEP, verify mm scale, then mesh imported CAD.
gmsh.initialize()
gmsh.option.setNumber('General.Terminal', 1)
gmsh.option.setNumber('General.NumThreads', 1)
gmsh.option.setNumber('Mesh.MeshSizeMin', 7.5)
gmsh.option.setNumber('Mesh.MeshSizeMax', 7.5)
gmsh.option.setNumber('Mesh.ElementOrder', 1)
gmsh.option.setNumber('Mesh.Algorithm3D', 1)
gmsh.model.add('astermax_c8_40_step_import')
ents = gmsh.model.occ.importShapes(str(STEP))
gmsh.model.occ.synchronize()
vols = gmsh.model.getEntities(3)
if len(vols) != 1:
    raise SystemExit(f'Expected exactly one imported solid, got {vols}')
_, vtag = vols[0]
bb = gmsh.model.getBoundingBox(3, vtag)
dims = [bb[3]-bb[0], bb[4]-bb[1], bb[5]-bb[2]]
expected = [L, W, H]
for got, exp in zip(dims, expected):
    if abs(got-exp) > TOL:
        raise SystemExit(f'STEP mm scale gate failed: bbox dims={dims}, expected={expected}')

surfaces = gmsh.model.getEntities(2)
fixed_surfs=[]; load_surfs=[]
for dim, stag in surfaces:
    sbb = gmsh.model.getBoundingBox(dim, stag)
    if abs(sbb[0]) < TOL and abs(sbb[3]) < TOL:
        fixed_surfs.append(stag)
    if abs(sbb[0]-L) < TOL and abs(sbb[3]-L) < TOL:
        load_surfs.append(stag)
if not fixed_surfs or not load_surfs:
    raise SystemExit(f'Geometric face classification failed: fixed={fixed_surfs}, load={load_surfs}')

gmsh.model.mesh.generate(3)
node_tags, coords, _ = gmsh.model.mesh.getNodes()
node_tags = [int(x) for x in node_tags]
coord_map = {}
for i, tag in enumerate(node_tags):
    coord_map[tag] = (float(coords[3*i]), float(coords[3*i+1]), float(coords[3*i+2]))

etypes, etags, enodes = gmsh.model.mesh.getElements(3, vtag)
tets=[]
for typ, tags, conn in zip(etypes, etags, enodes):
    if int(typ) != 4:
        continue
    conn=[int(x) for x in conn]
    for i, eid in enumerate(tags):
        tets.append((int(eid), conn[4*i:4*i+4]))
if not tets:
    raise SystemExit('No TETRA4 elements generated from imported STEP')

# Collect load-face TRI3 elements from the geometric x=L face.
tris=[]
for stag in load_surfs:
    stypes, stags, snodes = gmsh.model.mesh.getElements(2, stag)
    for typ, tags, conn in zip(stypes, stags, snodes):
        if int(typ) != 2:
            continue
        conn=[int(x) for x in conn]
        for i, eid in enumerate(tags):
            tris.append((int(eid), conn[3*i:3*i+3]))
if not tris:
    raise SystemExit('No TRI3 elements found on imported STEP load face')

fixed_nodes = sorted({n for n,(x,y,z) in coord_map.items() if abs(x) < TOL})
load_nodes = sorted({n for n,(x,y,z) in coord_map.items() if abs(x-L) < TOL})
if len(fixed_nodes) < 3 or len(load_nodes) < 3:
    raise SystemExit(f'Boundary node gate failed: fixed={len(fixed_nodes)} load={len(load_nodes)}')

# Independent signed-volume gate on every tetra.
def signed_volume(ns):
    a,b,c,d = [coord_map[n] for n in ns]
    ax,ay,az = a; bx,by,bz=b; cx,cy,cz=c; dx,dy,dz=d
    ux,uy,uz = bx-ax, by-ay, bz-az
    vx,vy,vz = cx-ax, cy-ay, cz-az
    wx,wy,wz = dx-ax, dy-ay, dz-az
    det = ux*(vy*wz-vz*wy) - uy*(vx*wz-vz*wx) + uz*(vx*wy-vy*wx)
    return det/6.0
volumes=[signed_volume(ns) for _,ns in tets]
abs_vols=[abs(v) for v in volumes]
if not all(math.isfinite(v) and v > 1e-9 for v in abs_vols):
    raise SystemExit('Degenerate/non-finite tetra volume detected')

gmsh_version = gmsh.option.getString('General.Version')
gmsh.finalize()

# Normalize entity labels to a deterministic sequential Code_Aster MAIL namespace.
all_used = sorted(set(n for _,ns in tets for n in ns) | set(n for _,ns in tris for n in ns))
node_id = {old:i+1 for i,old in enumerate(all_used)}
node_name = {old:f'N{i+1}' for i,old in enumerate(all_used)}
tet_names=[]; tri_names=[]
lines=['TITRE',' AsterMax C8.40 STEP mm E2E benchmark','FINSF','COOR_3D']
for old in all_used:
    x,y,z=coord_map[old]
    lines.append(f' {node_name[old]} {x:.12g} {y:.12g} {z:.12g}')
lines += ['FINSF','TETRA4']
for i,(_,ns) in enumerate(tets,1):
    name=f'M{i}'; tet_names.append(name)
    lines.append(' '+name+' '+' '.join(node_name[n] for n in ns))
lines += ['FINSF','TRIA3']
for i,(_,ns) in enumerate(tris,1):
    name=f'F{i}'; tri_names.append(name)
    lines.append(' '+name+' '+' '.join(node_name[n] for n in ns))
lines += ['FINSF',f'GROUP_MA NOM=VOLUME_ALL NBOBJ={len(tet_names)}',fmt_group(tet_names),'FINSF',
          f'GROUP_MA NOM=LOAD_FACE NBOBJ={len(tri_names)}',fmt_group(tri_names),'FINSF']
fixed_names=[node_name[n] for n in fixed_nodes if n in node_name]
load_names=[node_name[n] for n in load_nodes if n in node_name]
lines += [f'GROUP_NO NOM=FIXED NBOBJ={len(fixed_names)}',fmt_group(fixed_names),'FINSF',
          f'GROUP_NO NOM=LOADN NBOBJ={len(load_names)}',fmt_group(load_names),'FINSF','FIN']
MAIL.write_text('\n'.join(lines)+'\n', encoding='utf-8')

COMM.write_text(f"""DEBUT()\n\nmesh=LIRE_MAILLAGE(FORMAT='ASTER',UNITE=20)\nmodel=AFFE_MODELE(MAILLAGE=mesh,AFFE=_F(GROUP_MA='VOLUME_ALL',PHENOMENE='MECANIQUE',MODELISATION='3D'))\nmat=DEFI_MATERIAU(ELAS=_F(E={E},NU={NU}))\nmatf=AFFE_MATERIAU(MAILLAGE=mesh,AFFE=_F(GROUP_MA='VOLUME_ALL',MATER=mat))\nload=AFFE_CHAR_MECA(MODELE=model,DDL_IMPO=_F(GROUP_NO='FIXED',DX=0.0,DY=0.0,DZ=0.0),PRES_REP=_F(GROUP_MA='LOAD_FACE',PRES={PRESSURE}))\nres=MECA_STATIQUE(MODELE=model,CHAM_MATER=matf,EXCIT=_F(CHARGE=load))\nres=CALC_CHAMP(reuse=res,RESULTAT=res,CONTRAINTE=('SIGM_ELNO','SIGM_NOEU'),DEFORMATION=('EPSI_ELNO','EPSI_NOEU'),CRITERES=('SIEQ_ELNO','SIEQ_NOEU'))\nIMPR_RESU(FORMAT='MED',UNITE=80,RESU=_F(MAILLAGE=mesh,RESULTAT=res,NOM_CHAM=('DEPL','SIGM_NOEU','SIEQ_NOEU','EPSI_NOEU'),TOUT_ORDRE='OUI'))\ntd=CREA_TABLE(RESU=_F(RESULTAT=res,TOUT='OUI',NOM_CHAM='DEPL',NOM_CMP=('DX','DY','DZ')))\nIMPR_TABLE(TABLE=td,TITRE='PPM_DEPL',UNITE=8,FORMAT='TABLEAU',SEPARATEUR=';',FORMAT_R='1PE15.8',NOM_PARA=('NOEUD','DX','DY','DZ'))\ntm=CREA_TABLE(RESU=_F(RESULTAT=res,TOUT='OUI',NOM_CHAM='SIEQ_NOEU',NOM_CMP=('VMIS',)))\nIMPR_TABLE(TABLE=tm,TITRE='PPM_MISES',UNITE=8,FORMAT='TABLEAU',SEPARATEUR=';',FORMAT_R='1PE15.8',NOM_PARA=('NOEUD','VMIS'))\nFIN()\n""", encoding='utf-8')

EXPORT.write_text("""P actions make_etude\nP version stable\nP time_limit 300\nP memory_limit 2048\nP ncpus 1\nP mpi_nbcpu 1\nP mpi_nbnoeud 1\nF comm step_mm.comm D 1\nF libr step_mm.mail D 20\nF mess step_mm.mess R 6\nF resu step_mm.resu R 8\nF rmed step_mm.rmed R 80\n""", encoding='utf-8')

evidence={
  'schema':'astermax.c8-40.step-mm-pre-solve.v1',
  'cad_source':'generated STEP then re-imported in fresh Gmsh/OpenCASCADE session',
  'step_sha256':step_hash,
  'step_units_contract':'mm',
  'bbox_mm':{'x':dims[0],'y':dims[1],'z':dims[2]},
  'expected_bbox_mm':{'x':L,'y':W,'z':H},
  'gmsh_version':gmsh_version,
  'mesher':'Gmsh/OpenCASCADE imported STEP -> first-order tetra mesh',
  'mesh_size_mm':7.5,
  'mesh_nodes':len(all_used),
  'tetra4_elements':len(tets),
  'load_face_tri3_elements':len(tris),
  'fixed_nodes':len(fixed_names),
  'load_nodes':len(load_names),
  'min_tet_abs_volume_mm3':min(abs_vols),
  'max_tet_abs_volume_mm3':max(abs_vols),
  'material':{'E_MPa':E,'nu':NU},
  'pressure_MPa':PRESSURE,
  'nominal_resultant_N':EXPECTED_FORCE_N,
  'analytic_axial_displacement_mm':EXPECTED_DX_MM,
  'bc_semantics':'x=0 geometric face fixed XYZ; x=100 geometric face receives pressure',
  'industrial_validation':False,
  'ansys_equivalence':False
}
PRE.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps(evidence,indent=2))
