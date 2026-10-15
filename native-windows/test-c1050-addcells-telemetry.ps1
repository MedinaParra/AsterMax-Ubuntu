param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $p)){throw "C10.50 missing: $p"}
$v=[regex]::Replace((Get-Content $p -Raw),"\r\n?","`n")
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
$brace=$v.IndexOf('{',$add);$depth=0;$end=-1
for($n=$brace;$n -lt $v.Length;$n++){if($v[$n]-eq '{'){$depth++}elseif($v[$n]-eq '}'){$depth--;if($depth-eq 0){$end=$n+1;break}}}
if($end -lt 0){throw 'C10.50 AddCells closing brace missing.'}
$m=$v.Substring($add,$end-$add)
$actor=$m.IndexOf('_asterMaxSceneBatchActorConstructions++;')
$geometryAdd=$m.IndexOf('_asterMaxSceneBatchGeometryAdds++;')
$assignment=[regex]::Match($m,'(?ms)^\s*vtkMaxActor\s+\w+\s*=\s*(?=[^;]*new\s+vtkMaxActor\s*\()[^;]+;')
$dispatches=[regex]::Matches($m,'(?m)^\s*AddActorGeometry\s*\([^;]*\)\s*;')
if($actor -lt 0 -or $geometryAdd -lt 0){throw 'C10.50 counters are not located inside AddCells.'}
if(-not $assignment.Success){throw 'C10.50 semantic vtkMaxActor assignment missing.'}
if($dispatches.Count -ne 1){throw "C10.50 expected exactly one AddActorGeometry invocation, got $($dispatches.Count)."}
if($actor -gt $assignment.Index){throw 'C10.50 actor counter must precede vtkMaxActor assignment.'}
if($geometryAdd -gt $dispatches[0].Index){throw 'C10.50 geometry-add counter must precede AddActorGeometry invocation.'}
Write-Host 'C10.50 static telemetry guards PASS: semantic AddCells actor assignment/geometry invocation instrumented.' -ForegroundColor Green