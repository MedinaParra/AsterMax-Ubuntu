"""Mass and centroid from resolved bar centerlines. SI units.
No automatic geometry inference. Arc lengths/centroids must be supplied accurately.
Concrete volume is gross; embedded steel displaces concrete.
Do not include projecting dowels as embedded over their full length.
"""
import math,json
def calculate(gross_volume_m3,concrete_centroid_m,bars,
              concrete_density=2500.,steel_density=7850.):
    steel_volume=0.; steel_moment=[0.,0.,0.]
    displaced_volume=0.; displaced_moment=[0.,0.,0.]
    unresolved=[]
    for bar in bars:
        if not bar.get('geometry_resolved',False):
            unresolved.append(bar.get('mark','unknown'));continue
        area=math.pi*bar['diameter_m']**2/4
        for segment in bar['segments']:
            if 'length_m' in segment:
                length=segment['length_m'];centroid=segment['centroid_m']
            else:
                p,q=segment['start_m'],segment['end_m']
                length=math.dist(p,q);centroid=[(a+b)/2 for a,b in zip(p,q)]
            if length<=0:raise ValueError('zero or negative segment length')
            v=area*length;steel_volume+=v
            for k in range(3):steel_moment[k]+=v*centroid[k]
            if segment.get('embedded',True):
                displaced_volume+=v
                for k in range(3):displaced_moment[k]+=v*centroid[k]
    if unresolved:return {'status':'BLOCKED_UNRESOLVED_GEOMETRY','marks':unresolved}
    if displaced_volume>=gross_volume_m3:raise ValueError('steel displacement invalid')
    mass=concrete_density*(gross_volume_m3-displaced_volume)+steel_density*steel_volume
    moment=[concrete_density*(gross_volume_m3*concrete_centroid_m[k]-displaced_moment[k])
            +steel_density*steel_moment[k] for k in range(3)]
    return {'status':'GEOMETRIC_MASS_ONLY_NOT_FEA','mass_kg':mass,
       'centroid_m':[m/mass for m in moment],
       'steel_mass_kg':steel_density*steel_volume,
       'net_concrete_mass_kg':concrete_density*(gross_volume_m3-displaced_volume),
       'gross_concrete_volume_m3':gross_volume_m3,
       'embedded_steel_displacement_m3':displaced_volume,
       'limitations':['input curves must be non-overlapping physical steel',
        'rings, laps, hooks, anchors and recesses must all be explicitly included',
        'diameters are ideal cylinders; ribbed-bar nominal mass may differ',
        'no structural capacity is implied']}
if __name__=='__main__':
    import sys
    data=json.load(sys.stdin)
    print(json.dumps(calculate(**data),indent=2))
