param([Parameter(Mandatory=$true)][string]$Root,[string]$OutDir)
$ErrorActionPreference='Stop'
$root=(Resolve-Path $Root).Path
$out=if($OutDir){$OutDir}else{Join-Path $PSScriptRoot '..\dist\Audit\C10.78'}
New-Item -ItemType Directory -Force $out|Out-Null
$controller=Get-Content (Join-Path $root 'PrePoMax\Controller.cs') -Raw
$vtk=Get-Content (Join-Path $root 'vtkControl\vtkControl.cs') -Raw
$checks=[ordered]@{
 cad_transaction=$controller.Contains('_asterMaxCadImportDepth')
 import_counter_marker=$controller.Contains('ASTERMAX_PERF_IMPORT')
 render_counter_marker=$vtk.Contains('ASTERMAX_PERF_RENDER')
 actor_counter_marker=$vtk.Contains('ASTERMAX_PERF_ACTOR')
 counters_diagnostic_only=$vtk.Contains('ASTERMAX_PERF_TRACE')
 render_coalescing=$vtk.Contains('_asterMaxRenderScheduled')
}
$failed=@($checks.GetEnumerator()|Where-Object{-not $_.Value})
[ordered]@{release='C10.78';scope='RUNTIME_COUNTER_CONTRACT_ONLY';checks=$checks;compilation='NOT_RUN';functionality=if($failed.Count){'FAIL_STATIC_CONTRACT'}else{'PASS_STATIC_CONTRACT'};performance='NOT_RUN';regressions='NOT_RUN';exact_step='BLOCKED_NOT_PRESENT';benchmark_values_invented=$false}|ConvertTo-Json -Depth 5|Set-Content (Join-Path $out 'evidence.json') -Encoding UTF8
if($failed.Count){throw ('C10.78 contract failure: '+(($failed|% Key)-join ', '))}
Write-Host 'C10.78 runtime counter contract PASS.' -ForegroundColor Green
