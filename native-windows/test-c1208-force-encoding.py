"""Exercise the real source patch with a Windows cp1252 default text encoding."""
import argparse
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True, help='Generated C12.08 source tree')
parser.add_argument('--patch-script', default=str(Path(__file__).with_name('patch-c1208-force-distribution.py')))
args = parser.parse_args()
source = Path(args.root)
script = Path(args.patch_script).resolve()
paths = [
    'CaeModel/Steps/Loads/Load.cs', 'CaeModel/Steps/Loads/CLoad.cs',
    'CaeModel/Steps/StaticStep.cs',
    'CaeModel/FileInOut/Output/Calculix/Keywords/Step/Load/CalCLoad.cs',
    'PrePoMax/Forms/45_Load/ViewCLoad.cs', 'PrePoMax/AsterMaxModelContractBridge.cs',
    'PrePoMax/AsterMaxCodeAsterNativeExporter.cs',
    'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs', 'PrePoMax/PrePoMax.csproj',
]
read_text = Path.read_text

def windows_default_read(path, encoding=None, errors=None):
    return read_text(path, encoding=encoding or 'cp1252', errors=errors)

with tempfile.TemporaryDirectory(prefix='astermax-force-encoding-') as temp:
    target = Path(temp)
    for rel in paths:
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, target / rel)
    expected = (script.parent / 'AsterMaxForceDistribution.cs').read_bytes()
    with patch.object(Path, 'read_text', windows_default_read), patch.object(
            sys, 'argv', [str(script), '--root', str(target)]):
        runpy.run_path(str(script), run_name='__main__')
    actual = (target / 'PrePoMax/AsterMaxForceDistribution.cs').read_bytes()
    assert actual == expected, 'Source patch corrupted UTF-8 under Windows default encoding'
    assert 'ATENCIÓN' in actual.decode('utf-8')
print('PASS: real source patch preserves UTF-8 with simulated Windows cp1252 default')
