param(
    [Parameter(Position=0)][string]$ExportFile,
    [Parameter(Position=1)][string]$Workspace
)

$ErrorActionPreference = 'Stop'

function Fail([string]$Message, [int]$Code = 1) {
    [Console]::Error.WriteLine("ASTERMAX_CODE_ASTER_RUNNER: $Message")
    exit $Code
}

function Native-Quote([string]$Value) {
    if ($null -eq $Value) { return '""' }
    if ($Value -match '["%!\r\n]') { throw 'Unsupported quote, percent or exclamation in native command path.' }
    return '"' + $Value + '"'
}

function Invoke-NativeProcess([string]$Program, [string]$Arguments, [string]$Directory, [int]$TimeoutMs = 120000) {
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $p.StartInfo.FileName = $Program
    $p.StartInfo.Arguments = $Arguments
    $p.StartInfo.WorkingDirectory = $Directory
    $p.StartInfo.UseShellExecute = $false
    $p.StartInfo.CreateNoWindow = $true
    $p.StartInfo.RedirectStandardOutput = $true
    $p.StartInfo.RedirectStandardError = $true
    try {
        if (-not $p.Start()) { throw 'Could not start native Code_Aster process.' }
        $stdoutTask = $p.StandardOutput.ReadToEndAsync()
        $stderrTask = $p.StandardError.ReadToEndAsync()
        if (-not $p.WaitForExit($TimeoutMs)) {
            try { & "$env:SystemRoot\System32\taskkill.exe" /PID $p.Id /T /F 2>&1 | Out-Null } catch { }
            throw "Native Code_Aster command timed out after $TimeoutMs ms."
        }
        return [pscustomobject]@{
            ExitCode = $p.ExitCode
            Stdout = ($stdoutTask.Result -replace "`0", '')
            Stderr = ($stderrTask.Result -replace "`0", '')
        }
    }
    finally {
        $p.Dispose()
    }
}

function Invoke-WindowsBackend([string]$Backend, [string]$ExportPath, [string]$Directory, [int]$TimeoutMs) {
    # Code_Aster for Windows documents the standalone launcher as:
    #   install\bin\as_run.bat study.export
    $args = Native-Quote $ExportPath
    $ext = [IO.Path]::GetExtension($Backend).ToLowerInvariant()
    if ($ext -eq '.bat' -or $ext -eq '.cmd') {
        if ([string]::IsNullOrWhiteSpace($env:ComSpec)) { $env:ComSpec = "$env:SystemRoot\System32\cmd.exe" }
        return Invoke-NativeProcess $env:ComSpec ('/d /v:off /s /c "' + (Native-Quote $Backend) + ' ' + $args + '"') $Directory $TimeoutMs
    }
    if ($ext -eq '.exe') {
        return Invoke-NativeProcess $Backend $args $Directory $TimeoutMs
    }
    throw 'Configure a native Windows Code_Aster run_aster.bat, as_run.bat or executable.'
}

function Add-Root([System.Collections.Generic.List[string]]$Roots, [string]$Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) { return }
    try {
        $full = [IO.Path]::GetFullPath($Candidate)
        if (-not $Roots.Contains($full)) { $Roots.Add($full) }
    } catch { }
}

