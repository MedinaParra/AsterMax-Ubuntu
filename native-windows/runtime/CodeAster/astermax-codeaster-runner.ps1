param(
    [Parameter(Position=0)][string]$ExportFile,
    [Parameter(Position=1)][string]$Workspace
)

$ErrorActionPreference = 'Stop'

function Fail([string]$Message, [int]$Code = 1) {
    [Console]::Error.WriteLine("ASTERMAX_CODE_ASTER_RUNNER: $Message")
    exit $Code
}

function To-AsterPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    return ([System.IO.Path]::GetFullPath($Path)).Replace('\','/')
}

function New-SafeStageDirectory([string]$Prefix) {
    $base = $env:PUBLIC
    if ([string]::IsNullOrWhiteSpace($base) -or -not (Test-Path -LiteralPath $base -PathType Container)) {
        $base = [System.IO.Path]::GetTempPath()
    }
    $root = Join-Path $base 'AsterMaxJobs'
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    $leaf = $Prefix + '-' + [Guid]::NewGuid().ToString('N')
    $dir = Join-Path $root $leaf
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Resolve-LauncherCandidate([string]$Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) { return $null }
    try {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $Candidate).Path
        }
    } catch { }
    return $null
}

function Get-CodeAsterLauncher {
    $configured = Resolve-LauncherCandidate $env:ASTERMAX_WINDOWS_CODE_ASTER_COMMAND
    if ($configured) {
        return [pscustomobject]@{ Path=$configured; Source='environment-command'; Kind=$(if ([IO.Path]::GetFileName($configured) -match '^run_aster') {'run_aster'} else {'as_run'}) }
    }

    $roots = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($env:ASTERMAX_CODE_ASTER_HOME)) { $roots.Add($env:ASTERMAX_CODE_ASTER_HOME) }
    $roots.Add($PSScriptRoot)

    $relativeCandidates = @(
        'bin\run_aster.bat','bin\run_aster.cmd','bin\run_aster.exe',
        'run_aster.bat','run_aster.cmd','run_aster.exe',
        'bin\as_run.bat','bin\as_run.cmd','bin\as_run.exe',
        'as_run.bat','as_run.cmd','as_run.exe'
    )

    foreach ($root in $roots) {
        if ([string]::IsNullOrWhiteSpace($root) -or -not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        foreach ($relative in $relativeCandidates) {
            $found = Resolve-LauncherCandidate (Join-Path $root $relative)
            if ($found) {
                return [pscustomobject]@{ Path=$found; Source=$(if ($root -eq $PSScriptRoot) {'packaged'} else {'environment-home'}); Kind=$(if ([IO.Path]::GetFileName($found) -match '^run_aster') {'run_aster'} else {'as_run'}) }
            }
        }
    }

    # Last chance inside the packaged CodeAster tree. This allows a vendor bundle whose
    # exact directory layout changes between Windows releases without hard-coding it here.
    if (Test-Path -LiteralPath $PSScriptRoot -PathType Container) {
        $preferredNames = @('run_aster.bat','run_aster.cmd','run_aster.exe','as_run.bat','as_run.cmd','as_run.exe')
        foreach ($name in $preferredNames) {
            $found = Get-ChildItem -LiteralPath $PSScriptRoot -Recurse -File -Filter $name -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) {
                return [pscustomobject]@{ Path=$found.FullName; Source='packaged-recursive'; Kind=$(if ($name -match '^run_aster') {'run_aster'} else {'as_run'}) }
            }
        }
    }
    return $null
}

