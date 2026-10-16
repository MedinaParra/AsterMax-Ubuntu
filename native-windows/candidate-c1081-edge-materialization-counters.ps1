param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.81 missing: $vtkPath"}
$v=[regex]::Replace((Get-Content $vtkPath -Raw),'\r\n?',"`n")
if(!$v.Contains('_asterMaxDeferredElementEdgeActors')){throw 'C10.81 requires C10.48 lazy element edges.'}
if(!$v.Contains('_asterMaxMaterializedElementEdgeActors')){throw 'C10.81 requires C10.48 materialization telemetry.'}
if(!$v.Contains('AsterMaxPerfTraceEnabled')){throw 'C10.81 requires C10.78 runtime trace helper.'}
$needle='                if (actor.AsterMaxElementEdgesDeferred && actor.AsterMaxEnsureElementEdges())`n                    _asterMaxMaterializedElementEdgeActors++;'
if(!$v.Contains('ASTERMAX_PERF_EDGE materialized=')){
 if(!$v.Contains($needle)){throw 'C10.81 deferred-edge materialization anchor missing.'}
 $replacement=@'
                if (actor.AsterMaxElementEdgesDeferred && actor.AsterMaxEnsureElementEdges())
                {
                    _asterMaxMaterializedElementEdgeActors++;
                    if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace("ASTERMAX_PERF_EDGE materialized=" + _asterMaxMaterializedElementEdgeActors + " deferred=" + _asterMaxDeferredElementEdgeActors + " remaining=" + AsterMaxDeferredElementEdgesRemaining);
                }
'@
 $v=$v.Replace($needle,$replacement.TrimEnd())
}
$highlight='                    if (actorToHighLight.AsterMaxEnsureElementEdges()) _asterMaxMaterializedElementEdgeActors++;'
if(!$v.Contains('ASTERMAX_PERF_EDGE highlight-materialized=')){
 if(!$v.Contains($highlight)){throw 'C10.81 highlight edge materialization anchor missing.'}
 $highlightReplacement=@'
                    if (actorToHighLight.AsterMaxEnsureElementEdges())
                    {
                        _asterMaxMaterializedElementEdgeActors++;
                        if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace("ASTERMAX_PERF_EDGE highlight-materialized=" + _asterMaxMaterializedElementEdgeActors + " deferred=" + _asterMaxDeferredElementEdgeActors + " remaining=" + AsterMaxDeferredElementEdgesRemaining);
                    }
'@
 $v=$v.Replace($highlight,$highlightReplacement.TrimEnd())
}
Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.81 effective deferred-edge materialization tracing applied; no edge/render behavior changed.' -ForegroundColor Green
