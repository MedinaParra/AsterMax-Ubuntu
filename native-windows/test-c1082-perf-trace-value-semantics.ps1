$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$parser = Join-Path $root 'parse-c1082-perf-trace.ps1'
$trace = Join-Path $env:TEMP 'astermax-c1082-value-semantics.log'

@(
  'ASTERMAX_PERF_RENDER request=true',
  'ASTERMAX_PERF_RENDER request=false',
  'ASTERMAX_PERF_RENDER queued=true',
  'ASTERMAX_PERF_RENDER queued=false',
  'ASTERMAX_PERF_RENDER executed=true',
  'ASTERMAX_PERF_RENDER executed=false'
) | Set-Content -LiteralPath $trace -Encoding UTF8

$r = (& $parser -TracePath $trace | ConvertFrom-Json)

# C10.82 parser is intentionally token-based today. This regression makes the
# limitation explicit: false-valued telemetry is still counted as an event.
# Do not interpret these counts as work actually performed until the producer
# emits unambiguous event-only tokens or the parser gains value semantics.
if ($r.render_request_events -ne 2) { throw "Expected 2 request tokens, got $($r.render_request_events)" }
if ($r.render_queued_events -ne 2) { throw "Expected 2 queued tokens, got $($r.render_queued_events)" }
if ($r.render_executed_events -ne 2) { throw "Expected 2 executed tokens, got $($r.render_executed_events)" }

Remove-Item -LiteralPath $trace -Force -ErrorAction SilentlyContinue
Write-Host 'PASS C10.82 boolean token counting limitation is explicit'