function Invoke-CodeAster([string]$Launcher,[string]$Export,[string]$WorkingDirectory,[int]$TimeoutSeconds) {
    $stdoutFile = [IO.Path]::GetTempFileName()
    $stderrFile = [IO.Path]::GetTempFileName()
    try {
        $ext = [IO.Path]::GetExtension($Launcher).ToLowerInvariant()
        if ($ext -eq '.bat' -or $ext -eq '.cmd') {
            $hostExe = $env:COMSPEC
            if ([string]::IsNullOrWhiteSpace($hostExe)) { $hostExe = 'cmd.exe' }
            $argLine = '/d /s /c ""' + $Launcher + '" "' + $Export + '""'
            $p = Start-Process -FilePath $hostExe -ArgumentList $argLine -WorkingDirectory $WorkingDirectory -NoNewWindow -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        }
        else {
            $p = Start-Process -FilePath $Launcher -ArgumentList ('"' + $Export + '"') -WorkingDirectory $WorkingDirectory -NoNewWindow -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        }

        if (-not $p.WaitForExit($TimeoutSeconds * 1000)) {
            try { $p.Kill() } catch { }
            return [pscustomobject]@{ ExitCode=124; Stdout=(Get-Content -LiteralPath $stdoutFile -Raw -ErrorAction SilentlyContinue); Stderr=('Timed out after ' + $TimeoutSeconds + ' seconds.') }
        }
        return [pscustomobject]@{
            ExitCode=$p.ExitCode
            Stdout=(Get-Content -LiteralPath $stdoutFile -Raw -ErrorAction SilentlyContinue)
            Stderr=(Get-Content -LiteralPath $stderrFile -Raw -ErrorAction SilentlyContinue)
        }
    }
    finally {
        Remove-Item -LiteralPath $stdoutFile,$stderrFile -Force -ErrorAction SilentlyContinue
    }
}

