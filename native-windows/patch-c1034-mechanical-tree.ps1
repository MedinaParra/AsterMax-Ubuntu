param([string]$Root)
$ErrorActionPreference='Stop'
python "$PSScriptRoot/c1034-mechanical-tree.py" --root $Root
if($LASTEXITCODE -ne 0){throw 'C10.34 mechanical tree patch failed.'}
