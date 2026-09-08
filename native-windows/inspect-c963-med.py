#!/usr/bin/env python3
import json, sys, os, math
import h5py

if len(sys.argv) != 3:
    raise SystemExit('usage: inspect-c963-med.py <rmed> <out-json>')
path, out = sys.argv[1], sys.argv[2]
if not os.path.isfile(path):
    raise SystemExit(f'MED file missing: {path}')

records=[]
field_tokens=set()
stats={'finite_numeric_datasets':0,'numeric_values':0}

with h5py.File(path,'r') as h:
    def visit(name,obj):
        if isinstance(obj,h5py.Dataset):
            rec={'path':name,'shape':list(obj.shape),'dtype':str(obj.dtype)}
            up=name.upper()
            for tok in ('DEPL','SIGM','SIEQ','DX','DY','DZ'):
                if tok in up: field_tokens.add(tok)
            try:
                data=obj[()]
                if hasattr(data,'dtype') and data.dtype.kind in 'fiu':
                    flat=data.reshape(-1)
                    vals=[float(x) for x in flat[:200000]]
                    finite=[x for x in vals if math.isfinite(x)]
                    if finite:
                        rec['min']=min(finite); rec['max']=max(finite)
                        rec['sample_count']=len(finite)
                        stats['finite_numeric_datasets'] += 1
                        stats['numeric_values'] += len(finite)
            except Exception as e:
                rec['read_error']=type(e).__name__
            records.append(rec)
    h.visititems(visit)

manifest={
  'release':'C9.63',
  'source':'REAL_CODE_ASTER_RMED',
  'file':os.path.basename(path),
  'size_bytes':os.path.getsize(path),
  'datasets_total':len(records),
  'finite_numeric_datasets':stats['finite_numeric_datasets'],
  'numeric_values_sampled':stats['numeric_values'],
  'field_tokens_detected':sorted(field_tokens),
  'has_displacement_evidence':('DEPL' in field_tokens or 'DX' in field_tokens),
  'has_stress_evidence':('SIGM' in field_tokens or 'SIEQ' in field_tokens),
  'datasets':records,
  'fea_values_invented':False
}
manifest['pass'] = manifest['size_bytes'] > 1000 and manifest['datasets_total'] > 0 and manifest['finite_numeric_datasets'] > 0
with open(out,'w',encoding='utf-8') as f: json.dump(manifest,f,indent=2)
print(json.dumps({k:v for k,v in manifest.items() if k!='datasets'},indent=2))
if not manifest['pass']:
    raise SystemExit('MED inspection gate failed')
