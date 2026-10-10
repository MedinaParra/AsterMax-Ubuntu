param([string]$Root)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
$mainPath = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
foreach($p in @($vtkPath,$mainPath,$controllerPath)){ if(!(Test-Path $p)){ throw "C10.47 test missing: $p" } }

$v=Get-Content $vtkPath -Raw
$m=Get-Content $mainPath -Raw
$c=Get-Content $controllerPath -Raw

$checks=[ordered]@{
    'scene batch depth field' = $v.Contains('_asterMaxSceneBatchDepth')
    'scene batch camera dirty flag' = $v.Contains('_asterMaxSceneBatchCameraDirty')
    'deferred camera telemetry' = $v.Contains('_asterMaxSceneBatchDeferredCameraAdjusts++')
    'single batch camera flush telemetry' = $v.Contains('_asterMaxSceneBatchCameraFlushes++')
    'batch begin marshals to VTK owner thread' = $v.Contains('Invoke(new Action(AsterMaxBeginSceneBatch))')
    'batch end marshals to VTK owner thread' = $v.Contains('Invoke(new Action(AsterMaxEndSceneBatch))')
    'underflow guarded' = $v.Contains('AsterMax scene batch underflow.')
    'AddCells defers camera while batch active' = $v.Contains('if (_asterMaxSceneBatchDepth > 0)') -and $v.Contains('else')
    'historical camera path retained outside batch' = $v.Contains('AdjustCameraDistanceAndClippingRedraw();')
    'FrmMain batch wrappers present' = $m.Contains('public void AsterMaxBeginVtkSceneBatch()') -and $m.Contains('public void AsterMaxEndVtkSceneBatch()')
    'Controller final draw enters batch' = $c.Contains('_form.AsterMaxBeginVtkSceneBatch();')
    'Controller final draw exits batch' = $c.Contains('_form.AsterMaxEndVtkSceneBatch();')
    'Controller final draw protected by finally' = $c.Contains('finally') -and $c.IndexOf('_form.AsterMaxEndVtkSceneBatch();') -gt $c.IndexOf('DrawGeometry(false);')
    'no Application.DoEvents added' = (-not $v.Contains('Application.DoEvents')) -and (-not $c.Contains('Application.DoEvents'))
    'no STL substitution' = (-not $c.Contains('C10.47 STL'))
    'no FEM meshing policy touched' = (-not $c.Contains('C10.47 TET4')) -and (-not $c.Contains('C10.47 TET10'))
}

$failed=@($checks.GetEnumerator()|Where-Object{-not $_.Value})
foreach($item in $checks.GetEnumerator()){
    $status=if($item.Value){'PASS'}else{'FAIL'}
    Write-Host ($status+' - '+$item.Key)
}
if($failed.Count -gt 0){ throw ('C10.47 static regression failed: '+(($failed|ForEach-Object{$_.Key}) -join ', ')) }
Write-Host 'C10.47 static regression PASS: per-actor camera work is deferred only inside the final CAD scene batch.' -ForegroundColor Green
