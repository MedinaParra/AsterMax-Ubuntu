$ErrorActionPreference='Stop'
$here=Split-Path -Parent $MyInvocation.MyCommand.Path
$parser=Join-Path $here 'parse-c1082-perf-trace.ps1'
if(!(Test-Path -LiteralPath $parser)){throw 'C10.82 parser missing.'}
$tmp=Join-Path ([IO.Path]::GetTempPath()) ('astermax-c1082-overlap-'+[guid]::NewGuid().ToString('N')+'.log')
try {
@'
ASTERMAX_PERF_EDGE materialized=1
ASTERMAX_PERF_EDGE highlight-materialized=1
'@ | Set-Content -LiteralPath $tmp -Encoding UTF8
$r=(& $parser -TracePath $tmp | ConvertFrom-Json)
if($r.edge_materialized_events -ne 1){throw "C10.82 overlap regression: normal edge materialization expected 1, got $($r.edge_materialized_events)."}
if($r.edge_highlight_materialized_events -ne 1){throw "C10.82 overlap regression: highlight edge materialization expected 1, got $($r.edge_highlight_materialized_events)."}
Write-Host 'PASS C10.82 edge trace categories are non-overlapping.' -ForegroundColor Green
} finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
