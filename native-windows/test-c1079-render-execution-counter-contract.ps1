param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.79 missing: $vtkPath"}
$v=Get-Content $vtkPath -Raw
$required=@(
 '_asterMaxRenderScheduled',
 '_asterMaxPerfRenderRequests',
 '_asterMaxPerfRenderQueued',
 '_asterMaxPerfRenderExecuted',
 'ASTERMAX_PERF_RENDER request=',
 'ASTERMAX_PERF_RENDER queued=',
 'ASTERMAX_PERF_RENDER executed=',
 'Environment.GetEnvironmentVariable("ASTERMAX_PERF_TRACE") == "1"',
 'if (_asterMaxRenderScheduled) return;',
 'Invalidate();'
)
$missing=@($required|Where-Object{-not $v.Contains($_)})
$outDir=Join-Path (Split-Path $Root -Parent) 'dist/Audit/C10.79'
New-Item -ItemType Directory -Force -Path $outDir|Out-Null
$report=[ordered]@{
 version='C10.79'
 purpose='Static contract: distinguish render requests, queued paints and executed invalidations without changing C10.42 scheduling.'
 required=$required
 missing=$missing
 pass=($missing.Count -eq 0)
 dynamic_runtime='NOT_RUN'
 performance='NOT_RUN'
}
$report|ConvertTo-Json -Depth 5|Set-Content (Join-Path $outDir 'render-execution-counter-contract.json') -Encoding UTF8
if($missing.Count -gt 0){throw ('C10.79 contract missing: '+($missing -join ', '))}
Write-Host 'C10.79 render execution counter static contract PASS. Dynamic runtime/performance remain NOT_RUN.' -ForegroundColor Green
