import math,json,pathlib
root=pathlib.Path('evidence');root.mkdir(exist_ok=True)
L=8.; a=L*(math.sqrt(2)-1)/2; area=math.pi*.016**2/4
for level,h in enumerate([.4,.2,.1]):
 p=root/('mesh%d'%level);p.mkdir(exist_ok=True)
 xs=sorted(set(round(v,9) for v in [i*h for i in range(round(L/h)+1)]+[.058+.2*i for i in range(40)]+[7.942,a,L-a,.058]))
 ys=sorted(set(round(v,9) for v in [i/(4*2**level) for i in range(4*2**level+1)]+[.058,.208,.358,.642,.792,.942]))
 zs=sorted(set(round(v,9) for v in [-.2+i*.2/(2*2**level) for i in range(2*2**level+1)]+[-.142,-.126,-.1,-.074,-.058]))
 nodes={};coords={};eid=0;els=[];conc=[];steel=[]
 for i,x in enumerate(xs):
  for j,y in enumerate(ys):
   for k,z in enumerate(zs):
    n=len(nodes)+1;nodes[i,j,k]=n;coords[n]=(x,y,z)
 def add(kind,ns,group):
  global eid
  eid+=1;els.append((kind,eid,ns));group.append(eid)
 for i in range(len(xs)-1):
  for j in range(len(ys)-1):
   for k in range(len(zs)-1):
    add('HEXA8',[nodes[i,j,k],nodes[i+1,j,k],nodes[i+1,j+1,k],nodes[i,j+1,k],nodes[i,j,k+1],nodes[i+1,j,k+1],nodes[i+1,j+1,k+1],nodes[i,j+1,k+1]],conc)
 def nearest(arr,v):return min(range(len(arr)),key=lambda n:abs(arr[n]-v))
 for y in [.058,.208,.358,.642,.792,.942]:
  j=nearest(ys,y)
  for z in [-.074,-.126]:
   k=nearest(zs,z)
   for i in range(len(xs)-1):
    if xs[i]>=.058-1e-8 and xs[i+1]<=7.942+1e-8:add('SEG2',[nodes[i,j,k],nodes[i+1,j,k]],steel)
 for x in [.058+.2*i for i in range(40)]+[7.942]:
  i=nearest(xs,x)
  for z in [-.058,-.142]:
   k=nearest(zs,z)
   for j in range(len(ys)-1):
    if ys[j]>=.058-1e-8 and ys[j+1]<=.942+1e-8:add('SEG2',[nodes[i,j,k],nodes[i,j+1,k]],steel)
 supports=[nodes[nearest(xs,x),j,nearest(zs,-.1)] for x in [a,L-a] for j in [0,len(ys)-1]]
 lines=['TITRE','FABIAN M2 LINEAR PERFECT BOND SCREENING','FINSF','COOR_3D']
 lines += ['N%d %.10g %.10g %.10g'%(n,*xyz) for n,xyz in coords.items()];lines+=['FINSF']
 for typ in ['HEXA8','SEG2']:
  lines += [typ]+['E%d '%e+' '.join('N%d'%n for n in ns) for t,e,ns in els if t==typ]+['FINSF']
 def grp(typ,name,ids,prefix):
  lines.extend([typ,name]);lines.extend(' '.join(prefix+str(n) for n in ids[i:i+12]) for i in range(0,len(ids),12));lines.append('FINSF')
 grp('GROUP_MA','CONC',conc,'E');grp('GROUP_MA','STEEL',steel,'E');grp('GROUP_NO','SUPPORT',supports,'N')
 grp('GROUP_NO','PIN',[supports[0]],'N');grp('GROUP_NO','GUIDE',[supports[2]],'N');grp('GROUP_NO','ALLN',list(coords),'N')
 lines.append('FIN');(p/'case.mail').write_text('\n'.join(lines)+'\n')
 comm=f'''DEBUT()
mesh=LIRE_MAILLAGE(FORMAT='ASTER',UNITE=20)
model=AFFE_MODELE(MAILLAGE=mesh,AFFE=(_F(GROUP_MA='CONC',PHENOMENE='MECANIQUE',MODELISATION='3D'),_F(GROUP_MA='STEEL',PHENOMENE='MECANIQUE',MODELISATION='BARRE')))
concrete=DEFI_MATERIAU(ELAS=_F(E=28.e9,NU=.2,RHO=2500.))
steel=DEFI_MATERIAU(ELAS=_F(E=200.e9,NU=.3,RHO=5350.))
mat=AFFE_MATERIAU(MAILLAGE=mesh,AFFE=(_F(GROUP_MA='CONC',MATER=concrete),_F(GROUP_MA='STEEL',MATER=steel)))
cara=AFFE_CARA_ELEM(MODELE=model,BARRE=_F(GROUP_MA='STEEL',SECTION='GENERALE',CARA='A',VALE={area}))
bc=AFFE_CHAR_MECA(MODELE=model,DDL_IMPO=(_F(GROUP_NO='SUPPORT',DZ=0.),_F(GROUP_NO='PIN',DX=0.,DY=0.),_F(GROUP_NO='GUIDE',DY=0.)))
grav=AFFE_CHAR_MECA(MODELE=model,PESANTEUR=_F(GRAVITE=9.80665,DIRECTION=(0.,0.,-1.)))
res=MECA_STATIQUE(MODELE=model,CHAM_MATER=mat,CARA_ELEM=cara,EXCIT=(_F(CHARGE=bc),_F(CHARGE=grav)))
res=CALC_CHAMP(reuse=res,RESULTAT=res,CONTRAINTE=('SIGM_ELNO',),FORCE=('REAC_NODA',))
disp=POST_RELEVE_T(ACTION=_F(OPERATION='EXTRACTION',INTITULE='DISPLACEMENTS',RESULTAT=res,NOM_CHAM='DEPL',GROUP_NO='ALLN',NOM_CMP=('DX','DY','DZ'),TOUT_ORDRE='OUI'))
reaction=POST_RELEVE_T(ACTION=_F(OPERATION='EXTRACTION',INTITULE='REACTIONS',RESULTAT=res,NOM_CHAM='REAC_NODA',GROUP_NO='SUPPORT',NOM_CMP=('DX','DY','DZ'),TOUT_ORDRE='OUI'))
IMPR_TABLE(TABLE=disp,UNITE=80)
IMPR_TABLE(TABLE=reaction,UNITE=82)
IMPR_RESU(FORMAT='MED',UNITE=81,RESU=_F(RESULTAT=res))
FIN()
'''
 (p/'case.comm').write_text(comm)
 export='P actions make_etude\nP version 15.2\nP mode interactif\nP memory_limit 4096\nP time_limit 900\nP ncpus 1\nP mpi_nbcpu 1\n'
 for typ,ext,mode,unit in [('comm','comm','D',1),('mail','mail','D',20),('mess','mess','R',6),('resu','resu','R',80),('rmed','rmed','R',81),('resu','reactions','R',82)]:export+=f'F {typ} /analysis/mesh{level}/case.{ext} {mode} {unit}\n'
 (p/'case.export').write_text(export)
 steel_length=sum(math.dist(coords[ns[0]],coords[ns[1]]) for t,e,ns in els if t=='SEG2')
 data={'nodes':len(nodes),'solids':len(conc),'bars':len(steel),'expected_weight_N':(4000+5350*area*steel_length)*9.80665,'support_x_m':[a,L-a],'E_concrete_assumed_Pa':28e9,'steel_density_increment_kg_m3':5350,'state':'NOT_RUN','limitations':['linear elastic uncracked concrete','perfect bond by shared nodes','no anchors or local anchor capacity','no demould adhesion or dynamics','bar bends and laps omitted','solid concrete not subtracted at bars; additive stiffness approximation','assumed concrete modulus, not measured at demoulding']}
 (p/'INPUT.json').write_text(json.dumps(data,indent=2))
 print(level,data['nodes'],data['solids'],data['bars'])
