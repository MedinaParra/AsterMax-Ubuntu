param([string]$BuildRoot)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $BuildRoot 'vtkControl/vtkControl.cs'
$controllerPath = Join-Path $BuildRoot 'PrePoMax/Controller.cs'
foreach($p in @($vtkPath,$controllerPath)){ if(!(Test-Path $p)){ throw "C10.42 test missing: $p" } }

$v = Get-Content $vtkPath -Raw
$c = Get-Content $controllerPath -Raw

$checks = [ordered]@{
    'render scheduled field' = $v.Contains('private bool _asterMaxRenderScheduled;')
    'render request coalescing' = $v.Contains('if (_asterMaxRenderScheduled) return;')
    'single queued invalidation' = $v.Contains('BeginInvoke(new Action(() =>') -and $v.Contains('_asterMaxRenderScheduled = false;')
    'large assembly threshold env' = $c.Contains('ASTERMAX_LARGE_ASSEMBLY_PARTS')
    'large assembly default threshold' = $c.Contains('int asterMaxLargeAssemblyThreshold = 80;')
    'large assembly edge suppression' = $c.Contains('CurrentEdgesVisibility = vtkEdgesVisibility.NoEdges;')
    'exact geometry retained' = $c.Contains('Keep the CAD/BREP exact; only simplify the initial graphics path.')
}

$failed=@($checks.GetEnumerator() | Where-Object { -not $_.Value })
foreach($item in $checks.GetEnumerator()){
    Write-Host ((if($item.Value){'PASS'}else{'FAIL'}) + ' - ' + $item.Key)
}
if($failed.Count -gt 0){ throw ('C10.42 static regression failed: ' + (($failed | ForEach-Object {$_.Key}) -join ', ')) }

Write-Host 'C10.42 static regression PASS.' -ForegroundColor Green
