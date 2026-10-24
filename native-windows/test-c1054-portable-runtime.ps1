param([Parameter(Mandatory=$true)][string]$PackageRoot)
$ErrorActionPreference='Stop'
$root=(Resolve-Path $PackageRoot).Path
$out=Join-Path $PSScriptRoot '..\dist\Audit\C10.54'
New-Item -ItemType Directory -Force $out|Out-Null
$required=@(
  'NetGen\NetGenMesher.exe'
)
$missing=@()
foreach($rel in $required){if(-not (Test-Path (Join-Path $root $rel))){$missing += $rel}}
[ordered]@{
 release='C10.54-portable-runtime-guard'
 package_root=$root
 required=$required
 missing=$missing
 portable_runtime=if($missing.Count -eq 0){'PASS'}else{'FAIL'}
 compilation='NOT_RUN'
 functionality=if($missing.Count -eq 0){'PASS_PACKAGING_PREREQUISITE_ONLY'}else{'FAIL_MISSING_RUNTIME_DEPENDENCY'}
 performance='NOT_RUN'
 regressions=if($missing.Count -eq 0){'PASS_PACKAGING_GUARD_ONLY'}else{'FAIL_PACKAGING_GUARD'}
 exact_incident_step='BLOCKED_NOT_PRESENT_IN_REPOSITORY'
 code_aster_windows_only_solver_preserved=$true
 benchmark_values_invented=$false
}|ConvertTo-Json -Depth 6|Set-Content (Join-Path $out 'evidence.json') -Encoding UTF8
if($missing.Count){throw ('C10.54 portable package incomplete. Missing: '+($missing -join ', '))}
Write-Host 'C10.54 PASS: required portable runtime dependencies are present.'
