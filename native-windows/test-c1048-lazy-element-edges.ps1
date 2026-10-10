param([string]$Root)
$ErrorActionPreference='Stop'

$actorPath=Join-Path $Root 'vtkControl/vtkMax/Actor/vtkMaxActor.cs'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
foreach($p in @($actorPath,$vtkPath)){ if(!(Test-Path $p)){ throw "C10.48 test missing: $p" } }

$a=Get-Content $actorPath -Raw
$v=Get-Content $vtkPath -Raw
$candidatePath=Join-Path $PSScriptRoot 'candidate-c1048-lazy-element-edges.ps1'
$wrapperPath=Join-Path $PSScriptRoot 'candidate-c1048-lazy-element-edges-v2.ps1'
$auditPath=Join-Path $PSScriptRoot 'candidate-c1048-runtime-audit.ps1'
foreach($p in @($candidatePath,$wrapperPath,$auditPath)){ if(!(Test-Path $p)){ throw "C10.48 source guard missing: $p" } }
$candidateText=Get-Content $candidatePath -Raw
$wrapperText=Get-Content $wrapperPath -Raw
$auditText=Get-Content $auditPath -Raw

$checks=[ordered]@{
  'deferred actor state exists'=$a.Contains('_asterMaxElementEdgesDeferred')
  'placeholder actor retained'=$a.Contains('Keep a lightweight actor so historical transforms/visibility calls remain valid.') -and $a.Contains('_elementEdges = vtkActor.New();')
  'deferred topology skips second polydata update'=$a.Contains('polyEdges = extractEdges ? vtkPolyData.New() : null;') -and $a.Contains('if (extractEdges) polyEdges.Update();')
  'lazy materializer uses existing geometry mapper'=$a.Contains('extractEdges.SetInput(_geometryMapper.GetInputAsDataSet());')
  'lazy edge actor remains non-pickable'=$a.Contains('_elementEdges.PickableOff();')
  'copy path materializes before mapper copy'=$a.Contains('if (sourceActor.AsterMaxElementEdgesDeferred) sourceActor.AsterMaxEnsureElementEdges();')
  'animation path materializes before point mutation'=$a.Contains('C10.48 animation edge materialization')
  'defer limited to active scene batch'=$v.Contains('_asterMaxSceneBatchDepth > 0')
  'defer limited to NoEdges'=$v.Contains('_edgesVisibility == vtkEdgesVisibility.NoEdges')
  'defer limited to base renderer'=$v.Contains('data.Layer == vtkRendererLayer.Base')
  'defer limited to actors supporting element edges'=$v.Contains('data.CanHaveElementEdges')
  'ElementEdges mode materializes deferred topology'=$v.Contains('if (_edgesVisibility == vtkEdgesVisibility.ElementEdges) AsterMaxEnsureDeferredElementEdges();')
  'highlight materializes before edge mapper access'=$v.Contains('actorToHighLight.AsterMaxEnsureElementEdges();')
  'telemetry counts deferred actors'=$v.Contains('_asterMaxDeferredElementEdgeActors++')
  'telemetry counts materialized actors'=$v.Contains('_asterMaxMaterializedElementEdgeActors++')
  'geometry cell locator path retained'=$a.Contains('_cellLocator.LazyEvaluationOn();')
  'no CAD/FEM/solver mutation markers'=(-not $a.Contains('TET4')) -and (-not $a.Contains('TET10')) -and (-not $v.Contains('Code_Aster'))
  'C10.48 candidate and audit add no Application.DoEvents'=(-not $candidateText.Contains('Application.DoEvents')) -and (-not $wrapperText.Contains('Application.DoEvents')) -and (-not $auditText.Contains('Application.DoEvents'))
}

$failed=@($checks.GetEnumerator()|Where-Object{-not $_.Value})
foreach($item in $checks.GetEnumerator()){
  $status=if($item.Value){'PASS'}else{'FAIL'}
  Write-Host ($status+' - '+$item.Key)
}
if($failed.Count -gt 0){throw ('C10.48 static regression failed: '+(($failed|ForEach-Object{$_.Key}) -join ', '))}
Write-Host 'C10.48 static regression PASS: lazy element edges are constrained to initial NoEdges CAD scene batches.' -ForegroundColor Green
