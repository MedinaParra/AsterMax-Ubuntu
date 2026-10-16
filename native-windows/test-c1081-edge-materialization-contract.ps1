param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.81 contract missing: $vtkPath"}
$v=[regex]::Replace((Get-Content $vtkPath -Raw),'\r\n?',"`n")
$required=@(
 'ASTERMAX_PERF_EDGE materialized=',
 'ASTERMAX_PERF_EDGE highlight-materialized=',
 'AsterMaxDeferredElementEdgesMaterialized',
 'AsterMaxDeferredElementEdgesRemaining',
 'AsterMaxPerfTraceEnabled'
)
foreach($token in $required){if(!$v.Contains($token)){throw "C10.81 contract missing token: $token"}}
if(!$v.Contains('MaterializeDeferredElementEdges')){throw 'C10.81 deferred-edge materialization method missing.'}
Write-Host 'PASS C10.81 deferred-edge effective materialization trace contract.' -ForegroundColor Green
