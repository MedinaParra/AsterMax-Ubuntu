param([string]$BuildRoot)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $BuildRoot 'vtkControl/vtkControl.cs'
$controllerPath = Join-Path $BuildRoot 'PrePoMax/Controller.cs'
$uiPath = Join-Path $BuildRoot 'PrePoMax/Forms/AsterMaxNativeUi.cs'
foreach($p in @($vtkPath,$controllerPath,$uiPath)){ if(!(Test-Path $p)){ throw "C10.42 test missing: $p" } }

$v = Get-Content $vtkPath -Raw
$c = Get-Content $controllerPath -Raw
$u = Get-Content $uiPath -Raw

$centerStart=$u.IndexOf('private void AsterMaxCenterImportedGeometry()')
$centerEnd=if($centerStart -ge 0){$u.IndexOf('private TabPage BuildRibbonPage',$centerStart)}else{-1}
$center=if($centerStart -ge 0 -and $centerEnd -gt $centerStart){$u.Substring($centerStart,$centerEnd-$centerStart)}else{''}

$checks = [ordered]@{
    'render scheduled field' = $v.Contains('private bool _asterMaxRenderScheduled;')
    'render request coalescing' = $v.Contains('if (_asterMaxRenderScheduled) return;')
    'single queued invalidation' = $v.Contains('_asterMaxRenderScheduled = false;')
    'CAD import depth transaction' = $c.Contains('private int _asterMaxCadImportDepth;') -and $c.Contains('bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;')
    'nested compound redraw suppressed' = $c.Contains('if (_asterMaxCadImportDepth == 0)') -and $c.Contains('UpdateAfterImport(".brep");')
    'CAD import runtime telemetry' = $c.Contains('AsterMax CAD import:') -and $c.Contains('asterMaxCadImportWatch.ElapsedMilliseconds')
    'large assembly threshold env' = $c.Contains('ASTERMAX_LARGE_ASSEMBLY_PARTS')
    'large assembly default threshold' = $c.Contains('int asterMaxLargeAssemblyThreshold = 80;')
    'large assembly edge suppression' = $c.Contains('CurrentEdgesVisibility = vtkEdgesVisibility.NoEdges;')
    'exact geometry retained' = $c.Contains('Keep the CAD/BREP exact; only simplify the initial graphics path.')
    'camera finalization marshalled to UI' = $center.Contains('if (InvokeRequired)') -and $center.Contains('BeginInvoke(new Action(AsterMaxCenterImportedGeometry))')
    'camera finalization deferred' = $center.Contains('BeginInvoke(new Action(() =>')
    'no duplicate controller redraw after import' = (-not $center.Contains('_controller.Redraw();'))
}

$failed=@($checks.GetEnumerator() | Where-Object { -not $_.Value })
foreach($item in $checks.GetEnumerator()){
    Write-Host ((if($item.Value){'PASS'}else{'FAIL'}) + ' - ' + $item.Key)
}
if($failed.Count -gt 0){ throw ('C10.42 static regression failed: ' + (($failed | ForEach-Object {$_.Key}) -join ', ')) }

Write-Host 'C10.42 static regression PASS.' -ForegroundColor Green
