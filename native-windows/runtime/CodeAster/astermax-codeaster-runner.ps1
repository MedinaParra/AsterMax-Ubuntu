param(
    [Parameter(Position=0)][string]$ExportFile,
    [Parameter(Position=1)][string]$Workspace
)

$ErrorActionPreference = 'Stop'
# The packaged caller reads this adapter as UTF-8, including under Windows
# PowerShell 5.1. This changes this process only, never the user's environment.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

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
    $p.StartInfo.StandardOutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $p.StartInfo.StandardErrorEncoding = New-Object System.Text.UTF8Encoding($false)
    # Configure Python in the child environment, without changing $env: values
    # in this process or persistent user/machine settings. EnvironmentVariables
    # is available in .NET Framework used by Windows PowerShell 5.1.
    $p.StartInfo.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $p.StartInfo.EnvironmentVariables['PYTHONUTF8'] = '1'
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
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
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

function Get-ExpectedOutputs([string]$Content, [string]$Stage) {
    $outputs = @{}
    $prefix = [IO.Path]::GetFullPath($Stage).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    foreach ($line in ($Content -split "`r?`n")) {
        if ($line -match '^\s*F\s+(mess|rmed)\s+(\S+)\s+R\s+\d+\s*$') {
            $kind = $Matches[1]
            $relative = $Matches[2]
            if ($outputs.ContainsKey($kind)) { throw "Duplicate $kind output in export." }
            if ([IO.Path]::IsPathRooted($relative)) { throw "Output must be relative to the solve stage: $relative" }
            $path = [IO.Path]::GetFullPath((Join-Path $Stage $relative))
            if (-not $path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Output escapes the solve stage: $relative"
            }
            $outputs[$kind] = $path
        }
    }
    foreach ($kind in @('mess','rmed')) {
        if (-not $outputs.ContainsKey($kind)) { throw "Export has no unambiguous $kind output." }
    }
    if ($outputs.mess -eq $outputs.rmed) { throw 'MESS and RMED outputs must be different files.' }
    return $outputs
}

