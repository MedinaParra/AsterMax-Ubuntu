param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.81 contract missing: $vtkPath"}
$v=[regex]::Replace((Get-Content $vtkPath -Raw),'\r\n?',"`n")
$required=@(
 'ASTERMAX_PERF_EDGE materialized=',
 'ASTERMAX_PERF_EDGE highlight-materialized=',
 '_asterMaxMaterializedElementEdgeActors',
 '_asterMaxDeferredElementEdgeActors',
 'AsterMaxDeferredElementEdgesRemaining',
 'AsterMaxPerfTraceEnabled',
 'actor.AsterMaxElementEdgesDeferred',
 'actor.AsterMaxEnsureElementEdges()',
 'actorToHighLight.AsterMaxEnsureElementEdges()'
)
foreach($token in $required){if(!$v.Contains($token)){throw "C10.81 contract missing token: $token"}}
$materializedTrace='ASTERMAX_PERF_EDGE materialized='
$highlightTrace='ASTERMAX_PERF_EDGE highlight-materialized='
if(([regex]::Matches($v,[regex]::Escape($materializedTrace))).Count -lt 1){throw 'C10.81 effective materialization trace missing.'}
if(([regex]::Matches($v,[regex]::Escape($highlightTrace))).Count -lt 1){throw 'C10.81 highlight materialization trace missing.'}
$effectivePath='(?s)actor\.AsterMaxElementEdgesDeferred\s*&&\s*actor\.AsterMaxEnsureElementEdges\(\).*?_asterMaxMaterializedElementEdgeActors\+\+.*?ASTERMAX_PERF_EDGE materialized='
if(-not [regex]::IsMatch($v,$effectivePath)){throw 'C10.81 effective deferred-edge path is not instrumented.'}
$highlightPath='(?s)actorToHighLight\.AsterMaxEnsureElementEdges\(\).*?_asterMaxMaterializedElementEdgeActors\+\+.*?ASTERMAX_PERF_EDGE highlight-materialized='
if(-not [regex]::IsMatch($v,$highlightPath)){throw 'C10.81 highlight deferred-edge path is not instrumented.'}
Write-Host 'PASS C10.81 deferred-edge effective materialization trace contract.' -ForegroundColor Green
