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

# C10.82 v2 uses value semantics: explicit false fields are metadata, not work.
if ($r.schema -ne 'astermax-c1082-perf-trace-v2') { throw "Expected v2 schema, got $($r.schema)" }
if ($r.render_request_events -ne 1) { throw "Expected 1 true request event, got $($r.render_request_events)" }
if ($r.render_queued_events -ne 1) { throw "Expected 1 true queued event, got $($r.render_queued_events)" }
if ($r.render_executed_events -ne 1) { throw "Expected 1 true executed event, got $($r.render_executed_events)" }

Remove-Item -LiteralPath $trace -Force -ErrorAction SilentlyContinue
Write-Host 'PASS C10.82 render boolean value semantics'
