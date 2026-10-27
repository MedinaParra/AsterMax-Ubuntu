param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
python (Join-Path $PSScriptRoot 'patch-c1208-force-distribution.py') --root $Root
if($LASTEXITCODE -ne 0) { throw 'C12.08 force-distribution patch failed.' }
