$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$parser = Join-Path $here 'parse-c1082-perf-trace.ps1'
if (!(Test-Path -LiteralPath $parser)) { throw 'C10.82 parser missing.' }

# Regression: unrelated prose must not become render telemetry merely because
# request/queued/executed words occur elsewhere on the same line.
$trace = Join-Path $env:TEMP ('astermax-c1082-line-isolation-' + [guid]::NewGuid().ToString('N') + '.log')
@(
 'INFO request queued executed',
 'ASTERMAX_PERF_CAMERA request queued executed',
 'ASTERMAX_PERF_EDGE materialized=1 request queued executed',
 'ASTERMAX_PERF_RENDER request',
 'ASTERMAX_PERF_RENDER queued',
 'ASTERMAX_PERF_RENDER executed'
) | Set-Content -LiteralPath $trace -Encoding UTF8
try {
 $r = (& $parser -TracePath $trace | ConvertFrom-Json)
 if ($r.render_request_events -ne 1) { throw "request isolation failed: $($r.render_request_events)" }
 if ($r.render_queued_events -ne 1) { throw "queued isolation failed: $($r.render_queued_events)" }
 if ($r.render_executed_events -ne 1) { throw "executed isolation failed: $($r.render_executed_events)" }
 if ($r.camera_events -ne 1) { throw "camera accounting failed: $($r.camera_events)" }
 if ($r.edge_materialized_events -ne 1) { throw "edge accounting failed: $($r.edge_materialized_events)" }
 Write-Host 'PASS C10.82 trace line isolation contract.' -ForegroundColor Green
}
finally { Remove-Item -LiteralPath $trace -Force -ErrorAction SilentlyContinue }
