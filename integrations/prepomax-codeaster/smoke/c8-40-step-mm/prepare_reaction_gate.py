#!/usr/bin/env python3
import pathlib

root = pathlib.Path(__file__).resolve().parent
comm = root / 'step_mm.comm'
text = comm.read_text(encoding='utf-8')

old_calc = "res=CALC_CHAMP(reuse=res,RESULTAT=res,CONTRAINTE=('SIGM_ELNO','SIGM_NOEU'),DEFORMATION=('EPSI_ELNO','EPSI_NOEU'),CRITERES=('SIEQ_ELNO','SIEQ_NOEU'))"
new_calc = "res=CALC_CHAMP(reuse=res,RESULTAT=res,CONTRAINTE=('SIGM_ELNO','SIGM_NOEU'),DEFORMATION=('EPSI_ELNO','EPSI_NOEU'),CRITERES=('SIEQ_ELNO','SIEQ_NOEU'),FORCE=('REAC_NODA',))"
if old_calc in text:
    text = text.replace(old_calc, new_calc, 1)
elif new_calc not in text:
    raise SystemExit('CALC_CHAMP reaction patch anchor missing')

anchor = "IMPR_TABLE(TABLE=tm,TITRE='PPM_MISES',UNITE=8,FORMAT='TABLEAU',SEPARATEUR=';',FORMAT_R='1PE15.8',NOM_PARA=('NOEUD','VMIS'))\nFIN()"
replacement = "IMPR_TABLE(TABLE=tm,TITRE='PPM_MISES',UNITE=8,FORMAT='TABLEAU',SEPARATEUR=';',FORMAT_R='1PE15.8',NOM_PARA=('NOEUD','VMIS'))\ntr=CREA_TABLE(RESU=_F(RESULTAT=res,GROUP_NO='FIXED',NOM_CHAM='REAC_NODA',NOM_CMP=('DX','DY','DZ')))\nIMPR_TABLE(TABLE=tr,TITRE='PPM_REAC',UNITE=8,FORMAT='TABLEAU',SEPARATEUR=';',FORMAT_R='1PE15.8',NOM_PARA=('NOEUD','DX','DY','DZ'))\nFIN()"
if anchor in text:
    text = text.replace(anchor, replacement, 1)
elif "TITRE='PPM_REAC'" not in text:
    raise SystemExit('REACTION table patch anchor missing')

comm.write_text(text, encoding='utf-8')
print('C8.41 reaction extraction wired into genuine Code_Aster case')
