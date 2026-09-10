param(
    [Parameter(Position=0)][string]$ExportFile,
    [Parameter(Position=1)][string]$Workspace
)

$ErrorActionPreference = 'Stop'

function Fail([string]$Message, [int]$Code = 1) {
    [Console]::Error.WriteLine("ASTERMAX_CODE_ASTER_RUNNER: $Message")
    exit $Code
}

function ShellQuote([string]$Value) {
    if ($null -eq $Value) { return "''" }
    $sq = [string][char]39
    $dq = [string][char]34
    $embeddedQuote = $sq + $dq + $sq + $dq + $sq
    return $sq + $Value.Replace($sq, $embeddedQuote) + $sq
}

function Get-WslExe {
    $cmd = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { return $null }
    return $cmd.Source
}

function Get-CodeAsterBackend([string]$WslExe) {
    $configured = $env:ASTERMAX_WSL_CODE_ASTER_COMMAND
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        $q = ShellQuote $configured
        $script = "if command -v $q >/dev/null 2>&1 || [ -x $q ]; then printf '%s' $q; exit 0; fi; exit 127"
        $out = & $WslExe sh -lc $script 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return (($out | Select-Object -Last 1).ToString()).Trim() }
        return $null
    }

    $script = "if command -v as_run >/dev/null 2>&1; then command -v as_run; exit 0; fi; exit 127"
    $out = & $WslExe sh -lc $script 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) { return (($out | Select-Object -Last 1).ToString()).Trim() }
    return $null
}

function Get-WslPath([string]$WslExe, [string]$WindowsPath) {
    $out = & $WslExe wslpath -a -u $WindowsPath 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    return (($out | Select-Object -Last 1).ToString()).Trim()
}

$wsl = Get-WslExe
if ($ExportFile -eq 'probe') {
    $backend = $null
    if ($wsl) { $backend = Get-CodeAsterBackend $wsl }
    $ready = (-not [string]::IsNullOrWhiteSpace($wsl)) -and (-not [string]::IsNullOrWhiteSpace($backend))
    [ordered]@{
        schema = 'astermax-codeaster-runner-probe/v1'
        ready = $ready
        transport = $(if ($wsl) { 'WSL2' } else { 'missing' })
        backend = $(if ($backend) { $backend } else { 'missing' })
        configured_backend = $env:ASTERMAX_WSL_CODE_ASTER_COMMAND
        synthetic_results_allowed = $false
    } | ConvertTo-Json -Compress | Write-Output
    if ($ready) { exit 0 } else { exit 21 }
}

if ([string]::IsNullOrWhiteSpace($ExportFile)) { Fail 'Missing .export file argument.' 2 }
if ([string]::IsNullOrWhiteSpace($Workspace)) { Fail 'Missing solve workspace argument.' 2 }
if (-not (Test-Path -LiteralPath $ExportFile -PathType Leaf)) { Fail "Export file not found: $ExportFile" 3 }
if (-not (Test-Path -LiteralPath $Workspace -PathType Container)) { Fail "Workspace not found: $Workspace" 3 }
if (-not $wsl) { Fail 'wsl.exe is not available. Install/enable WSL2 and a Linux Code_Aster runtime.' 20 }

$backend = Get-CodeAsterBackend $wsl
if ([string]::IsNullOrWhiteSpace($backend)) {
    Fail 'No Code_Aster as_run executable is available in the default WSL distribution. Install Code_Aster or set ASTERMAX_WSL_CODE_ASTER_COMMAND to its as_run executable/path.' 21
}

$resolvedWorkspace = (Resolve-Path -LiteralPath $Workspace).Path
$resolvedExport = (Resolve-Path -LiteralPath $ExportFile).Path
$wslWorkspace = Get-WslPath $wsl $resolvedWorkspace
if ([string]::IsNullOrWhiteSpace($wslWorkspace)) { Fail 'Could not translate the solve workspace to a WSL path.' 22 }

# AsterMax C10.00 intentionally emits a transport-neutral /analysis/ root.
# Materialize a disposable export profile whose paths point to this exact transaction workspace.
$portableExport = Join-Path $resolvedWorkspace 'astermax-wsl.export'
$text = Get-Content -LiteralPath $resolvedExport -Raw
$text = $text.Replace('/analysis/', ($wslWorkspace.TrimEnd('/') + '/'))
Set-Content -LiteralPath $portableExport -Value $text -Encoding UTF8

$wslExport = Get-WslPath $wsl $portableExport
if ([string]::IsNullOrWhiteSpace($wslExport)) { Fail 'Could not translate the adapted export profile to a WSL path.' 22 }

$workQ = ShellQuote $wslWorkspace
$backendQ = ShellQuote $backend
$exportQ = ShellQuote $wslExport
$command = "cd $workQ && $backendQ --run $exportQ"

Write-Output "ASTERMAX_CODE_ASTER_TRANSPORT=WSL2"
Write-Output "ASTERMAX_CODE_ASTER_BACKEND=$backend"
Write-Output "ASTERMAX_CODE_ASTER_EXPORT=$wslExport"

& $wsl sh -lc $command
$solverExit = $LASTEXITCODE
if ($solverExit -ne 0) { Fail "Code_Aster as_run returned exit code $solverExit." $solverExit }

$mess = Get-ChildItem -LiteralPath $resolvedWorkspace -Filter '*.mess' -File -ErrorAction SilentlyContinue | Select-Object -First 1
$rmed = Get-ChildItem -LiteralPath $resolvedWorkspace -Filter '*.rmed' -File -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $mess -or $mess.Length -le 0) { Fail 'Solver returned success but no non-empty .mess file was produced.' 30 }
if ($null -eq $rmed -or $rmed.Length -le 0) { Fail 'Solver returned success but no non-empty .rmed file was produced.' 31 }

Write-Output 'ASTERMAX_CODE_ASTER_RUNNER=SUCCESS'
exit 0
