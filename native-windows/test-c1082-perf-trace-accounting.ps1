$ErrorActionPreference='Stop'
$here=Split-Path -Parent $MyInvocation.MyCommand.Path
$parser=Join-Path $here 'parse-c1082-perf-trace.ps1'
if(!(Test-Path -LiteralPath $parser)){throw 'C10.82 parser missing.'}
$tmp=Join-Path ([IO.Path]::GetTempPath()) ('astermax-c1082-accounting-'+[guid]::NewGuid().ToString('N')+'.log')
try {
@'
ASTERMAX_PERF_RENDER request
ASTERMAX_PERF_RENDER request
ASTERMAX_PERF_RENDER request
ASTERMAX_PERF_RENDER queued
ASTERMAX_PERF_RENDER executed
ASTERMAX_PERF_EDGE materialized=1
ASTERMAX_PERF_EDGE highlight-materialized=1
ASTERMAX_PERF_CAMERA fit
ASTERMAX_PERF_ACTOR add
ASTERMAX_PERF_TREE refresh
'@ | Set-Content -LiteralPath $tmp -Encoding UTF8
$r=(& $parser -TracePath $tmp | ConvertFrom-Json)
if($r.schema -ne 'astermax-c1082-perf-trace-v2'){throw 'schema mismatch'}
if($r.render_request_events -ne 3){throw 'render request accounting mismatch'}
if($r.render_queued_events -ne 1){throw 'render queued accounting mismatch'}
if($r.render_executed_events -ne 1){throw 'render executed accounting mismatch'}
if($r.edge_materialized_events -ne 1){throw 'edge accounting mismatch'}
if($r.edge_highlight_materialized_events -ne 1){throw 'highlight edge accounting mismatch'}
if($r.camera_events -ne 1 -or $r.actor_events -ne 1 -or $r.tree_events -ne 1){throw 'scene accounting mismatch'}
Write-Host 'PASS C10.82 trace accounting contract.' -ForegroundColor Green
} finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
