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

function Count-RenderEvent([string]$Token) {
    # Producers may emit either event-only tokens (`request`) or boolean fields
    # (`request=true/false`). Count bare/true occurrences, never explicit false.
    $positive = 'ASTERMAX_PERF_RENDER.*\b' + [regex]::Escape($Token) + '(?:=true)?(?:\s|$)'
    $negative = 'ASTERMAX_PERF_RENDER.*\b' + [regex]::Escape($Token) + '=false(?:\s|$)'
    return @($lines | Where-Object { ($_ -match $positive) -and ($_ -notmatch $negative) }).Count
}

# Missing tokens are reported as zero and are never converted into timing/FPS
# claims. Render boolean fields use value semantics so `queued=false` cannot be
# mistaken for work actually queued/executed.
$result = [ordered]@{
    schema = 'astermax-c1082-perf-trace-v2'
    trace = (Resolve-Path -LiteralPath $TracePath).Path
    lines = $lines.Count
    render_request_events = Count-RenderEvent 'request'
    render_queued_events = Count-RenderEvent 'queued'
    render_executed_events = (Count-RenderEvent 'executed') + (Count-RenderEvent 'invalidate')
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
