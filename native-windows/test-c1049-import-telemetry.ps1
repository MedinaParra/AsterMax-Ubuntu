param([string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.49 test missing: $vtkPath"}
$v=Get-Content $vtkPath -Raw
$checks=[ordered]@{
  add_cells_counter_field=$v.Contains('private long _asterMaxSceneBatchAddCellsCalls;')
  render_request_counter_field=$v.Contains('private long _asterMaxSceneBatchRenderRequests;')
  add_cells_public_counter=$v.Contains('public long AsterMaxSceneBatchAddCellsCalls')
  render_request_public_counter=$v.Contains('public long AsterMaxSceneBatchRenderRequests')
  add_cells_counter_reset=$v.Contains('_asterMaxSceneBatchAddCellsCalls = 0;')
  render_request_counter_reset=$v.Contains('_asterMaxSceneBatchRenderRequests = 0;')
  add_cells_instrumented=$v.Contains('if (_asterMaxSceneBatchDepth > 0) _asterMaxSceneBatchAddCellsCalls++;')
}
$failed=@($checks.GetEnumerator()|Where-Object{-not $_.Value})
$checks.GetEnumerator()|ForEach-Object{Write-Host ("{0}={1}" -f $_.Key, $(if($_.Value){'PASS'}else{'FAIL'}))}
if($failed.Count -gt 0){throw ('C10.49 static telemetry guards failed: '+(($failed|ForEach-Object{$_.Key}) -join ', '))}
Write-Host 'C10.49 static telemetry guards PASS.' -ForegroundColor Green
