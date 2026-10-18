$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
$parser=Join-Path $root 'parse-c1082-perf-trace.ps1'
$tmp=Join-Path ([IO.Path]::GetTempPath()) ('astermax-c1082-render-overlap-'+[guid]::NewGuid().ToString('N')+'.log')
try {
  @(
    'ASTERMAX_PERF_RENDER request queued=false',
    'ASTERMAX_PERF_RENDER queued request=false',
    'ASTERMAX_PERF_RENDER executed request=false',
    'ASTERMAX_PERF_RENDER invalidate request=false'
  ) | Set-Content -LiteralPath $tmp -Encoding UTF8
  $r = (& $parser -TracePath $tmp | ConvertFrom-Json)
  if($r.render_request_events -ne 1){ throw "C10.82 request value accounting changed: $($r.render_request_events), expected=1." }
  if($r.render_queued_events -ne 1){ throw "C10.82 queued value accounting changed: $($r.render_queued_events), expected=1." }
  if($r.render_executed_events -ne 2){ throw "C10.82 executed/invalidate accounting changed: $($r.render_executed_events), expected=2." }
  Write-Host 'PASS C10.82 render value/overlap accounting contract.' -ForegroundColor Green
}
finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
