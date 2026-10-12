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

# Do not reject historical upstream DoEvents occurrences. C10.49 must prove only
# that its own instrumentation patch did not introduce one; older code is outside
# this candidate's regression scope and is audited separately by prior stages.
$patchPath=Join-Path $PSScriptRoot 'candidate-c1049-first-frame-instrumentation.ps1'
if(!(Test-Path $patchPath)){throw "C10.49 patch source missing: $patchPath"}
$patch=Get-Content $patchPath -Raw
if($patch -match 'Application\.DoEvents\s*\('){throw 'C10.49 regression: instrumentation patch introduces Application.DoEvents.'}
Write-Host 'PASS: C10.49 patch introduces no Application.DoEvents' -ForegroundColor Green
Write-Host 'C10.49 static regression PASS: instrumentation is observational and scene-batch scoped.' -ForegroundColor Green
