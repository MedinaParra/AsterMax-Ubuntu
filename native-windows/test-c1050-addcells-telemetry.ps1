param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $p)){throw "C10.50 missing: $p"}
$v=Get-Content $p -Raw
$checks=[ordered]@{
  actor_field='_asterMaxSceneBatchActorConstructions'
  geometry_add_field='_asterMaxSceneBatchGeometryAdds'
  actor_api='AsterMaxSceneBatchActorConstructions'
  geometry_add_api='AsterMaxSceneBatchGeometryAdds'
  actor_reset='_asterMaxSceneBatchActorConstructions = 0;'
  geometry_add_reset='_asterMaxSceneBatchGeometryAdds = 0;'
  actor_increment='_asterMaxSceneBatchActorConstructions++;'
  geometry_add_increment='_asterMaxSceneBatchGeometryAdds++;'
}
foreach($c in $checks.GetEnumerator()){if(-not $v.Contains($c.Value)){throw "C10.50 static guard FAIL: $($c.Key)"}}
$add=$v.IndexOf('public void AddCells(vtkMaxActorData data)')
if($add -lt 0){throw 'C10.50 AddCells missing.'}
$actor=$v.IndexOf('_asterMaxSceneBatchActorConstructions++;',$add)
$geometryAdd=$v.IndexOf('_asterMaxSceneBatchGeometryAdds++;',$add)
$ctor=$v.IndexOf('vtkMaxActor actor = new vtkMaxActor(data);',$add)
$dispatch=$v.IndexOf('AddActorGeometry(actor, data.Layer);',$add)
if($actor -lt $add -or $geometryAdd -lt $add){throw 'C10.50 counters are not located after AddCells entry.'}
if($ctor -lt 0 -or $dispatch -lt 0){throw 'C10.50 expected AddCells actor path missing.'}
if($actor -gt $ctor){throw 'C10.50 actor counter must precede vtkMaxActor construction.'}
if($geometryAdd -gt $dispatch){throw 'C10.50 geometry-add counter must precede AddActorGeometry dispatch.'}
Write-Host 'C10.50 static telemetry guards PASS: actual AddCells actor construction/geometry dispatch instrumented.' -ForegroundColor Green
