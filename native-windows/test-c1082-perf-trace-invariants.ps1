$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
$parser=Join-Path $root 'parse-c1082-perf-trace.ps1'
if(!(Test-Path $parser)){throw 'C10.82 parser missing.'}

function Invoke-Case([string]$Name,[string]$Trace,[scriptblock]$Assert){
    $tmp=Join-Path ([IO.Path]::GetTempPath()) ('astermax-c1082-'+$Name+'-'+[guid]::NewGuid().ToString('N')+'.log')
    try {
        Set-Content -LiteralPath $tmp -Value $Trace -Encoding UTF8
        $j=& $parser -TracePath $tmp | ConvertFrom-Json
        & $Assert $j
    } finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
}

Invoke-Case 'coalesced' @'
ASTERMAX_PERF_RENDER request=1
ASTERMAX_PERF_RENDER request=2
ASTERMAX_PERF_RENDER request=3
ASTERMAX_PERF_RENDER queued=1
ASTERMAX_PERF_RENDER executed=1
'@ {
    param($j)
    if($j.render_request_events -ne 3 -or $j.render_queued_events -ne 1 -or $j.render_executed_events -ne 1){throw 'coalesced render counts mismatch'}
    if($j.render_queued_events -gt $j.render_request_events){throw 'queued renders exceed requests'}
    if($j.render_executed_events -gt $j.render_queued_events){throw 'executed renders exceed queued renders'}
}

Invoke-Case 'deferred-edges' @'
ASTERMAX_PERF_EDGE materialized=1
ASTERMAX_PERF_EDGE materialized=2
ASTERMAX_PERF_EDGE highlight-materialized=1
'@ {
    param($j)
    if($j.edge_materialized_events -ne 2){throw 'effective edge materialization count mismatch'}
    if($j.edge_highlight_materialized_events -ne 1){throw 'highlight edge materialization count mismatch'}
}

Invoke-Case 'empty' 'unrelated log line' {
    param($j)
    if($j.render_request_events -ne 0 -or $j.render_queued_events -ne 0 -or $j.render_executed_events -ne 0){throw 'missing render tokens must remain zero'}
    if($j.edge_materialized_events -ne 0 -or $j.edge_highlight_materialized_events -ne 0){throw 'missing edge tokens must remain zero'}
    if($j.camera_events -ne 0 -or $j.actor_events -ne 0 -or $j.tree_events -ne 0){throw 'missing subsystem tokens must remain zero'}
}

Write-Host 'PASS C10.82 performance trace invariant contract.' -ForegroundColor Green
