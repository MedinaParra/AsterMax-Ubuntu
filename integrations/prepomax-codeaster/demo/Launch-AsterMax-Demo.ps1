param(
    [string]$EvidencePath = "",
    [switch]$NoWait
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$contractPath = Join-Path $root 'demo-contract.json'
$logs = Join-Path $root 'Logs'
New-Item -ItemType Directory -Force $logs | Out-Null
$inv = [Globalization.CultureInfo]::InvariantCulture

function Fail([string]$message) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $failure = @{ ok=$false; timestamp=(Get-Date).ToUniversalTime().ToString('o'); error=$message }
    $failure | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $logs "launch-failure-$stamp.json") -Encoding UTF8
    throw $message
}

if (-not [Environment]::Is64BitOperatingSystem) { Fail 'AsterMax PMV requires 64-bit Windows.' }
if ($PSVersionTable.PSVersion.Major -lt 5) { Fail 'AsterMax PMV requires Windows PowerShell 5.1 or newer.' }
if (-not (Test-Path $contractPath)) { Fail 'demo-contract.json is missing.' }

$contract = Get-Content $contractPath -Raw | ConvertFrom-Json
$exe = Join-Path $root 'PrePoMax.exe'
$pmx = Join-Path $root $contract.dataset.pmx.path
$rmed = Join-Path $root $contract.dataset.rmed.path
$resu = Join-Path $root $contract.dataset.resu.path
foreach ($p in @($exe,$pmx,$rmed,$resu)) { if (-not (Test-Path $p)) { Fail "Required demo file missing: $p" } }

$checks = @(
    @{ path=$pmx; expected=[string]$contract.dataset.pmx.sha256 },
    @{ path=$rmed; expected=[string]$contract.dataset.rmed.sha256 },
    @{ path=$resu; expected=[string]$contract.dataset.resu.sha256 }
)
foreach ($c in $checks) {
    $actual = (Get-FileHash $c.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $c.expected.ToLowerInvariant()) { Fail "Demo provenance hash mismatch: $($c.path)" }
}

if ([string]::IsNullOrWhiteSpace($EvidencePath)) {
    $EvidencePath = Join-Path $logs ("READY-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
} elseif (-not [IO.Path]::IsPathRooted($EvidencePath)) {
    $EvidencePath = Join-Path $root $EvidencePath
}

$stdout = Join-Path $logs 'AsterMax-demo.stdout.log'
$stderr = Join-Path $logs 'AsterMax-demo.stderr.log'
$env:ASTERMAX_RESULTS_FULL_MODEL_PMX = $pmx
$env:ASTERMAX_RESULTS_EXPECTED_NODES = ([int]$contract.expected.node_count).ToString($inv)
$env:ASTERMAX_RESULTS_EXPECTED_ELEMENTS = ([int]$contract.expected.element_count).ToString($inv)
$env:ASTERMAX_RESULTS_EXPECTED_MISES_MAX = ([double]$contract.expected.max_von_mises_mpa).ToString('R',$inv)
$env:ASTERMAX_RESULTS_EXPECTED_DISP_MAX = ([double]$contract.expected.max_displacement_mm).ToString('R',$inv)
$env:ASTERMAX_RESULTS_EXPECTED_MISES_NODE = ([int]$contract.expected.max_von_mises_node).ToString($inv)
$env:ASTERMAX_RESULTS_EXPECTED_DISP_NODE = ([int]$contract.expected.max_displacement_node).ToString($inv)

# Start-Process joins ArgumentList into a Win32 command line. Build one explicit argument line using
# ASCII quote (34), avoiding locale- and escape-rule ambiguity for package paths containing spaces.
$q = [char]34
$argLine = '--astermax-results-demo ' + $q + $rmed + $q + ' ' + $q + $resu + $q + ' ' + $q + $EvidencePath + $q
$p = Start-Process $exe -ArgumentList $argLine -WorkingDirectory $root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$launch = @{
    schema='astermax.c8.78.launch-summary.v1'; ok=$true; process_id=$p.Id; evidence_path=$EvidencePath;
    dataset_verified=$true; package_root=$root; started_utc=(Get-Date).ToUniversalTime().ToString('o'); waited=(-not $NoWait);
    quoted_path_arguments=$true; invariant_numeric_contract=$true; argument_line_model='explicit-win32-quoted'
}
$launch | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $logs 'last-launch.json') -Encoding UTF8

if ($NoWait) { return }
if (-not $p.WaitForExit(120000)) { try { Stop-Process -Id $p.Id -Force } catch {}; Fail 'AsterMax demo did not exit within the deterministic qualification window.' }
if ($p.ExitCode -ne 0) { Fail "AsterMax demo exited with code $($p.ExitCode). See Logs." }
if (-not (Test-Path $EvidencePath)) { Fail 'AsterMax demo exited without emitting READY evidence.' }
$ready = Get-Content $EvidencePath -Raw | ConvertFrom-Json
if (-not $ready.scene_ready -or -not $ready.result_admitted -or -not $ready.rendered_viewport_deformation_verified) { Fail 'AsterMax demo READY evidence did not satisfy the admitted Results contract.' }
if ([string]$ready.deformation_state -ne 'user-defined-x10-contour') { Fail 'AsterMax demo did not preserve the qualified x10 deformation state.' }

$launch.exit_code = $p.ExitCode
$launch.completed_utc = (Get-Date).ToUniversalTime().ToString('o')
$launch.result_admitted = $true
$launch.rendered_x10 = $true
$launch | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $logs 'last-launch.json') -Encoding UTF8
Write-Host 'AsterMax PMV demo completed with solver-verified Results and deterministic exit code 0.'
