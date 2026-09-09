from pathlib import Path
import argparse, json

p=argparse.ArgumentParser()
p.add_argument('--nx',type=int,required=True); p.add_argument('--ny',type=int,required=True); p.add_argument('--nz',type=int,required=True)
p.add_argument('--name',required=True); p.add_argument('--out',required=True)
a=p.parse_args()
L=100.0; H=10.0; W=10.0; E=210000.0; NU=0.30; FY=-100.0
out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
node_id={}; nodes=[]; idx=1
for i in range(a.nx+1):
  for j in range(a.ny+1):
    for k in range(a.nz+1):
      node_id[(i,j,k)]=idx; nodes.append((idx,L*i/a.nx,H*j/a.ny,W*k/a.nz)); idx+=1
elems=[]; eid=1
for i in range(a.nx):
  for j in range(a.ny):
    for k in range(a.nz):
      c=[node_id[(i,j,k)],node_id[(i+1,j,k)],node_id[(i+1,j+1,k)],node_id[(i,j+1,k)],node_id[(i,j,k+1)],node_id[(i+1,j,k+1)],node_id[(i+1,j+1,k+1)],node_id[(i,j+1,k+1)]]
      elems.append((eid,c)); eid+=1
fixed=[node_id[(0,j,k)] for j in range(a.ny+1) for k in range(a.nz+1)]
load=[node_id[(a.nx,j,k)] for j in range(a.ny+1) for k in range(a.nz+1)]
mail=out/f'{a.name}.mail'
with mail.open('w',encoding='utf-8',newline='\n') as f:
  f.write(f'TITRE\nASTERMAX C9.82 {a.name} - {a.nx}x{a.ny}x{a.nz} HEXA8\nFINSF\nCOOR_3D\n')
  for n,x,y,z in nodes: f.write(f'N{n} {x:.9f} {y:.9f} {z:.9f}\n')
  f.write('FINSF\nHEXA8\n')
  for e,c in elems: f.write(f'E{e} '+ ' '.join(f'N{n}' for n in c)+'\n')
  f.write('FINSF\nGROUP_NO\nFIXED '+' '.join(f'N{n}' for n in fixed)+'\nFINSF\n')
  f.write('GROUP_NO\nLOAD '+' '.join(f'N{n}' for n in load)+'\nFINSF\nFIN\n')
load_per_node=FY/len(load)
comm=out/f'{a.name}.comm'
comm.write_text(f"""DEBUT()\nmesh=LIRE_MAILLAGE(FORMAT='ASTER',UNITE=20)\nmodel=AFFE_MODELE(MAILLAGE=mesh,AFFE=_F(TOUT='OUI',PHENOMENE='MECANIQUE',MODELISATION='3D'))\nsteel=DEFI_MATERIAU(ELAS=_F(E={E},NU={NU}))\nmatfield=AFFE_MATERIAU(MAILLAGE=mesh,AFFE=_F(TOUT='OUI',MATER=steel))\nfixed=AFFE_CHAR_MECA(MODELE=model,DDL_IMPO=_F(GROUP_NO='FIXED',DX=0.0,DY=0.0,DZ=0.0))\nload=AFFE_CHAR_MECA(MODELE=model,FORCE_NODALE=_F(GROUP_NO='LOAD',FY={load_per_node:.15g}))\nresult=MECA_STATIQUE(MODELE=model,CHAM_MATER=matfield,EXCIT=(_F(CHARGE=fixed),_F(CHARGE=load)))\nprobe=POST_RELEVE_T(ACTION=_F(OPERATION='EXTRACTION',INTITULE='FREE_FACE_DISPLACEMENT',RESULTAT=result,NOM_CHAM='DEPL',GROUP_NO='LOAD',NOM_CMP=('DX','DY','DZ'),TOUT_ORDRE='OUI'))\nIMPR_TABLE(TABLE=probe,UNITE=80)\nIMPR_RESU(FORMAT='MED',UNITE=81,RESU=_F(RESULTAT=result))\nFIN()\n""",encoding='utf-8')
export=out/f'{a.name}.export'
export.write_text(f"""P actions make_etude\nP version 15.2\nP mode interactif\nP time_limit 600\nP memory_limit 4096\nF comm /analysis/{a.name}.comm D 1\nF mail /analysis/{a.name}.mail D 20\nF mess /analysis/{a.name}.mess R 6\nF resu /analysis/{a.name}.resu R 80\nF rmed /analysis/{a.name}.rmed R 81\n""",encoding='utf-8')
meta={'name':a.name,'nx':a.nx,'ny':a.ny,'nz':a.nz,'nodes':len(nodes),'elements':len(elems),'fixed_nodes':len(fixed),'load_nodes':len(load),'load_per_node_N':load_per_node,'total_load_N':FY,'units':'mm-N-MPa'}
(out/f'{a.name}.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
print(json.dumps(meta))
