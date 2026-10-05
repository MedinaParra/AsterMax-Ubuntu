"""Reject ambiguous/missing field identity using copies of genuine solver output.

C10.10.1 rebuild marker: rerun the complete Windows package after enabling validated
TETRA4/TETRA10/HEXA8 result provenance in the C9.74 compatibility gate.
"""
import os, sys, tempfile, shutil, subprocess, json
from pathlib import Path
import h5py
bridge, source, report=map(Path,sys.argv[1:])
checks=[]
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    for case in ('ambiguous','missing','wrong_mesh'):
        med=root/(case+'.rmed');shutil.copyfile(source,med)
        with h5py.File(med,'r+') as h:
            name=next(n for n in h['CHA'] if n.endswith('__DEPL'))
            if case=='ambiguous':h.copy('CHA/'+name,'CHA/another__DEPL')
            elif case=='missing':del h['CHA'][name]
            else:h['CHA'][name].attrs['MAI']=b'OTHER_MESH'
        output=root/(case+'.json');vtu=root/(case+'.vtu')
        env=dict(os.environ,ASTERMAX_MED_BRIDGE_MODE='production')
        result=subprocess.run([sys.executable,str(bridge),str(med),str(output),str(vtu)],env=env,capture_output=True,text=True,timeout=30)
        assert result.returncode!=0 and not output.exists() and not vtu.exists(),case
        assert ('unambiguous' if case!='wrong_mesh' else 'different MED mesh') in result.stderr, result.stderr
        checks.append({'case':case,'rejected':True,'fea_values_generated':False})
report.write_text(json.dumps(checks,indent=2))
print(json.dumps(checks))
