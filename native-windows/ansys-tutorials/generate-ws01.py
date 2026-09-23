#!/usr/bin/env python3
"""Build the exact ANSYS Mechanical WS01.1 cover case for AsterMax/Code_Aster.

Source geometry: Cap_fillets.stp from the public ANSYS Mechanical training bundle.
No FEA output is embedded. Surface groups are identified from the exact CAD topology
and are fail-closed against geometric signatures before meshing.
"""
import argparse, json, math, os
from pathlib import Path
import gmsh

PRESS = [39,11,176,174,6,2,7,12,175,170,10,8,172,9,169,171,173]
CBSUP = [1,17,18,19]
INSUP = [41,76,74,78,35,43,75,77]
LIPSUP = [13]

def close(a,b,tol): return abs(a-b) <= tol

def require_surface(surfaces, tag, kind=None, area=None, area_tol=None, center=None, center_tol=1e-5):
    if tag not in surfaces:
        raise RuntimeError(f"required CAD face {tag} missing")
    s=surfaces[tag]
    if kind and s["type"] != kind:
        raise RuntimeError(f"face {tag} type mismatch: {s['type']} != {kind}")
    if area is not None and not close(s["area"],area,area_tol):
        raise RuntimeError(f"face {tag} area mismatch: {s['area']} != {area}")
    if center:
        for i,(actual,expected) in enumerate(zip(s["center"],center)):
            if not close(actual,expected,center_tol):
                raise RuntimeError(f"face {tag} center[{i}] mismatch: {actual} != {expected}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--step",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--size",type=float,default=3.0)
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal",1)
        gmsh.model.add("WS01_1_Cap")
        imported=gmsh.model.occ.importShapes(args.step)
        gmsh.model.occ.synchronize()
        vols=gmsh.model.getEntities(3)
        faces=gmsh.model.getEntities(2)
        if len(vols)!=1 or len(faces)!=176:
            raise RuntimeError(f"exact WS01 topology mismatch: volumes={len(vols)}, faces={len(faces)}")
        surfaces={}
        for dim,tag in faces:
            surfaces[tag]={
                "type":gmsh.model.getType(dim,tag),
                "area":float(gmsh.model.occ.getMass(dim,tag)),
                "center":[float(x) for x in gmsh.model.occ.getCenterOfMass(dim,tag)],
                "bbox":[float(x) for x in gmsh.model.getBoundingBox(dim,tag)],
            }

        # Fail closed on anchor faces so a future STEP/topology change cannot silently
        # scope pressure/supports to the wrong geometry.
        require_surface(surfaces,39,"Plane",3640.457747946257,1e-4,[40.0,25.0,0.0],1e-5)
        require_surface(surfaces,13,"Plane",247.19281793413893,1e-4,[40.0,25.0,15.0],1e-5)
        for tag,center in [(1,[8,42,2]),(17,[72,8,2]),(18,[8,8,2]),(19,[72,42,2])]:
            require_surface(surfaces,tag,None,31.415926535897935,1e-5,center,1e-5)
        for tag in PRESS+CBSUP+INSUP+LIPSUP:
            if tag not in surfaces: raise RuntimeError(f"scoped face missing: {tag}")
        if len(set(PRESS))!=17 or len(set(INSUP))!=8 or len(set(CBSUP))!=4:
            raise RuntimeError("tutorial CAD scope cardinality mismatch")

        vol_tags=[t for _,t in vols]
        def physical(dim,tags,name):
            p=gmsh.model.addPhysicalGroup(dim,tags)
            gmsh.model.setPhysicalName(dim,p,name)
        physical(3,vol_tags,"ALLVOL")
        physical(2,PRESS,"PRESS")
        physical(2,CBSUP,"CBSUP")
        physical(2,INSUP,"INSUP")
        physical(2,LIPSUP,"LIPSUP")

        gmsh.option.setNumber("Mesh.ElementOrder",1)
        gmsh.option.setNumber("Mesh.MeshSizeMin",max(args.size/2.0,0.6))
        gmsh.option.setNumber("Mesh.MeshSizeMax",args.size)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature",10)
        gmsh.model.mesh.generate(3)
        node_tags,_,_=gmsh.model.mesh.getNodes()
        etypes,etags,_=gmsh.model.mesh.getElements(3)
        nelem=sum(len(x) for x in etags)
        med=out/"ws01.med"
        gmsh.write(str(med))

        comm=out/"ws01.comm"
        comm.write_text("""DEBUT()
mesh=LIRE_MAILLAGE(FORMAT='MED',UNITE=20)
model=AFFE_MODELE(MAILLAGE=mesh,AFFE=_F(GROUP_MA='ALLVOL',PHENOMENE='MECANIQUE',MODELISATION='3D'))
al=DEFI_MATERIAU(ELAS=_F(E=71000.0,NU=0.33))
mat=AFFE_MATERIAU(MAILLAGE=mesh,AFFE=_F(GROUP_MA='ALLVOL',MATER=al))
support=AFFE_CHAR_MECA(MODELE=model,FACE_IMPO=(
    _F(GROUP_MA='CBSUP',DNOR=0.0),
    _F(GROUP_MA='INSUP',DNOR=0.0),
    _F(GROUP_MA='LIPSUP',DNOR=0.0),
))
pressure=AFFE_CHAR_MECA(MODELE=model,PRES_REP=_F(GROUP_MA='PRESS',PRES=1.1))
result=MECA_STATIQUE(MODELE=model,CHAM_MATER=mat,EXCIT=(_F(CHARGE=support),_F(CHARGE=pressure)))
result=CALC_CHAMP(reuse=result,RESULTAT=result,CONTRAINTE=('SIGM_ELNO',),CRITERES=('SIEQ_ELNO',),FORCE=('REAC_NODA',))
IMPR_RESU(FORMAT='MED',UNITE=81,RESU=_F(RESULTAT=result))
FIN()
""",encoding="utf-8")
        export=out/"ws01.export"
        export.write_text("""P actions make_etude
P version stable
P mode interactif
P time_limit 1200
P memory_limit 4096
P ncpus 1
P mpi_nbcpu 1

F comm /analysis/ws01.comm D 1
F mmed /analysis/ws01.med D 20
F mess /analysis/ws01.mess R 6
F rmed /analysis/ws01.rmed R 81
""",encoding="utf-8")
        meta={
            "tutorial":"ANSYS Mechanical Release 17.0 WS01.1 Mechanical Basics",
            "geometry":os.path.basename(args.step),
            "topology":{"volumes":len(vols),"faces":len(faces)},
            "scope":{"pressure_faces":PRESS,"pressure_face_count":len(PRESS),
                     "counterbore_support":CBSUP,"inner_recess_support":INSUP,"lip_support":LIPSUP},
            "load":{"type":"pressure","magnitude_mpa":1.1},
            "supports":{"type":"frictionless-normal","code_aster":"FACE_IMPO/DNOR=0"},
            "material":{"name":"Aluminum Alloy","E_mpa":71000.0,"nu":0.33,"yield_mpa_for_safety_factor":280.0},
            "mesh":{"target_max_size_mm":args.size,"nodes":len(node_tags),"volume_elements":nelem,"order":1},
            "solver":"native Windows Code_Aster through AsterMax runner",
            "fea_values_invented":False,
        }
        (out/"ws01-input.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
        print(json.dumps(meta,indent=2))
    finally:
        gmsh.finalize()

if __name__=="__main__": main()
