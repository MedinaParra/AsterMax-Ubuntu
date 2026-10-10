param([string]$BuildRoot)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $BuildRoot 'vtkControl/vtkControl.cs'
$controllerPath = Join-Path $BuildRoot 'PrePoMax/Controller.cs'
$uiPath = Join-Path $BuildRoot 'PrePoMax/Forms/AsterMaxNativeUi.cs'
foreach($p in @($vtkPath,$controllerPath,$uiPath)){ if(!(Test-Path $p)){ throw "C10.43 test missing: $p" } }

$v = Get-Content $vtkPath -Raw
$c = Get-Content $controllerPath -Raw
$u = Get-Content $uiPath -Raw

$centerStart=$u.IndexOf('private void AsterMaxCenterImportedGeometry()')
$centerEnd=if($centerStart -ge 0){ $u.IndexOf('private void',$centerStart+10) }else{-1}
if($centerStart -ge 0 -and $centerEnd -lt 0){ $centerEnd=$u.Length }
$center=if($centerStart -ge 0){ $u.Substring($centerStart,$centerEnd-$centerStart) }else{''}

$checks = [ordered]@{
    'full-open stopwatch retained beyond preparation' = $c.Contains('private System.Diagnostics.Stopwatch _asterMaxCadOpenWatch;') -and $c.Contains('Este valor NO es el tiempo total de apertura')
    'source SHA256 captured' = $c.Contains('System.Security.Cryptography.SHA256.Create()') -and $c.Contains('sha256=')
    'split job duration measured' = $c.Contains('asterMaxSplitWatch') -and $c.Contains('_asterMaxCadSplitMs')
    'BREP visualization duration measured' = $c.Contains('asterMaxBrepWatch') -and $c.Contains('_asterMaxCadBrepVisualizationMs')
    'model incorporation measured' = $c.Contains('asterMaxModelWatch') -and $c.Contains('_asterMaxCadModelIncorporationMs')
    'scene build measured' = $c.Contains('asterMaxSceneWatch') -and $c.Contains('_asterMaxCadSceneBuildMs')
    'Netgen submit count measured without claiming OS process count' = $c.Contains('_asterMaxCadNetgenSubmitCount++') -and $c.Contains('netgen_job_submits=')
    'update-after-import count measured' = $c.Contains('_asterMaxCadUpdateAfterImportCount++')
    'controller redraw count measured' = $c.Contains('_asterMaxCadRedrawCount++')
    'working set explicitly labels process peak' = $c.Contains('PeakWorkingSet64') -and $c.Contains('process_peak_working_set_mb=')
    'VTK render requests counted' = $v.Contains('_asterMaxPerfRenderRequests') -and $v.Contains('Interlocked.Increment(ref _asterMaxPerfRenderRequests)')
    'VTK AddCells counted' = $v.Contains('_asterMaxPerfAddCells') -and $v.Contains('Interlocked.Increment(ref _asterMaxPerfAddCells)')
    'VTK camera redraw path counted' = $v.Contains('_asterMaxPerfCameraAdjustRedraws') -and $v.Contains('Interlocked.Increment(ref _asterMaxPerfCameraAdjustRedraws)')
    'counter reset marshalled to UI owner' = $u.Contains('public void AsterMaxResetCadViewportCounters()') -and $u.Contains('Invoke(new Action(AsterMaxResetCadViewportCounters))')
    'completion belongs to import-center method' = $center.Contains('_vtk.Refresh();') -and $center.Contains('AsterMaxCompleteCadOpenTelemetry(_vtk.AsterMaxPerfRenderRequests') -and $center.IndexOf('AsterMaxCompleteCadOpenTelemetry') -gt $center.IndexOf('_vtk.Refresh();')
    'measurement names UI refresh not GPU presentation' = $c.Contains('total_to_visible_refresh_ms=')
    'no FEM mesh policy touched' = (-not $c.Contains('C10.43 TET4')) -and (-not $c.Contains('C10.43 TET10'))
}

$failed=@($checks.GetEnumerator() | Where-Object { -not $_.Value })
foreach($item in $checks.GetEnumerator()){
    $status = if($item.Value){ 'PASS' } else { 'FAIL' }
    Write-Host ($status + ' - ' + $item.Key)
}
if($failed.Count -gt 0){ throw ('C10.43 static regression failed: ' + (($failed | ForEach-Object {$_.Key}) -join ', ')) }
Write-Host 'C10.43 telemetry static regression PASS.' -ForegroundColor Green