function Probe-CodeAster([object]$LauncherInfo) {
    $probeRoot = New-SafeStageDirectory 'probe'
    try {
        $comm = Join-Path $probeRoot 'probe.comm'
        $export = Join-Path $probeRoot 'probe.export'
        $mess = Join-Path $probeRoot 'probe.mess'
        [IO.File]::WriteAllText($comm, "DEBUT()`nFIN()`n", (New-Object System.Text.UTF8Encoding($false)))
        $commAster = To-AsterPath $comm
        $messAster = To-AsterPath $mess
        $exportText = @(
            'P actions make_etude',
            'P version stable',
            'P mode interactif',
            'P memory_limit 512',
            'P time_limit 60',
            'P ncpus 1',
            'P mpi_nbcpu 1',
            ('F comm ' + $commAster + ' D 1'),
            ('F mess ' + $messAster + ' R 6')
        ) -join "`n"
        [IO.File]::WriteAllText($export, $exportText + "`n", (New-Object System.Text.UTF8Encoding($false)))
        $result = Invoke-CodeAster $LauncherInfo.Path $export $probeRoot 90
        $messReady = (Test-Path -LiteralPath $mess -PathType Leaf) -and ((Get-Item -LiteralPath $mess).Length -gt 0)
        return [pscustomobject]@{
            Ready=($result.ExitCode -eq 0 -and $messReady)
            ExitCode=$result.ExitCode
            Stdout=$result.Stdout
            Stderr=$result.Stderr
            MessReady=$messReady
        }
    }
    finally {
        Remove-Item -LiteralPath $probeRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$launcher = Get-CodeAsterLauncher
if ($ExportFile -eq 'probe') {
    $probe = $null
    if ($launcher) { $probe = Probe-CodeAster $launcher }
    $ready = ($launcher -ne $null) -and ($probe -ne $null) -and $probe.Ready
    [ordered]@{
        schema = 'astermax-codeaster-runner-probe/v2'
        ready = $ready
        transport = 'WINDOWS_NATIVE'
        backend = $(if ($launcher) { $launcher.Path } else { 'missing' })
        backend_kind = $(if ($launcher) { $launcher.Kind } else { 'missing' })
        backend_source = $(if ($launcher) { $launcher.Source } else { 'missing' })
        configured_backend = $env:ASTERMAX_WINDOWS_CODE_ASTER_COMMAND
        configured_home = $env:ASTERMAX_CODE_ASTER_HOME
        solver_probe_exit_code = $(if ($probe) { $probe.ExitCode } else { $null })
        solver_probe_mess_ready = $(if ($probe) { $probe.MessReady } else { $false })
        solver_probe_stderr = $(if ($probe -and $probe.Stderr) { $probe.Stderr.Trim() } else { '' })
        wsl_required = $false
        synthetic_results_allowed = $false
    } | ConvertTo-Json -Compress | Write-Output
    if ($ready) { exit 0 } else { exit 21 }
}

if ([string]::IsNullOrWhiteSpace($ExportFile)) { Fail 'Missing .export file argument.' 2 }
if ([string]::IsNullOrWhiteSpace($Workspace)) { Fail 'Missing solve workspace argument.' 2 }
if (-not (Test-Path -LiteralPath $ExportFile -PathType Leaf)) { Fail "Export file not found: $ExportFile" 3 }
if (-not (Test-Path -LiteralPath $Workspace -PathType Container)) { Fail "Workspace not found: $Workspace" 3 }
if (-not $launcher) {
    Fail 'No native Windows Code_Aster launcher was found. Package run_aster.bat under AsterMaxRuntime\CodeAster, or set ASTERMAX_CODE_ASTER_HOME / ASTERMAX_WINDOWS_CODE_ASTER_COMMAND.' 21
}

$resolvedWorkspace = (Resolve-Path -LiteralPath $Workspace).Path
$resolvedExport = (Resolve-Path -LiteralPath $ExportFile).Path
$stage = New-SafeStageDirectory 'solve'

try {
    # Stage away from user/profile paths (which may contain spaces or non-ASCII characters).
    # Code_Aster sees only this short Windows-native transaction directory.
    Copy-Item -LiteralPath (Join-Path $resolvedWorkspace '*') -Destination $stage -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath $resolvedWorkspace -Force -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $stage -Recurse -Force
    }

    $stageRoot = (To-AsterPath $stage).TrimEnd('/') + '/'
    $portableExport = Join-Path $stage 'astermax-windows.export'
    $text = Get-Content -LiteralPath $resolvedExport -Raw
    $text = $text.Replace('/analysis/', $stageRoot)
    [IO.File]::WriteAllText($portableExport, $text, (New-Object System.Text.UTF8Encoding($false)))

    Write-Output 'ASTERMAX_CODE_ASTER_TRANSPORT=WINDOWS_NATIVE'
    Write-Output ("ASTERMAX_CODE_ASTER_BACKEND=" + $launcher.Path)
    Write-Output ("ASTERMAX_CODE_ASTER_BACKEND_KIND=" + $launcher.Kind)
    Write-Output ("ASTERMAX_CODE_ASTER_EXPORT=" + $portableExport)
    Write-Output ("ASTERMAX_CODE_ASTER_STAGE=" + $stage)

    $run = Invoke-CodeAster $launcher.Path $portableExport $stage 7200
    if ($run.Stdout) { Write-Output $run.Stdout.TrimEnd() }
    if ($run.Stderr) { [Console]::Error.WriteLine($run.Stderr.TrimEnd()) }

    # Always return the transaction evidence to the original AsterMax workspace.
    Get-ChildItem -LiteralPath $stage -Force -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $resolvedWorkspace -Recurse -Force
    }

    if ($run.ExitCode -ne 0) { Fail "Native Windows Code_Aster returned exit code $($run.ExitCode)." $run.ExitCode }

    $mess = Get-ChildItem -LiteralPath $stage -Filter '*.mess' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    $rmed = Get-ChildItem -LiteralPath $stage -Filter '*.rmed' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $mess -or $mess.Length -le 0) { Fail 'Solver returned success but no non-empty .mess file was produced.' 30 }
    if ($null -eq $rmed -or $rmed.Length -le 0) { Fail 'Solver returned success but no non-empty .rmed file was produced.' 31 }

    Write-Output 'ASTERMAX_CODE_ASTER_RUNNER=SUCCESS'
    exit 0
}
finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
