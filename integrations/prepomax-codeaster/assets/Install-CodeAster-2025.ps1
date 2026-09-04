param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$downloadUrl = 'https://simulease.com/wp-content/uploads/2026/03/code-aster_v2025_std.msi'
$expectedMd5 = '95a2171a6eb967874f7d0c98e881c66c'
$cacheDir = Join-Path $env:LOCALAPPDATA 'AsterMax Mechanical\Downloads'
$msi = Join-Path $cacheDir 'code-aster_v2025_std.msi'
$launcher = Join-Path $env:LOCALAPPDATA 'code_aster\bin\run_aster.bat'

Write-Host ''
Write-Host 'AsterMax Mechanical - Code_Aster 2025 setup'
Write-Host '------------------------------------------------'
Write-Host 'This installs the native Windows Code_Aster solver distributed by SimulEase/Code_Aster for Windows.'
Write-Host "Expected launcher after installation: $launcher"
Write-Host ''

if (Test-Path $launcher) {
    Write-Host "Code_Aster is already installed: $launcher"
    exit 0
}

New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null

$needsDownload = $true
if (Test-Path $msi) {
    $actual = (Get-FileHash -Path $msi -Algorithm MD5).Hash.ToLowerInvariant()
    if ($actual -eq $expectedMd5) {
        Write-Host 'Using previously downloaded installer with matching MD5.'
        $needsDownload = $false
    }
    else {
        Write-Warning "Cached installer hash mismatch ($actual). Downloading a clean copy."
        Remove-Item $msi -Force
    }
}

if ($needsDownload) {
    Write-Host 'Downloading Code_Aster 2025 Windows MSI (~398 MB)...'
    Invoke-WebRequest -Uri $downloadUrl -OutFile $msi -UseBasicParsing
}

$actualMd5 = (Get-FileHash -Path $msi -Algorithm MD5).Hash.ToLowerInvariant()
if ($actualMd5 -ne $expectedMd5) {
    throw "Code_Aster installer MD5 mismatch. Expected $expectedMd5, got $actualMd5. Installation aborted."
}
Write-Host "Installer MD5 verified: $actualMd5"

$args = @('/i', ('"' + $msi + '"'))
if ($Quiet) { $args += @('/qn', '/norestart') }

Write-Host 'Launching Code_Aster installer...'
$process = Start-Process -FilePath 'msiexec.exe' -ArgumentList $args -Wait -PassThru
if ($process.ExitCode -notin @(0, 3010)) {
    throw "Code_Aster installer returned exit code $($process.ExitCode)."
}

if (Test-Path $launcher) {
    Write-Host ''
    Write-Host "Code_Aster runtime detected: $launcher"
    Write-Host 'Return to AsterMax Mechanical and press Solve again.'
    exit 0
}

Write-Warning 'Installation finished, but AsterMax did not find the expected run_aster.bat path.'
Write-Warning 'Open AsterMax Mechanical > Tools > Settings > Code_Aster and point the launcher to your run_aster.bat.'
exit 2
