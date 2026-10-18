$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
$parser=Join-Path $root 'parse-c1082-perf-trace.ps1'
if(!(Test-Path $parser)){throw 'C10.82 parser missing.'}
$tmp=Join-Path ([IO.Path]::GetTempPath()) ('astermax-c1082-'+[guid]::NewGuid().ToString('N')+'.log')
try {
@'
ASTERMAX_PERF_RENDER request=true
ASTERMAX_PERF_RENDER request=true
ASTERMAX_PERF_RENDER queued=true
ASTERMAX_PERF_RENDER executed=true
ASTERMAX_PERF_EDGE materialized=1
ASTERMAX_PERF_EDGE highlight-materialized=1
ASTERMAX_PERF_CAMERA reset=1
ASTERMAX_PERF_ACTOR add=1
ASTERMAX_PERF_TREE update=1
ASTERMAX_PERF_RENDER request=false
ASTERMAX_PERF_RENDER queued=false
ASTERMAX_PERF_RENDER executed=false
'@ | Set-Content -LiteralPath $tmp -Encoding UTF8
$j=& $parser -TracePath $tmp | ConvertFrom-Json
if($j.render_request_events -ne 2){throw 'render request count mismatch'}
if($j.render_queued_events -ne 1){throw 'render queued count mismatch'}
if($j.render_executed_events -ne 1){throw 'render executed count mismatch'}
if($j.edge_materialized_events -ne 1){throw 'edge materialization count mismatch'}
if($j.edge_highlight_materialized_events -ne 1){throw 'highlight edge count mismatch'}
if($j.camera_events -ne 1 -or $j.actor_events -ne 1 -or $j.tree_events -ne 1){throw 'camera/actor/tree count mismatch'}
Write-Host 'PASS C10.82 deterministic performance trace parser contract.' -ForegroundColor Green
} finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
