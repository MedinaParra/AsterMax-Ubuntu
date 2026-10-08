"""Analytical load scenarios only. No anchor selection or construction approval."""
import math,json
out=[]
for name,vol,L in [('M1',1.84,8.),('M2',1.6,8.),('M3',1.25,6.25)]:
    # M1 inclined surface actual area; assumed 400 mm run and 400 mm drop.
    A=L if name!='M1' else L-.4+math.hypot(.4,.4)
    G=vol*2500*9.80665/1000
    row=dict(module=name,concrete_reference_weight_kN=G,base_contact_m2=A,
      free_lift_reference_kN=1.3*G,scenarios=[])
    for q in (1.,2.,3.):
        total=G+q*A
        row['scenarios'].append(dict(q_adh_kPa=q,adhesion_kN=q*A,
          demould_static_total_kN=total,
          ideal_equalized_four_point_kN=total/4,
          two_effective_points_kN=total/2,
          sensitivity_1p3_times_entire_demould_load_kN=1.3*total))
    out.append(row)
report={'status':'ANALYTICAL_SCENARIOS_NOT_FEA_NOT_APPROVED',
 'notes':['reference concrete weights omit detailed steel quantity correction',
 'q=1 kPa is catalogue minimum reference for lubricated steel, not upper bound',
 'q=2,3 kPa are sensitivity scenarios, not measured steel mould adhesion',
 'dynamic multiplier on entire demould load is sensitivity, not prescribed load combination',
 'four-point equalization must be ensured by actual rig',
 'partial release needs spatial loads and torsion analysis',
 'no anchor capacity or reinforcement diameter is implied'],
 'results':out}
print(json.dumps(report,indent=2))
