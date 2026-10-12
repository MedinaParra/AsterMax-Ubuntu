param([string]$Root)
$ErrorActionPreference='Stop'

$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.49 missing: $vtkPath"}
$v=Get-Content $vtkPath -Raw

$checks=[ordered]@{
 'AddCells counter field'='_asterMaxSceneBatchAddCells;'
 'scene flush request field'='_asterMaxSceneBatchRenderRequests;'
 'batch start ticks field'='_asterMaxSceneBatchStartedUtcTicks;'
 'batch end ticks field'='_asterMaxSceneBatchEndedUtcTicks;'
 'AddCells public telemetry'='AsterMaxSceneBatchAddCells { get { return _asterMaxSceneBatchAddCells; } }'
 'flush request public telemetry'='AsterMaxSceneBatchRenderRequests { get { return _asterMaxSceneBatchRenderRequests; } }'
 'start ticks public telemetry'='AsterMaxSceneBatchStartedUtcTicks { get { return _asterMaxSceneBatchStartedUtcTicks; } }'
 'end ticks public telemetry'='AsterMaxSceneBatchEndedUtcTicks { get { return _asterMaxSceneBatchEndedUtcTicks; } }'
 'batch start timestamp'='_asterMaxSceneBatchStartedUtcTicks = DateTime.UtcNow.Ticks;'
 'batch end timestamp'='_asterMaxSceneBatchEndedUtcTicks = DateTime.UtcNow.Ticks;'
 'AddCells increments only in scene batch'='if (_asterMaxSceneBatchDepth > 0) _asterMaxSceneBatchAddCells++;'
 'flush request increment'='_asterMaxSceneBatchRenderRequests++;'
}
foreach($kv in $checks.GetEnumerator()){
 if(-not $v.Contains($kv.Value)){throw "C10.49 static regression failed: $($kv.Key)"}
 Write-Host "PASS: $($kv.Key)" -ForegroundColor Green
}
if($v -match 'Application\.DoEvents\s*\('){throw 'C10.49 regression: Application.DoEvents introduced.'}
Write-Host 'C10.49 static regression PASS: instrumentation is observational and scene-batch scoped.' -ForegroundColor Green
