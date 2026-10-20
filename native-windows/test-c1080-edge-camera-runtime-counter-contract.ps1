param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.80 contract missing: $vtkPath"}
$v=[regex]::Replace((Get-Content $vtkPath -Raw),'\r\n?',"`n")
$edgeTrace='ASTERMAX_PERF_EDGE request=' 
$edgeTraceCount=([regex]::Matches($v,[regex]::Escape($edgeTrace))).Count
$checks=[ordered]@{
 c1042_render_scheduled = $v.Contains('_asterMaxRenderScheduled')
 c1078_trace_gate = $v.Contains('ASTERMAX_PERF_TRACE')
 c1079_render_executed = $v.Contains('_asterMaxPerfRenderExecuted') -and $v.Contains('ASTERMAX_PERF_RENDER executed=')
 edge_counter_field = $v.Contains('_asterMaxPerfEdgeRequests')
 edge_counter_effective = $edgeTraceCount -eq 1 -and $v.Contains('_asterMaxPerfEdgeRequests++;')
 camera_counter_field = $v.Contains('_asterMaxPerfCameraRequests')
 camera_zoom_trace = $v.Contains('ASTERMAX_PERF_CAMERA type=zoom_fit request=')
 camera_isometric_trace = $v.Contains('ASTERMAX_PERF_CAMERA type=isometric request=')
 semantics_message = $v.Contains('SetZoomToFit(') -and $v.Contains('SetIsometricView(')
}
$failed=@($checks.GetEnumerator() | Where-Object { -not $_.Value })
$checks.GetEnumerator() | ForEach-Object { Write-Host ("{0}: {1}" -f $_.Key, $(if($_.Value){'PASS'}else{'FAIL'})) }
Write-Host ("edge_trace_occurrences: {0}" -f $edgeTraceCount)
if($failed.Count -gt 0){throw ('C10.80 contract failed: '+(($failed | ForEach-Object {$_.Key}) -join ', '))}
Write-Host 'C10.87 edge/camera runtime counter effectiveness contract PASS.' -ForegroundColor Green
