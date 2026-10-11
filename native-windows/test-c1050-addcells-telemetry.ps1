param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $p)){throw "C10.50 missing: $p"}
$v=Get-Content $p -Raw
$checks=[ordered]@{
  mapper_field='_asterMaxSceneBatchMapperInputs'
  renderer_field='_asterMaxSceneBatchRendererAdds'
  mapper_api='AsterMaxSceneBatchMapperInputs'
  renderer_api='AsterMaxSceneBatchRendererAdds'
  mapper_reset='_asterMaxSceneBatchMapperInputs = 0;'
  renderer_reset='_asterMaxSceneBatchRendererAdds = 0;'
  mapper_increment='_asterMaxSceneBatchMapperInputs++;'
  renderer_increment='_asterMaxSceneBatchRendererAdds++;'
}
foreach($c in $checks.GetEnumerator()){if(-not $v.Contains($c.Value)){throw "C10.50 static guard FAIL: $($c.Key)"}}
$add=$v.IndexOf('public void AddCells(vtkMaxActorData data)')
if($add -lt 0){throw 'C10.50 AddCells missing.'}
$mapper=$v.IndexOf('_asterMaxSceneBatchMapperInputs++;',$add)
$renderer=$v.IndexOf('_asterMaxSceneBatchRendererAdds++;',$add)
if($mapper -lt $add -or $renderer -lt $add){throw 'C10.50 counters are not located after AddCells entry.'}
Write-Host 'C10.50 static telemetry guards PASS.' -ForegroundColor Green
