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

# Windows-native adapter for the SimulEase Code_Aster distributions.
# The vendor's run_aster.bat activates its own Python and profile.bat.
function Invoke-NativeProcess([string]$Program, [string]$Arguments, [string]$Directory, [int]$Timeout=12000) {
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $p.StartInfo.FileName=$Program; $p.StartInfo.Arguments=$Arguments
    $p.StartInfo.WorkingDirectory=$Directory; $p.StartInfo.UseShellExecute=$false
    $p.StartInfo.CreateNoWindow=$true
    $p.StartInfo.RedirectStandardOutput=$true; $p.StartInfo.RedirectStandardError=$true
    $p.StartInfo.StandardOutputEncoding=New-Object System.Text.UTF8Encoding($false)
    $p.StartInfo.StandardErrorEncoding=New-Object System.Text.UTF8Encoding($false)
    try {
        if (-not $p.Start()) { throw 'Could not start native runner.' }
        $stdout=$p.StandardOutput.ReadToEndAsync(); $stderr=$p.StandardError.ReadToEndAsync()
        if (-not $p.WaitForExit($Timeout)) {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $p.Id /T /F 2>&1 | Out-Null
            throw 'Native Code_Aster command timed out.'
        }
        return @{ExitCode=$p.ExitCode; Stdout=$stdout.Result; Stderr=$stderr.Result}
    } finally { $p.Dispose() }
}
function Native-Quote([string]$Value) {
    if ($Value -match '["%!\r\n]') { throw 'Unsupported quote, percent or exclamation in native command path.' }
    return '"'+$Value+'"'
}
function Find-WindowsBackend {
    $explicit=$env:ASTERMAX_WINDOWS_CODE_ASTER_COMMAND
    if ($explicit) {
        if (-not (Test-Path -LiteralPath $explicit -PathType Leaf)) { throw "Configured Windows launcher not found: $explicit" }
        return (Get-Item -LiteralPath $explicit).FullName
    }
    $roots=@()
    if ($env:ASTERMAX_CODE_ASTER_HOME) { $roots+= $env:ASTERMAX_CODE_ASTER_HOME }
    $config=Join-Path $env:LOCALAPPDATA 'AsterMax\code-aster-windows.json'
    if (Test-Path -LiteralPath $config) {
        $root=(Get-Content -LiteralPath $config -Raw | ConvertFrom-Json).installation
        if ($root) { $roots+=$root }
    }
    $roots+=@((Join-Path $env:LOCALAPPDATA 'code_aster'),(Join-Path $env:ProgramFiles 'code_aster'),'C:\code_aster')
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        # Bounded search: root, install/bin, version/bin, release/version/bin.
        $found=@()
        foreach ($pattern in @('bin\run_aster.bat','*\bin\run_aster.bat','*\*\bin\run_aster.bat','install\bin\as_run.bat','bin\as_run.bat')) {
            $found+=@(Get-ChildItem -Path (Join-Path $root $pattern) -File -ErrorAction SilentlyContinue)
        }
        if ($found.Count) { return ($found | Sort-Object FullName -Descending | Select-Object -First 1).FullName }
    }
    foreach ($name in @('run_aster.bat','as_run.bat')) {
        $command=Get-Command $name -CommandType Application -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}
function Invoke-WindowsBackend([string]$Backend,[string]$Arguments,[string]$Directory,[int]$Timeout=12000) {
    $ext=[IO.Path]::GetExtension($Backend).ToLowerInvariant()
    if ($ext -eq '.bat' -or $ext -eq '.cmd') {
        return Invoke-NativeProcess $env:ComSpec ('/d /v:off /s /c "'+(Native-Quote $Backend)+' '+$Arguments+'"') $Directory $Timeout
    }
    if ($ext -eq '.exe') { return Invoke-NativeProcess $Backend $Arguments $Directory $Timeout }
    throw 'Configure a Code_Aster run_aster.bat, as_run.bat or native executable.'
}

$native=$null; $nativeError=$null
try { $native=Find-WindowsBackend } catch { $nativeError=$_.Exception.Message }
if ($native -or $nativeError) {
    if ($ExportFile -eq 'probe') {
        $ready=$false; $version=''
        if ($native) {
            try {
                $p=Invoke-WindowsBackend $native '--version' ([IO.Path]::GetDirectoryName($native))
                $version=($p.Stdout -replace '\x00','').Trim()
                $ready=($p.ExitCode -eq 0 -and $version -match '\d+\.\d+')
                if (-not $ready) { $nativeError=($p.Stderr -replace '\x00','').Trim(); if (-not $nativeError) {$nativeError=$version} }
            } catch { $nativeError=$_.Exception.Message }
        }
        [ordered]@{schema='astermax-codeaster-runner-probe/v2';ready=$ready;transport='WINDOWS_NATIVE';backend=$native;version=$version;message=$nativeError;synthetic_results_allowed=$false} | ConvertTo-Json -Compress
        if($ready){exit 0}else{exit 21}
    }
    if ($nativeError) { Fail $nativeError 21 }
    if (-not (Test-Path -LiteralPath $ExportFile -PathType Leaf)) { Fail 'Missing export file.' 3 }
    if (-not (Test-Path -LiteralPath $Workspace -PathType Container)) { Fail 'Missing solve workspace.' 3 }
    $work=(Resolve-Path -LiteralPath $Workspace).Path
    $profile=Join-Path $work 'astermax-windows.export'
    # Relative file records are resolved by run_aster from the transaction directory.
    # This avoids introducing spaces into the .export record tokenizer.
    $content=(Get-Content -LiteralPath $ExportFile -Raw).Replace('/analysis/','./')
    [IO.File]::WriteAllText($profile,$content,(New-Object System.Text.UTF8Encoding($false)))
    $args=Native-Quote $profile
    if ([IO.Path]::GetFileName($native) -like 'as_run*') {$args='--run '+$args}
    Write-Output 'ASTERMAX_CODE_ASTER_TRANSPORT=WINDOWS_NATIVE'
    Write-Output "ASTERMAX_CODE_ASTER_BACKEND=$native"
    $started=[DateTime]::UtcNow
    $result=Invoke-WindowsBackend $native $args $work 3600000
    Write-Output $result.Stdout
    if($result.Stderr){[Console]::Error.WriteLine($result.Stderr)}
    if($result.ExitCode -ne 0){Fail "Native Code_Aster returned exit code $($result.ExitCode)." $result.ExitCode}
    foreach($extension in @('mess','rmed')) {
        $output=Get-ChildItem -LiteralPath $work -Filter "*.$extension" -File | Where-Object {$_.Length -gt 0 -and $_.LastWriteTimeUtc -ge $started.AddSeconds(-1)} | Select-Object -First 1
        if (-not $output) {Fail "Native solver did not produce a fresh non-empty .$extension file." 30}
    }
    Write-Output 'ASTERMAX_CODE_ASTER_RUNNER=SUCCESS'
    exit 0
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

