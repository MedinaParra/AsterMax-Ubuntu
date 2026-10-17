param(
    [Parameter(Mandatory=$true)][string]$TracePath,
    [string]$OutputPath = ""
)

$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $TracePath)) { throw "Trace not found: $TracePath" }

$lines = Get-Content -LiteralPath $TracePath

function Count-Matches([string]$Pattern) {
    return @($lines | Select-String -Pattern $Pattern).Count
}

# These are deliberately trace-token based. Missing tokens are reported as zero,
# never converted into timing/FPS claims.
$result = [ordered]@{
    schema = 'astermax-c1082-perf-trace-v1'
    trace = (Resolve-Path -LiteralPath $TracePath).Path
    lines = $lines.Count
    render_request_events = Count-Matches 'ASTERMAX_PERF_RENDER.*request'
    render_queued_events = Count-Matches 'ASTERMAX_PERF_RENDER.*queued'
    render_executed_events = Count-Matches 'ASTERMAX_PERF_RENDER.*(executed|invalidate)'
    edge_materialized_events = Count-Matches 'ASTERMAX_PERF_EDGE materialized='
    edge_highlight_materialized_events = Count-Matches 'ASTERMAX_PERF_EDGE highlight-materialized='
    camera_events = Count-Matches 'ASTERMAX_PERF_CAMERA'
    actor_events = Count-Matches 'ASTERMAX_PERF_ACTOR'
    tree_events = Count-Matches 'ASTERMAX_PERF_TREE'
}

$json = $result | ConvertTo-Json -Depth 4
if ($OutputPath) {
    $parent = Split-Path -Parent $OutputPath
    if ($parent -and !(Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Set-Content -LiteralPath $OutputPath -Value $json -Encoding UTF8
}
$json