function Read-CodeAsterText([string]$Path) {
    # Keep the original diagnostic bytes on disk. Prefer BOM/strict UTF-8 for
    # current runtimes; old native Windows launchers may use the ANSI code page.
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -eq 0) { return '' }
    $stream = New-Object IO.MemoryStream(,$bytes)
    $reader = New-Object IO.StreamReader($stream, (New-Object Text.UTF8Encoding($false, $true)), $true)
    try {
        try { return $reader.ReadToEnd() }
        catch [Text.DecoderFallbackException] {
            $codePage = [Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage
            if ($codePage -le 0) { $codePage = 1252 }
            return [Text.Encoding]::GetEncoding($codePage).GetString($bytes)
        }
    } finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Get-CodeAsterFailureEvidence([string]$MessText, [string]$Stdout, [string]$Stderr) {
    # A launcher can print DIAGNOSTIC JOB : OK and return zero after a solver
    # fatal. Inspect the solver's own message first, including before FIN output.
    # Do not require solver identity here: legacy transaction tests deliberately
    # use plain-text stubs. Probe readiness has its separate, stronger contract.
    $firstFailure = $null
    foreach ($sourceText in @($MessText, $Stdout, $Stderr)) {
        if ([string]::IsNullOrWhiteSpace($sourceText)) { continue }
        $text = $sourceText -replace "`0", ''
        foreach ($raw in ($text -split "`r?`n")) {
            $line = $raw.Trim()
            $marker = $null
            if ($line -match '^(?:EXECUTION_CODE_ASTER_EXIT_[^=\s]+|EXIT_CODE)\s*=\s*(.+)$') {
                $exitCode = 0
                if (-not [int]::TryParse($Matches[1].Trim(), [ref]$exitCode)) {
                    $marker = 'CODE_ASTER_INVALID_EXIT'
                } elseif ($exitCode -ne 0) {
                    $marker = 'CODE_ASTER_NONZERO_EXIT'
                }
            }
            # Native Code_Aster can label the same fatal diagnostic <F> or
            # <EXCEPTION>; neither is overridden by a later normal FIN/exit 0.
            if ($line -match '(?i)(?:^\s*[!|]?\s*<(?:F|EXCEPTION)(?:>|_)|<(?:F|EXCEPTION)>\s*<|FATAL ERROR|ERREUR[ _]+FATALE|Traceback \(most recent call last\)|_ABNORMAL_ABORT|DIAGNOSTIC\s+JOB\s*:\s*<(?:F|EXCEPTION)>)') {
                $tag = [regex]::Match($line, '(?i)<(?:F|EXCEPTION)>\s*<(?<marker>[A-Z][A-Z0-9_]+)>|<(?:F|EXCEPTION)>_(?<marker>[A-Z][A-Z0-9_]+)')
                if ($tag.Success) { $marker = $tag.Groups['marker'].Value.ToUpperInvariant() }
                elseif ($line -match '(?i)Traceback \(most recent call last\)') { $marker = 'PYTHON_TRACEBACK' }
                else { $marker = 'CODE_ASTER_FATAL' }
            }
            if (-not $marker) { continue }
            $failure = [pscustomobject]@{
                Marker = $marker
                ContactZones = @()
                SharedSlaveNodes = $null
                Message = ('Code_Aster reported fatal diagnostic ' + $marker + '.')
            }
            if ($marker -eq 'CONTACT2_16') {
                # Parse only this diagnostic's following text, not earlier zones
                # echoed from the command file. ASCII digits survive old OEM or
                # ANSI accent corruption; a missing translation stays unknown.
                $start = $text.IndexOf($raw, [StringComparison]::Ordinal)
                $context = $text.Substring($start, [Math]::Min(4096, $text.Length - $start))
                $context = ($context -replace '[!|]', ' ') -replace '\s+', ' '
                $zones = [regex]::Match($context, '(?i)\bzones?\s+de\s+contact\s+num[^0-9]{0,30}(?<a>[0-9]+)\s+et\s+num[^0-9]{0,30}(?<b>[0-9]+)\s+ont\s+(?<n>[0-9]+)\s+n\S*\s+communs')
                if (-not $zones.Success) {
                    $zones = [regex]::Match($context, '(?i)\bcontact\s+zones?\s+(?:number\s+)?(?<a>[0-9]+)\s+and\s+(?:number\s+)?(?<b>[0-9]+)\s+have\s+(?<n>[0-9]+)\s+(?:common|shared)\s+nodes')
                }
                if ($zones.Success) {
                    $a = 0; $b = 0; $n = 0
                    if ([int]::TryParse($zones.Groups['a'].Value, [ref]$a) -and
                        [int]::TryParse($zones.Groups['b'].Value, [ref]$b) -and
                        [int]::TryParse($zones.Groups['n'].Value, [ref]$n)) {
                        $failure.ContactZones = @($a, $b)
                        $failure.SharedSlaveNodes = $n
                        $failure.Message = "Code_Aster CONTACT2_16: contact zones $a and $b share $n slave nodes."
                    }
                }
                return $failure
            }
            if (-not $firstFailure) { $firstFailure = $failure }
        }
    }
    return $firstFailure
}

function Write-RunnerFailureDiagnostic {
    param(
        [string]$Stage, [string]$MessPath, [string]$StdoutPath, [string]$StderrPath,
        [string]$Kind, [int]$ExitCode, $BackendExitCode, $Failure
    )
    $diagnosticPath = Join-Path $Stage 'astermax-runner-diagnostic.json'
    $message = [string]$Failure.Message
    if ($message.Length -gt 500) { $message = $message.Substring(0, 500) }
    $diagnostic = [ordered]@{
        schema = 'astermax-codeaster-runner-diagnostic/v1'
        status = 'failed'
        failure_kind = $Kind
        marker = [string]$Failure.Marker
        exit_code = $ExitCode
        backend_exit_code = $BackendExitCode
        contact_zones = @($Failure.ContactZones)
        shared_slave_nodes = $Failure.SharedSlaveNodes
        message = $message
        stage = $Stage
        mess_path = $MessPath
        stdout_path = $StdoutPath
        stderr_path = $StderrPath
    }
    [IO.File]::WriteAllText($diagnosticPath, ($diagnostic | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
    $markerLine = 'ASTERMAX_CODE_ASTER_FAILURE=' + $Failure.Marker
    if (@($Failure.ContactZones).Count -eq 2) {
        $markerLine += ';contact_zones=' + ($Failure.ContactZones -join ',')
        $markerLine += ';shared_slave_nodes=' + $Failure.SharedSlaveNodes
    }
    Write-Output $markerLine
    Write-Output ('ASTERMAX_CODE_ASTER_DIAGNOSTIC=' + $diagnosticPath)
}

function Get-CodeAsterProbeEvidence([string]$MessText, [string]$Stdout, [string]$Stderr) {
    # A native launcher may return zero even when Code_Aster reports a fatal
    # diagnostic. Match the transaction's failure semantics before accepting a
    # normal-stop marker, and require the solver's identity in its own .mess.
    $identity = -not [string]::IsNullOrWhiteSpace($MessText) -and
        [regex]::IsMatch($MessText, '(?i)\bCODE[_ -]?ASTER\b')
    $normalStop = $false
    $failure = $null
    $combined = (($MessText, $Stdout, $Stderr) -join "`n") -replace "`0", ''
    foreach ($raw in ($combined -split "`r?`n")) {
        $line = $raw.Trim()
        if ($line -match '^(?:EXECUTION_CODE_ASTER_EXIT_[^=\s]+|EXIT_CODE)\s*=\s*(.+)$') {
            $exitCode = 0
            if (-not [int]::TryParse($Matches[1].Trim(), [ref]$exitCode)) {
                $failure = 'Invalid Code_Aster exit marker: ' + $line
                break
            }
            if ($exitCode -ne 0) {
                $failure = 'Code_Aster exit marker: ' + $line
                break
            }
            $normalStop = $true
        }
        if ($line -match '(?i)(?:^\s*[!|]?\s*<(?:F|EXCEPTION)(?:>|_)|<(?:F|EXCEPTION)>\s*<|FATAL ERROR|ERREUR[ _]+FATALE|Traceback \(most recent call last\)|_ABNORMAL_ABORT|DIAGNOSTIC\s+JOB\s*:\s*<(?:F|EXCEPTION)>)') {
            $failure = 'Code_Aster fatal diagnostic: ' + $line
            break
        }
        # The provider writes both ARRET NORMAL and Arret normal with an
        # accented e. Legacy OEM bytes decoded as UTF-8 can produce U+FFFD.
        if ($line -match '(?i)\bARR(?:E|\u00CA|\u00DB|\uFFFD)T\s+NORMAL\b') {
            $normalStop = $true
        }
    }
    if (-not $failure -and -not $identity) { $failure = 'Code_Aster identity was not found in the probe .mess file.' }
    if (-not $failure -and -not $normalStop) { $failure = 'Code_Aster normal-stop evidence was not found in the probe output.' }
    if ($failure -and $failure.Length -gt 500) { $failure = $failure.Substring(0, 500) }
    return [pscustomobject]@{
        Ready = ($identity -and $normalStop -and -not $failure)
        IdentityVerified = [bool]$identity
        NormalStop = [bool]$normalStop
        Message = $failure
    }
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
        $messText = $(if ($messReady) { Read-CodeAsterText $mess } else { '' })
        $evidence = Get-CodeAsterProbeEvidence $messText $run.Stdout $run.Stderr
        return [pscustomobject]@{
            Ready = ($run.ExitCode -eq 0 -and $messReady -and $evidence.Ready)
            ExitCode = $run.ExitCode
            Stdout = $run.Stdout
            Stderr = $run.Stderr
            MessReady = $messReady
            IdentityVerified = $evidence.IdentityVerified
            NormalStop = $evidence.NormalStop
            Message = $(if ($run.ExitCode -ne 0) { 'Native Code_Aster probe returned exit code ' + $run.ExitCode + '.' } else { $evidence.Message })
        }
    }
    catch {
        return [pscustomobject]@{ Ready=$false; ExitCode=124; Stdout=''; Stderr=$_.Exception.Message; MessReady=$false; IdentityVerified=$false; NormalStop=$false; Message=$_.Exception.Message }
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
        solver_probe_identity_verified = $(if ($probe) { $probe.IdentityVerified } else { $false })
        solver_probe_normal_stop = $(if ($probe) { $probe.NormalStop } else { $false })
        message = $(if ($nativeError) { $nativeError } elseif ($probe -and $probe.Message) { $probe.Message } elseif ($probe -and $probe.Stderr) { $probe.Stderr.Trim() } elseif (-not $native) { 'No native Windows Code_Aster launcher found.' } else { '' })
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
$completed = $false
$result = $null
$expectedOutputs = @{}
$stdoutPath = Join-Path $stage 'astermax-native.stdout.log'
$stderrPath = Join-Path $stage 'astermax-native.stderr.log'
try {
    Copy-Workspace $resolvedWorkspace $stage
    $portableExport = Join-Path $stage 'astermax-windows.export'
    $content = Convert-ToWindowsExport (Get-Content -LiteralPath $resolvedExport -Raw)
    $expectedOutputs = Get-ExpectedOutputs $content $stage
    # A rerun may copy recent outputs into the stage. Remove the exact declared
    # outputs before launch; timestamps alone cannot prove that this run wrote them.
    foreach ($path in @($expectedOutputs.Values) + @($stdoutPath, $stderrPath, (Join-Path $stage 'astermax-runner-diagnostic.json'))) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
    [IO.File]::WriteAllText($portableExport, $content + "`r`n", (New-Object System.Text.UTF8Encoding($false)))

    Write-Output 'ASTERMAX_CODE_ASTER_TRANSPORT=WINDOWS_NATIVE'
    Write-Output ("ASTERMAX_CODE_ASTER_BACKEND=" + $native)
    Write-Output ("ASTERMAX_CODE_ASTER_EXPORT=" + $portableExport)
    Write-Output ("ASTERMAX_CODE_ASTER_STAGE=" + $stage)

    $result = Invoke-WindowsBackend $native $portableExport $stage 3600000
    [IO.File]::WriteAllText($stdoutPath, $result.Stdout, (New-Object Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($stderrPath, $result.Stderr, (New-Object Text.UTF8Encoding($false)))
    $messText = $(if (Test-Path -LiteralPath $expectedOutputs.mess -PathType Leaf) { Read-CodeAsterText $expectedOutputs.mess } else { '' })
    $failure = Get-CodeAsterFailureEvidence $messText $result.Stdout $result.Stderr
    if ($failure) {
        Write-RunnerFailureDiagnostic $stage $expectedOutputs.mess $stdoutPath $stderrPath 'solver_fatal' 31 $result.ExitCode $failure
        Fail $failure.Message 31
    }

    if ($result.ExitCode -ne 0) {
        $failure = [pscustomobject]@{ Marker='NATIVE_PROCESS_EXIT'; ContactZones=@(); SharedSlaveNodes=$null; Message="Native Windows Code_Aster returned exit code $($result.ExitCode)." }
        Write-RunnerFailureDiagnostic $stage $expectedOutputs.mess $stdoutPath $stderrPath 'process_exit' $result.ExitCode $result.ExitCode $failure
        Fail $failure.Message $result.ExitCode
    }
    foreach ($kind in @('mess','rmed')) {
        $path = $expectedOutputs[$kind]
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) {
            $failure = [pscustomobject]@{ Marker='MISSING_OUTPUT'; ContactZones=@(); SharedSlaveNodes=$null; Message="Native solver did not produce the declared non-empty $kind output: $path" }
            Write-RunnerFailureDiagnostic $stage $expectedOutputs.mess $stdoutPath $stderrPath 'missing_output' 30 $result.ExitCode $failure
            Fail $failure.Message 30
        }
    }

    if ($result.Stdout) { Write-Output $result.Stdout.TrimEnd() }
    if ($result.Stderr) { [Console]::Error.WriteLine($result.Stderr.TrimEnd()) }
    Copy-Workspace $stage $resolvedWorkspace
    $completed = $true
    Write-Output 'ASTERMAX_CODE_ASTER_RUNNER=SUCCESS'
    exit 0
}
catch {
    $failure = [pscustomobject]@{ Marker='RUNNER_ERROR'; ContactZones=@(); SharedSlaveNodes=$null; Message=$_.Exception.Message }
    try {
        Write-RunnerFailureDiagnostic $stage $expectedOutputs.mess $stdoutPath $stderrPath 'runner_error' 1 $(if ($result) { $result.ExitCode } else { $null }) $failure
    } catch { [Console]::Error.WriteLine('Could not write the structured runner diagnostic: ' + $_.Exception.Message) }
    Fail $failure.Message 1
}
finally {
    if ($completed) {
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        # Preserve the complete stage on process failure, timeout or copy error.
        # Copy diagnostics into a separate directory, never promote failed outputs.
        $diagnostics = Join-Path $resolvedWorkspace ('failed-' + (Split-Path $stage -Leaf))
        try {
            New-Item -ItemType Directory -Path $diagnostics -Force | Out-Null
            Copy-Workspace $stage $diagnostics
        } catch {
            [Console]::Error.WriteLine("Could not copy diagnostics: " + $_.Exception.Message)
        }
        [Console]::Error.WriteLine("ASTERMAX_CODE_ASTER_FAILED_STAGE=" + $stage)
    }
}
