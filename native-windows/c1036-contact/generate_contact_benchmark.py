#!/usr/bin/env python3
import argparse, hashlib, json, re
from pathlib import Path

def sha256(p):
    h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True)
    ap.add_argument("--name",default="astermax-c1036-contact")
    a=ap.parse_args()
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)

    # Two independent HEXA8 bodies touch at x=1 mm. Interface nodes are
    # intentionally duplicated so load transfer can only occur through contact.
    nodes={
      1:(0,0,0),2:(1,0,0),3:(1,1,0),4:(0,1,0),
      5:(0,0,1),6:(1,0,1),7:(1,1,1),8:(0,1,1),
      9:(1,0,0),10:(2,0,0),11:(2,1,0),12:(1,1,0),
      13:(1,0,1),14:(2,0,1),15:(2,1,1),16:(1,1,1),
    }
    # Surface ordering chosen with outward normals before MODI_MAILLAGE.
    vol_l=[1,2,3,4,5,6,7,8]
    vol_r=[9,10,11,12,13,14,15,16]
    master=[2,3,7,6]       # outward +X from left body
    slave=[9,13,16,12]     # outward -X from right body
    fixed=[1,4,5,8]
    drive=[10,11,14,15]

    mail=out/f"{a.name}.mail"
    lines=["TITRE","ASTERMAX C10.36 FRICTIONLESS CONTACT BENCHMARK","FINSF","COOR_3D"]
    for nid,(x,y,z) in nodes.items():
        lines.append(f"N{nid} {x} {y} {z}")
    lines += ["FINSF","HEXA8",
              "E1 "+" ".join(f"N{x}" for x in vol_l),
              "E2 "+" ".join(f"N{x}" for x in vol_r),
              "FINSF","QUAD4",
              "CM1 "+" ".join(f"N{x}" for x in master),
              "CS1 "+" ".join(f"N{x}" for x in slave),
              "FINSF",
              "GROUP_MA NOM = VOL_L","E1","FINSF",
              "GROUP_MA NOM = VOL_R","E2","FINSF",
              "GROUP_MA NOM = AM_M001","CM1","FINSF",
              "GROUP_MA NOM = AM_S001","CS1","FINSF",
              "GROUP_NO NOM = FIXED"," ".join(f"N{x}" for x in fixed),"FINSF",
              "GROUP_NO NOM = DRIVE"," ".join(f"N{x}" for x in drive),"FINSF",
              "FIN"]
    mail.write_text("\n".join(lines)+"\n",encoding="utf-8")

    comm=out/f"{a.name}.comm"
    comm.write_text("""DEBUT()
mesh=LIRE_MAILLAGE(FORMAT='ASTER',UNITE=20)
mesh=MODI_MAILLAGE(
    reuse=mesh,
    MAILLAGE=mesh,
    ORIE_PEAU_3D=(
        _F(GROUP_MA=('AM_M001',)),
        _F(GROUP_MA=('AM_S001',)),
    ),
)
model=AFFE_MODELE(
    MAILLAGE=mesh,
    AFFE=_F(GROUP_MA=('VOL_L','VOL_R'),PHENOMENE='MECANIQUE',MODELISATION='3D'),
)
steel=DEFI_MATERIAU(ELAS=_F(E=210000.0,NU=0.3))
matfield=AFFE_MATERIAU(
    MAILLAGE=mesh,
    AFFE=_F(GROUP_MA=('VOL_L','VOL_R'),MATER=steel),
)
fixed=AFFE_CHAR_MECA(
    MODELE=model,
    DDL_IMPO=_F(GROUP_NO='FIXED',DX=0.0,DY=0.0,DZ=0.0),
)
drive=AFFE_CHAR_MECA(
    MODELE=model,
    DDL_IMPO=_F(GROUP_NO='DRIVE',DX=-0.01,DY=0.0,DZ=0.0),
)
ramp=DEFI_FONCTION(
    NOM_PARA='INST',
    VALE=(0.0,0.0,1.0,1.0),
    PROL_GAUCHE='CONSTANT',
    PROL_DROITE='CONSTANT',
)
times=DEFI_LIST_REEL(DEBUT=0.0,INTERVALLE=_F(JUSQU_A=1.0,NOMBRE=10))
contact=DEFI_CONTACT(
    MODELE=model,
    FORMULATION='CONTINUE',
    FROTTEMENT='SANS',
    ALGO_RESO_CONT='NEWTON',
    ZONE=_F(
        GROUP_MA_MAIT='AM_M001',
        GROUP_MA_ESCL='AM_S001',
        CONTACT_INIT='INTERPENETRE',
    ),
)
result=STAT_NON_LINE(
    MODELE=model,
    CHAM_MATER=matfield,
    EXCIT=(
        _F(CHARGE=fixed),
        _F(CHARGE=drive,FONC_MULT=ramp),
    ),
    CONTACT=contact,
    COMPORTEMENT=_F(RELATION='ELAS',DEFORMATION='PETIT',TOUT='OUI'),
    INCREMENT=_F(LIST_INST=times),
    NEWTON=_F(MATRICE='TANGENTE',REAC_ITER=1),
    CONVERGENCE=_F(ITER_GLOB_MAXI=40),
)
result=CALC_CHAMP(
    reuse=result,
    RESULTAT=result,
    FORCE=('REAC_NODA',),
    CONTRAINTE=('SIGM_ELNO',),
    CRITERES=('SIEQ_ELNO',),
)
reaction=POST_RELEVE_T(
    ACTION=_F(
        OPERATION='EXTRACTION',
        INTITULE='FIXED_REACTIONS',
        RESULTAT=result,
        NOM_CHAM='REAC_NODA',
        GROUP_NO='FIXED',
        NOM_CMP=('DX','DY','DZ'),
        TOUT_ORDRE='OUI',
    ),
)
IMPR_TABLE(TABLE=reaction,UNITE=82)
IMPR_RESU(FORMAT='MED',UNITE=81,RESU=_F(RESULTAT=result))
FIN()
""",encoding="utf-8")

    export=out/f"{a.name}.export"
    export.write_text(f"""P actions make_etude
P version 15.2
P mode interactif
P time_limit 600
P memory_limit 4096
P ncpus 1
P mpi_nbcpu 1

F comm /analysis/{a.name}.comm D 1
F mail /analysis/{a.name}.mail D 20
F mess /analysis/{a.name}.mess R 6
F rmed /analysis/{a.name}.rmed R 81
F repe /analysis/{a.name}.reactions R 82
""",encoding="utf-8")

    meta={
      "release":"C10.36",
      "case":a.name,
      "solver_contact_formulation":"CONTINUE",
      "friction":"SANS",
      "contact_init":"INTERPENETRE",
      "interface_node_sets_are_distinct":True,
      "prescribed_displacement_mm":-0.01,
      "young_modulus_mpa":210000.0,
      "poisson":0.3,
      "expected_physics":"nonzero compressive reaction transmitted only through contact",
      "fea_values_invented":False,
      "input_sha256":{p.name:sha256(p) for p in (mail,comm,export)}
    }
    (out/f"{a.name}.input.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    print(json.dumps(meta,indent=2))

if __name__=="__main__":
    main()
