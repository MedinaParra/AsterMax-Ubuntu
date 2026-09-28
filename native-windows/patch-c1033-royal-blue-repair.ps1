param([string]$Root)
$ErrorActionPreference='Stop'
python "$PSScriptRoot/c1033-repair.py" --root $Root
if($LASTEXITCODE -ne 0){throw 'C10.33 source repair failed.'}
