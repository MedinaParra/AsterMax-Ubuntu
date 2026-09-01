$ErrorActionPreference = 'Stop'

$AppRoot = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $env:LOCALAPPDATA 'AsterMax'
$StateFile = Join-Path $StateDir 'installation_state.json'
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

$report = [ordered]@{
    schema = 'AsterMaxWindowsDependencyBootstrapV1'
    timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
    app_root = $AppRoot
    architecture = $env:PROCESSOR_ARCHITECTURE
    vc_runtime = 'unknown'
    packaged_runtime = 'present'
}

function Test-VCRedistX64 {
    $roots = @(
        'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64'
    )
    foreach ($root in $roots) {
        try {
            $value = Get-ItemProperty -Path $root -ErrorAction Stop
            if ($value.Installed -eq 1) { return $true }
        } catch {}
    }
    return $false
}

if (Test-VCRedistX64) {
    $report.vc_runtime = 'already-installed'
} else {
    $download = Join-Path $env:TEMP 'AsterMax-vc_redist.x64.exe'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $download
    $signature = Get-AuthenticodeSignature $download
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft') {
        throw 'Downloaded Microsoft Visual C++ Redistributable failed Authenticode verification.'
    }
    $process = Start-Process -FilePath $download -ArgumentList '/install','/quiet','/norestart' -Wait -PassThru
    if ($process.ExitCode -notin @(0, 1638, 3010)) {
        throw "Visual C++ Redistributable installer failed with exit code $($process.ExitCode)."
    }
    $report.vc_runtime = "installed:$($process.ExitCode)"
}

# Python, NumPy, SciPy and the Gmsh Python runtime are frozen into the onedir build.
# No global Python installation and no modification of system PATH are required.
$exe = Join-Path $AppRoot 'AsterMax.exe'
if (-not (Test-Path $exe)) {
    throw "AsterMax.exe not found at $exe"
}
$report.astermax_exe = $exe
$report | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $StateFile
Write-Host "AsterMax dependency bootstrap complete. State: $StateFile"