function Find-WindowsBackend {
    $explicit = $env:ASTERMAX_WINDOWS_CODE_ASTER_COMMAND
    if (-not [string]::IsNullOrWhiteSpace($explicit)) {
        if (-not (Test-Path -LiteralPath $explicit -PathType Leaf)) { throw "Configured Windows launcher not found: $explicit" }
        return (Get-Item -LiteralPath $explicit).FullName
    }

    $roots = New-Object 'System.Collections.Generic.List[string]'
    Add-Root $roots $env:ASTERMAX_CODE_ASTER_HOME

    $config = Join-Path $env:LOCALAPPDATA 'AsterMax\code-aster-windows.json'
    if (Test-Path -LiteralPath $config -PathType Leaf) {
        try {
            $configuredRoot = (Get-Content -LiteralPath $config -Raw | ConvertFrom-Json).installation
            Add-Root $roots $configuredRoot
        } catch { }
    }

    Add-Root $roots (Join-Path $env:LOCALAPPDATA 'code_aster')
    Add-Root $roots (Join-Path $env:LOCALAPPDATA 'Programs\code_aster')
    Add-Root $roots (Join-Path $env:ProgramFiles 'code_aster')
    if (${env:ProgramFiles(x86)}) { Add-Root $roots (Join-Path ${env:ProgramFiles(x86)} 'code_aster') }
    Add-Root $roots 'C:\code_aster'

    $relativeCandidates = @(
        'install\bin\run_aster.bat','install\bin\run_aster.cmd','install\bin\run_aster.exe',
        'install\bin\as_run.bat','install\bin\as_run.cmd','install\bin\as_run.exe',
        'bin\run_aster.bat','bin\run_aster.cmd','bin\run_aster.exe',
        'run_aster.bat','run_aster.cmd','run_aster.exe',
        'bin\as_run.bat','bin\as_run.cmd','bin\as_run.exe',
        'as_run.bat','as_run.cmd','as_run.exe'
    )
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        foreach ($relative in $relativeCandidates) {
            $candidate = Join-Path $root $relative
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return (Get-Item -LiteralPath $candidate).FullName }
        }
        foreach ($name in @('run_aster.bat','run_aster.cmd','run_aster.exe','as_run.bat','as_run.cmd','as_run.exe')) {
            $found = Get-ChildItem -LiteralPath $root -Recurse -File -Filter $name -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) { return $found.FullName }
        }
    }

    foreach ($name in @('run_aster.bat','run_aster.cmd','run_aster.exe','as_run.bat','as_run.cmd','as_run.exe')) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}

