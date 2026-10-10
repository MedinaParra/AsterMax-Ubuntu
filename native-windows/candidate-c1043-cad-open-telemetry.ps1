param([string]$Root)
$ErrorActionPreference='Stop'

$impl = Join-Path $PSScriptRoot 'candidate-c1043-cad-open-telemetry-v2.ps1'
if(!(Test-Path $impl)){ throw "C10.43 v2 implementation missing: $impl" }
& $impl -Root $Root
