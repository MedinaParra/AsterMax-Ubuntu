param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.81 missing: $vtkPath"}
$v=[regex]::Replace((Get-Content $vtkPath -Raw),'\r\n?',"`n")
if(!$v.Contains('_asterMaxDeferredElementEdgeActors')){throw 'C10.81 requires C10.48 lazy element edges.'}
if(!$v.Contains('_asterMaxMaterializedElementEdgeActors')){throw 'C10.81 requires C10.48 materialization telemetry.'}
if(!$v.Contains('AsterMaxPerfTraceEnabled')){throw 'C10.81 requires C10.78 runtime trace helper.'}
if(!$v.Contains('ASTERMAX_PERF_EDGE materialized=')){
 $pattern='(?m)^(?<indent>\s*)if \(actor\.AsterMaxElementEdgesDeferred && actor\.AsterMaxEnsureElementEdges\(\)\)\s*\r?\n\s*_asterMaxMaterializedElementEdgeActors\+\+;'
 $rx=[regex]::new($pattern)
 $matches=$rx.Matches($v)
 if($matches.Count -ne 1){throw "C10.81 deferred-edge materialization anchor expected 1 structural match, got $($matches.Count)."}
 $indent=$matches[0].Groups['indent'].Value
 $replacement=$indent+'if (actor.AsterMaxElementEdgesDeferred && actor.AsterMaxEnsureElementEdges())'+"`n"+
              $indent+'{'+"`n"+
              $indent+'    _asterMaxMaterializedElementEdgeActors++;'+"`n"+
              $indent+'    if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace("ASTERMAX_PERF_EDGE materialized=" + _asterMaxMaterializedElementEdgeActors + " deferred=" + _asterMaxDeferredElementEdgeActors + " remaining=" + AsterMaxDeferredElementEdgesRemaining);'+"`n"+
              $indent+'}'
 $v=$rx.Replace($v,$replacement,1)
}
if(!$v.Contains('ASTERMAX_PERF_EDGE highlight-materialized=')){
 $pattern='(?m)^(?<indent>\s*)if \(actorToHighLight\.AsterMaxEnsureElementEdges\(\)\)\s*_asterMaxMaterializedElementEdgeActors\+\+;'
 $rx=[regex]::new($pattern)
 $matches=$rx.Matches($v)
 if($matches.Count -ne 1){throw "C10.81 highlight edge materialization anchor expected 1 structural match, got $($matches.Count)."}
 $indent=$matches[0].Groups['indent'].Value
 $replacement=$indent+'if (actorToHighLight.AsterMaxEnsureElementEdges())'+"`n"+
              $indent+'{'+"`n"+
              $indent+'    _asterMaxMaterializedElementEdgeActors++;'+"`n"+
              $indent+'    if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace("ASTERMAX_PERF_EDGE highlight-materialized=" + _asterMaxMaterializedElementEdgeActors + " deferred=" + _asterMaxDeferredElementEdgeActors + " remaining=" + AsterMaxDeferredElementEdgesRemaining);'+"`n"+
              $indent+'}'
 $v=$rx.Replace($v,$replacement,1)
}
Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.81 effective deferred-edge materialization tracing applied; no edge/render behavior changed.' -ForegroundColor Green