function New-SafeStageDirectory([string]$Prefix) {
    $base = $env:PUBLIC
    if ([string]::IsNullOrWhiteSpace($base) -or -not (Test-Path -LiteralPath $base -PathType Container)) {
        $base = [IO.Path]::GetTempPath()
    }
    $root = Join-Path $base 'AsterMaxJobs'
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    $dir = Join-Path $root ($Prefix + '-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Copy-Workspace([string]$Source, [string]$Destination) {
    Get-ChildItem -LiteralPath $Source -Force -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
}

function Convert-ToWindowsExport([string]$Content) {
    $culture = [Globalization.CultureInfo]::InvariantCulture
    $normalized = New-Object 'System.Collections.Generic.List[string]'
    foreach ($line in ($Content -split "`r?`n")) {
        if ($line -match '^P\s+version\s+\S+\s*$') {
            $normalized.Add('P version stable')
            continue
        }
        if ($line -match '^P\s+time_limit\s+([0-9]+(?:\.[0-9]+)?)\s*$') {
            $seconds = [double]::Parse($Matches[1], $culture)
            $normalized.Add('A tpmax ' + $seconds.ToString('0.###', $culture))
            continue
        }
        if ($line -match '^P\s+memory_limit\s+([0-9]+(?:\.[0-9]+)?)\s*$') {
            # Windows standalone as_run uses memjeveux (Mwords). Historical
            # Code_Aster Windows guidance maps memory_limit 512 -> memjeveux 64.
            $memoryMb = [double]::Parse($Matches[1], $culture)
            $normalized.Add('A memjeveux ' + ($memoryMb / 8.0).ToString('0.###', $culture))
            continue
        }
        $normalized.Add($line.Replace('/analysis/', './'))
    }
    return ($normalized -join "`r`n")
}

function Probe-CodeAster([string]$Backend) {
    $stage = New-SafeStageDirectory 'probe'
    try {
        $comm = Join-Path $stage 'probe.comm'
        $export = Join-Path $stage 'probe.export'
        $mess = Join-Path $stage 'probe.mess'
        [IO.File]::WriteAllText($comm, "DEBUT()`r`nFIN()`r`n", (New-Object System.Text.UTF8Encoding($false)))
        # Use the native Windows export syntax documented for standalone as_run.
        $exportText = @(
            'A tpmax 60.0',
            'A memjeveux 64.0',
            'P ncpus 1',
            'P mpi_nbcpu 1',
            'P mpi_nbnoeud 1',
            'F comm ./probe.comm D 1',
            'F mess ./probe.mess R 6',
            'P version stable',
            'P actions make_etude'
        ) -join "`r`n"
        [IO.File]::WriteAllText($export, $exportText + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
        $run = Invoke-WindowsBackend $Backend $export $stage 120000
        $messReady = (Test-Path -LiteralPath $mess -PathType Leaf) -and ((Get-Item -LiteralPath $mess).Length -gt 0)
        return [pscustomobject]@{
            Ready = ($run.ExitCode -eq 0 -and $messReady)
            ExitCode = $run.ExitCode
            Stdout = $run.Stdout
            Stderr = $run.Stderr
            MessReady = $messReady
        }
    }
    catch {
        return [pscustomobject]@{ Ready=$false; ExitCode=124; Stdout=''; Stderr=$_.Exception.Message; MessReady=$false }
    }
    finally {
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$native = $null
$nativeError = $null
try { $native = Find-WindowsBackend } catch { $nativeError = $_.Exception.Message }

if ($ExportFile -eq 'probe') {
    $probe = $null
    if ($native -and -not $nativeError) { $probe = Probe-CodeAster $native }
    $ready = ($native -ne $null) -and ($nativeError -eq $null) -and ($probe -ne $null) -and $probe.Ready
    [ordered]@{
        schema = 'astermax-codeaster-runner-probe/v4'
        ready = $ready
        transport = 'WINDOWS_NATIVE'
        backend = $(if ($native) { $native } else { 'missing' })
        backend_kind = $(if ($native) { [IO.Path]::GetFileName($native) } else { 'missing' })
        configured_backend = $env:ASTERMAX_WINDOWS_CODE_ASTER_COMMAND
        configured_home = $env:ASTERMAX_CODE_ASTER_HOME
        solver_probe_exit_code = $(if ($probe) { $probe.ExitCode } else { $null })
        solver_probe_mess_ready = $(if ($probe) { $probe.MessReady } else { $false })
        message = $(if ($nativeError) { $nativeError } elseif ($probe -and $probe.Stderr) { $probe.Stderr.Trim() } elseif (-not $native) { 'No native Windows Code_Aster launcher found.' } else { '' })
        wsl_required = $false
        synthetic_results_allowed = $false
    } | ConvertTo-Json -Compress | Write-Output
    if ($ready) { exit 0 } else { exit 21 }
}

if ([string]::IsNullOrWhiteSpace($ExportFile)) { Fail 'Missing .export file argument.' 2 }
if ([string]::IsNullOrWhiteSpace($Workspace)) { Fail 'Missing solve workspace argument.' 2 }
if (-not (Test-Path -LiteralPath $ExportFile -PathType Leaf)) { Fail "Export file not found: $ExportFile" 3 }
if (-not (Test-Path -LiteralPath $Workspace -PathType Container)) { Fail "Workspace not found: $Workspace" 3 }
if ($nativeError) { Fail $nativeError 21 }
if (-not $native) {
    Fail 'No native Windows Code_Aster launcher was found. Install Code_Aster for Windows or select its installation folder from Runtime/PREFLIGHT.' 21
}

$resolvedWorkspace = (Resolve-Path -LiteralPath $Workspace).Path
$resolvedExport = (Resolve-Path -LiteralPath $ExportFile).Path
$stage = New-SafeStageDirectory 'solve'
try {
    Copy-Workspace $resolvedWorkspace $stage
    $portableExport = Join-Path $stage 'astermax-windows.export'
    $content = Convert-ToWindowsExport (Get-Content -LiteralPath $resolvedExport -Raw)
    [IO.File]::WriteAllText($portableExport, $content + "`r`n", (New-Object System.Text.UTF8Encoding($false)))

    Write-Output 'ASTERMAX_CODE_ASTER_TRANSPORT=WINDOWS_NATIVE'
    Write-Output ("ASTERMAX_CODE_ASTER_BACKEND=" + $native)
    Write-Output ("ASTERMAX_CODE_ASTER_EXPORT=" + $portableExport)
    Write-Output ("ASTERMAX_CODE_ASTER_STAGE=" + $stage)

    $started = [DateTime]::UtcNow
    $result = Invoke-WindowsBackend $native $portableExport $stage 3600000
    if ($result.Stdout) { Write-Output $result.Stdout.TrimEnd() }
    if ($result.Stderr) { [Console]::Error.WriteLine($result.Stderr.TrimEnd()) }

    Copy-Workspace $stage $resolvedWorkspace

    if ($result.ExitCode -ne 0) { Fail "Native Windows Code_Aster returned exit code $($result.ExitCode)." $result.ExitCode }
    foreach ($extension in @('mess','rmed')) {
        $output = Get-ChildItem -LiteralPath $stage -Filter "*.$extension" -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Length -gt 0 -and $_.LastWriteTimeUtc -ge $started.AddSeconds(-2) } |
            Select-Object -First 1
        if (-not $output) { Fail "Native solver did not produce a fresh non-empty .$extension file." 30 }
    }

    Write-Output 'ASTERMAX_CODE_ASTER_RUNNER=SUCCESS'
    exit 0
}
finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
