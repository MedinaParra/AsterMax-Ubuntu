# These fixtures and process stubs exercise diagnostic/publication contracts.
# They are NOT Code_Aster execution, MED validation, or evidence of FEA accuracy.
param([string]$OutDir)
$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'runtime/CodeAster/astermax-codeaster-runner.ps1'
$tokens = $null; $parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($runner, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
foreach ($name in @('Read-CodeAsterText','Get-CodeAsterFailureEvidence','Get-CodeAsterProbeEvidence','Invoke-NativeProcess')) {
    $helper = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }, $true)
    if (-not $helper) { throw "Missing runner helper: $name" }
    . ([scriptblock]::Create($helper.Extent.Text))
}

# ASCII source is intentional for Windows PowerShell 5.1; fixture strings still
# contain real French accents and are written with explicit byte encodings.
$acute = [char]0xE9
$circumflex = [char]0xEA
$header = '-- CODE_ASTER -- VERSION : 16.9.0 (deliberate contract fixture)'
$normal = $header + "`n<I> <FIN> Arr" + $circumflex + "t normal dans FIN.`n"
$contact = $header + "`n! <F> <CONTACT2_16> !`n! Les zones de contact num" + $acute + 'ro 13 et num' + $acute + "ro 28 ont 12 noeuds communs`n! " + "a leurs surfaces esclaves : c'est interdit. !`n"
$exceptionContact = $contact.Replace('<F>', '<EXCEPTION>')
$wrappedContact = $contact.Replace('ro 13 et num', "ro 13 !`n! et num")
$mojibakeContact = $contact.Replace([string]$acute, ([string][char]0xC3 + [char]0xA9))
$fixtures = @(
    @{ Name='normal-accented'; Mess=$normal; Out=''; Err=''; Marker=$null },
    @{ Name='legacy-transaction-stub'; Mess='current'; Out=''; Err=''; Marker=$null },
    @{ Name='alarm-with-normal-stop'; Mess=($normal + '<A> <CONTACT2_10> informational alarm'); Out=''; Err=''; Marker=$null },
    @{ Name='ordinary-french-message'; Mess=($normal + 'ERREUR_RELATIVE=0.00001; nombre de contraintes'); Out=''; Err=''; Marker=$null },
    @{ Name='marker-mentioned-without-fatal'; Mess=($normal + 'Documentation: CONTACT2_16'); Out=''; Err=''; Marker=$null },
    @{ Name='ordinary-exception-word'; Mess=($normal + 'Exception handling is available.'); Out=''; Err=''; Marker=$null },
    @{ Name='zero-exit-markers'; Mess=($normal + 'EXIT_CODE=0'); Out='EXECUTION_CODE_ASTER_EXIT_2=0'; Err=''; Marker=$null },
    @{ Name='fatal-with-job-ok'; Mess=$contact; Out='DIAGNOSTIC JOB : OK'; Err=''; Marker='CONTACT2_16'; Zones=@(13,28); Nodes=12 },
    @{ Name='fatal-after-fin'; Mess=($normal + $contact); Out='EXECUTION_CODE_ASTER_EXIT_2=0'; Err=''; Marker='CONTACT2_16'; Zones=@(13,28); Nodes=12 },
    @{ Name='fatal-wrapped-french'; Mess=$wrappedContact; Out=''; Err=''; Marker='CONTACT2_16'; Zones=@(13,28); Nodes=12 },
    @{ Name='fatal-accent-mojibake'; Mess=$mojibakeContact; Out=''; Err=''; Marker='CONTACT2_16'; Zones=@(13,28); Nodes=12 },
    @{ Name='fatal-unknown-translation'; Mess='<F> <CONTACT2_16> unknown translation'; Out=''; Err=''; Marker='CONTACT2_16'; Zones=@(); Nodes=$null },
    @{ Name='fatal-specific-before-cleanup'; Mess=('<F> <SUPERVIS_2> cleanup failed' + "`n" + $contact); Out=''; Err=''; Marker='CONTACT2_16'; Zones=@(13,28); Nodes=12 },
    @{ Name='fatal-stdout'; Mess=$normal; Out=$contact; Err=''; Marker='CONTACT2_16'; Zones=@(13,28); Nodes=12 },
    @{ Name='exception-mess-with-job-ok'; Mess=$exceptionContact; Out='DIAGNOSTIC JOB : OK'; Err=''; Marker='CONTACT2_16'; Zones=@(13,28); Nodes=12 },
    @{ Name='exception-mess-after-fin'; Mess=($normal + $exceptionContact); Out='EXECUTION_CODE_ASTER_EXIT_2=0'; Err=''; Marker='CONTACT2_16'; Zones=@(13,28); Nodes=12 },
    @{ Name='exception-stdout-after-fin'; Mess=$normal; Out=($normal + $exceptionContact); Err=''; Marker='CONTACT2_16'; Zones=@(13,28); Nodes=12 },
    @{ Name='exception-stderr'; Mess=$normal; Out='DIAGNOSTIC JOB : OK'; Err=$exceptionContact; Marker='CONTACT2_16'; Zones=@(13,28); Nodes=12 },
    @{ Name='exception-tag-only'; Mess=($normal + '! <EXCEPTION> failure !'); Out=''; Err=''; Marker='CODE_ASTER_FATAL' },
    @{ Name='fatal-other-tag'; Mess=($normal + '<F> <MODELISA_7> failed'); Out=''; Err=''; Marker='MODELISA_7' },
    @{ Name='fatal-french'; Mess=($normal + 'ERREUR FATALE'); Out=''; Err=''; Marker='CODE_ASTER_FATAL' },
    @{ Name='python-traceback'; Mess=$normal; Out=''; Err='Traceback (most recent call last):'; Marker='PYTHON_TRACEBACK' },
    @{ Name='abnormal-abort'; Mess=$normal; Out='DIAGNOSTIC JOB : <F>_ABNORMAL_ABORT'; Err=''; Marker='ABNORMAL_ABORT' },
    @{ Name='nonzero-marker'; Mess=($normal + 'EXECUTION_CODE_ASTER_EXIT_123=4'); Out='DIAGNOSTIC JOB : OK'; Err=''; Marker='CODE_ASTER_NONZERO_EXIT' },
    @{ Name='invalid-marker'; Mess=$normal; Out='EXIT_CODE=unknown'; Err=''; Marker='CODE_ASTER_INVALID_EXIT' }
)
$fixturePassed = 0
foreach ($case in $fixtures) {
    $failure = Get-CodeAsterFailureEvidence $case.Mess $case.Out $case.Err
    if ($null -eq $case.Marker) {
        if ($failure) { throw "Normal fixture rejected: $($case.Name), marker=$($failure.Marker)" }
    } else {
        if (-not $failure -or $failure.Marker -ne $case.Marker) { throw "Wrong failure marker: $($case.Name)" }
        if ($case.ContainsKey('Zones') -and (($failure.ContactZones -join ',') -ne ($case.Zones -join ','))) { throw "Wrong contact zones: $($case.Name)" }
        if ($case.ContainsKey('Nodes') -and $failure.SharedSlaveNodes -ne $case.Nodes) { throw "Wrong shared node count: $($case.Name)" }
    }
    $fixturePassed++
    Write-Host "PASS runner failure fixture: $($case.Name) (not solver evidence)"
}

$probeFixtures = @(
    @{ Name='normal'; Mess=$normal; Out=''; Err=''; Ready=$true },
    @{ Name='ordinary-exception-word'; Mess=($normal + 'Exception handling is available.'); Out=''; Err=''; Ready=$true },
    @{ Name='exception-mess'; Mess=$exceptionContact; Out='DIAGNOSTIC JOB : OK'; Err=''; Ready=$false },
    @{ Name='exception-mess-after-fin'; Mess=($normal + $exceptionContact); Out='EXECUTION_CODE_ASTER_EXIT_2=0'; Err=''; Ready=$false },
    @{ Name='exception-stdout-after-fin'; Mess=$normal; Out=($normal + $exceptionContact); Err=''; Ready=$false },
    @{ Name='exception-stderr'; Mess=$normal; Out='DIAGNOSTIC JOB : OK'; Err=$exceptionContact; Ready=$false },
    @{ Name='exception-tag-only'; Mess=($normal + '! <EXCEPTION> failure !'); Out=''; Err=''; Ready=$false }
)
$probePassed = 0
foreach ($case in $probeFixtures) {
    $evidence = Get-CodeAsterProbeEvidence $case.Mess $case.Out $case.Err
    if ($evidence.Ready -ne $case.Ready) { throw "Probe EXCEPTION regression failed: $($case.Name)" }
    if (-not $case.Ready -and $evidence.Message -notmatch '<EXCEPTION>') { throw "Probe lost its EXCEPTION diagnostic: $($case.Name)" }
    if (-not $case.Ready -and $case.Name -ne 'exception-tag-only' -and $evidence.Message -notmatch 'CONTACT2_16') { throw "Probe lost the CONTACT2_16 marker: $($case.Name)" }
    $probePassed++
}

$root = Join-Path ([IO.Path]::GetTempPath()) ('astermax runner failure contracts ' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
$stages = New-Object 'System.Collections.Generic.List[string]'
$encodingPassed = 0; $environmentPassed = 0; $processPassed = 0
$previousIo = [Environment]::GetEnvironmentVariable('PYTHONIOENCODING','Process')
$previousUtf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8','Process')
try {
    foreach ($encoding in @((New-Object Text.UTF8Encoding($false)), (New-Object Text.UTF8Encoding($true)), [Text.Encoding]::Unicode, [Text.Encoding]::GetEncoding([Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage))) {
        $path = Join-Path $root ('encoding-' + $encodingPassed + '.mess')
        [IO.File]::WriteAllText($path, $contact, $encoding)
        $original = [Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
        $decoded = Read-CodeAsterText $path
        if ($decoded -cne $contact) { throw "Diagnostic text was corrupted: $($encoding.WebName), BOM=$($encoding.GetPreamble().Length)" }
        $failure = Get-CodeAsterFailureEvidence $decoded '' ''
        if ($failure.Marker -ne 'CONTACT2_16' -or ($failure.ContactZones -join ',') -ne '13,28') { throw 'Encoded diagnostic lost contact metadata.' }
        if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($path)) -cne $original) { throw 'Reading a diagnostic modified original bytes.' }
        $encodingPassed++
    }

    $environmentStub = Join-Path $root 'environment-contract-stub.ps1'
    @'
# Deliberate encoding/environment process stub; not a solver.
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
[ordered]@{
    pythonioencoding=$env:PYTHONIOENCODING
    pythonutf8=$env:PYTHONUTF8
    accented=('Arr' + [char]0xEA + 't normal')
} | ConvertTo-Json -Compress | Write-Output
[Console]::Error.WriteLine('num' + [char]0xE9 + 'ro')
'@ | Set-Content -LiteralPath $environmentStub -Encoding UTF8
    $thisPowerShell = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
    foreach ($existingValues in @($true, $false)) {
        if ($existingValues) { $env:PYTHONIOENCODING = 'latin-1'; $env:PYTHONUTF8 = '0' }
        else { Remove-Item Env:PYTHONIOENCODING,Env:PYTHONUTF8 -ErrorAction SilentlyContinue }
        $expectedIo = [Environment]::GetEnvironmentVariable('PYTHONIOENCODING','Process')
        $expectedUtf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8','Process')
        $run = Invoke-NativeProcess $thisPowerShell ('-NoLogo -NoProfile -File "' + $environmentStub + '"') $root 30000
        if ($run.ExitCode -ne 0) { throw 'Environment/encoding process stub failed.' }
        $data = $run.Stdout | ConvertFrom-Json
        if ($data.pythonioencoding -ne 'utf-8' -or $data.pythonutf8 -ne '1') { throw 'Child Python encoding was not explicitly configured.' }
        if ($data.accented -cne ('Arr' + $circumflex + 't normal') -or $run.Stderr.Trim() -cne ('num' + $acute + 'ro')) { throw 'UTF-8 stdout/stderr were decoded incorrectly.' }
        if ([Environment]::GetEnvironmentVariable('PYTHONIOENCODING','Process') -cne $expectedIo -or [Environment]::GetEnvironmentVariable('PYTHONUTF8','Process') -cne $expectedUtf8) { throw 'Runner mutated the parent Python environment.' }
        $environmentPassed++
    }

    if ($env:OS -eq 'Windows_NT') {
        $fullLog = 'FULL_LOG_SENTINEL ' + ('detailed diagnostic ' * 200) + ' fin' + $acute
        $processCases = @(
            @{ Name='success-with-alarm'; Mess=($normal + '<A> <CONTACT2_10> informational alarm'); Rmed='current contract stub'; Out='normal contract stub'; Err=''; Code=0; Expected=0; Marker=$null },
            @{ Name='fatal-code0-partial-rmed'; Mess=$contact; Rmed='partial invalid result'; Out=('DIAGNOSTIC JOB : OK' + "`n" + $fullLog); Err=''; Code=0; Expected=31; Marker='CONTACT2_16' },
            @{ Name='fatal-code8-partial-rmed'; Mess=$contact; Rmed='partial invalid result'; Out=$fullLog; Err=''; Code=8; Expected=31; Marker='CONTACT2_16' },
            @{ Name='exception-code0-partial-rmed'; Mess=$exceptionContact; Rmed='partial invalid result'; Out=('DIAGNOSTIC JOB : OK' + "`n" + $fullLog); Err=''; Code=0; Expected=31; Marker='CONTACT2_16' },
            @{ Name='exception-after-fin-code0-partial-rmed'; Mess=($normal + $exceptionContact); Rmed='partial invalid result'; Out='EXECUTION_CODE_ASTER_EXIT_2=0'; Err=''; Code=0; Expected=31; Marker='CONTACT2_16' },
            @{ Name='exception-stdout-code0-partial-rmed'; Mess=$normal; Rmed='partial invalid result'; Out=($normal + $exceptionContact); Err=''; Code=0; Expected=31; Marker='CONTACT2_16' },
            @{ Name='fatal-no-rmed'; Mess=$contact; Rmed=$null; Out='DIAGNOSTIC JOB : OK'; Err=''; Code=0; Expected=31; Marker='CONTACT2_16' },
            @{ Name='fatal-ansi-mess'; Mess=$contact; Encoding='ansi'; Rmed='partial invalid result'; Out=''; Err=''; Code=0; Expected=31; Marker='CONTACT2_16' },
            @{ Name='fatal-stdout'; Mess=$normal; Rmed='partial invalid result'; Out=$contact; Err=''; Code=0; Expected=31; Marker='CONTACT2_16' },
            @{ Name='fatal-stderr'; Mess=$normal; Rmed='partial invalid result'; Out=''; Err='Traceback (most recent call last):'; Code=0; Expected=31; Marker='PYTHON_TRACEBACK' },
            @{ Name='nonzero-exit-marker'; Mess=($normal + 'EXIT_CODE=4'); Rmed='partial invalid result'; Out='DIAGNOSTIC JOB : OK'; Err=''; Code=0; Expected=31; Marker='CODE_ASTER_NONZERO_EXIT' },
            @{ Name='nonzero-process'; Mess='launcher failure diagnostic'; Rmed=$null; Out=$fullLog; Err=''; Code=9; Expected=9; Marker='NATIVE_PROCESS_EXIT' },
            @{ Name='missing-rmed'; Mess=$normal; Rmed=$null; Out=''; Err=''; Code=0; Expected=30; Marker='MISSING_OUTPUT' },
            @{ Name='stale-outputs'; Mess=$null; Rmed=$null; Out=''; Err=''; Code=0; Expected=30; Marker='MISSING_OUTPUT' }
        )
        foreach ($case in $processCases) {
            $directory = Join-Path $root $case.Name
            $workspace = Join-Path $directory 'workspace with spaces'
            New-Item -ItemType Directory -Path $workspace -Force | Out-Null
            $export = Join-Path $workspace 'case.export'
            @('F mess /analysis/case.mess R 6','F rmed /analysis/case.rmed R 81') | Set-Content -LiteralPath $export -Encoding ASCII
            [IO.File]::WriteAllText((Join-Path $workspace 'case.mess'), 'preexisting diagnostic', (New-Object Text.UTF8Encoding($false)))
            [IO.File]::WriteAllText((Join-Path $workspace 'case.rmed'), 'preexisting result', (New-Object Text.UTF8Encoding($false)))
            $case | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'contract-fixture.json') -Encoding UTF8
            @'
# Deliberate process stub: these text outputs are not numerical MED files.
param([string]$Fixture)
$data = Get-Content -LiteralPath $Fixture -Raw -Encoding UTF8 | ConvertFrom-Json
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$encoding = New-Object Text.UTF8Encoding($false)
if ($data.Encoding -eq 'ansi') { $encoding = [Text.Encoding]::GetEncoding([Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage) }
if ($null -ne $data.Mess) { [IO.File]::WriteAllText((Join-Path (Get-Location).Path 'case.mess'), [string]$data.Mess, $encoding) }
if ($null -ne $data.Rmed) { [IO.File]::WriteAllText((Join-Path (Get-Location).Path 'case.rmed'), [string]$data.Rmed, (New-Object Text.UTF8Encoding($false))) }
if ($data.Out) { [Console]::Out.WriteLine([string]$data.Out) }
if ($data.Err) { [Console]::Error.WriteLine([string]$data.Err) }
exit ([int]$data.Code)
'@ | Set-Content -LiteralPath (Join-Path $directory 'contract-stub.ps1') -Encoding UTF8
            $backend = Join-Path $directory 'contract-stub.cmd'
            @('@echo off','rem Diagnostic contract stub, NOT a solver.','"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0contract-stub.ps1" "%~dp0contract-fixture.json"','exit /b %errorlevel%') | Set-Content -LiteralPath $backend -Encoding ASCII
            $process = New-Object Diagnostics.Process
            $process.StartInfo.FileName = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
            $process.StartInfo.Arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $runner + '" "' + $export + '" "' + $workspace + '"'
            $process.StartInfo.UseShellExecute = $false
            $process.StartInfo.RedirectStandardOutput = $true
            $process.StartInfo.RedirectStandardError = $true
            $process.StartInfo.StandardOutputEncoding = New-Object Text.UTF8Encoding($false)
            $process.StartInfo.StandardErrorEncoding = New-Object Text.UTF8Encoding($false)
            $process.StartInfo.EnvironmentVariables['ASTERMAX_WINDOWS_CODE_ASTER_COMMAND'] = $backend
            try {
                [void]$process.Start()
                $stdout = $process.StandardOutput.ReadToEndAsync()
                $stderr = $process.StandardError.ReadToEndAsync()
                if (-not $process.WaitForExit(30000)) { & (Join-Path $env:SystemRoot 'System32/taskkill.exe') /PID $process.Id /T /F 2>&1 | Out-Null; throw "Runner contract timed out: $($case.Name)" }
                $code = $process.ExitCode
                $log = $stdout.Result + "`n" + $stderr.Result
            } finally { $process.Dispose() }
            if ($log -match 'ASTERMAX_CODE_ASTER_FAILED_STAGE=([^\r\n]+)') { $stages.Add($Matches[1]) }
            if ($code -ne $case.Expected) { throw "Wrong wrapper exit: $($case.Name), got=$code expected=$($case.Expected), log=$log" }
            if ($code -eq 0) {
                if ($log -notmatch 'ASTERMAX_CODE_ASTER_RUNNER=SUCCESS' -or [IO.File]::ReadAllText((Join-Path $workspace 'case.rmed')) -cne $case.Rmed) { throw 'Successful current transaction was not promoted.' }
            } else {
                if ($log -match 'ASTERMAX_CODE_ASTER_RUNNER=SUCCESS|FULL_LOG_SENTINEL') { throw 'Failed transaction was accepted or dumped its full diagnostic into the UI stream.' }
                if ([IO.File]::ReadAllText((Join-Path $workspace 'case.rmed')) -cne 'preexisting result' -or [IO.File]::ReadAllText((Join-Path $workspace 'case.mess')) -cne 'preexisting diagnostic') { throw 'Failed or stale outputs were promoted.' }
                if ($log -notmatch 'ASTERMAX_CODE_ASTER_DIAGNOSTIC=([^\r\n]+)') { throw 'Failure has no structured diagnostic path.' }
                $diagnosticPath = $Matches[1]
                $diagnostic = Get-Content -LiteralPath $diagnosticPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($diagnostic.schema -ne 'astermax-codeaster-runner-diagnostic/v1' -or $diagnostic.status -ne 'failed' -or $diagnostic.marker -ne $case.Marker -or $diagnostic.exit_code -ne $code -or $diagnostic.backend_exit_code -ne $case.Code) { throw 'Incorrect structured failure metadata.' }
                if ($case.Marker -eq 'CONTACT2_16' -and (($diagnostic.contact_zones -join ',') -ne '13,28' -or $diagnostic.shared_slave_nodes -ne 12)) { throw 'CONTACT2_16 metadata was not extracted.' }
                if (([IO.File]::ReadAllText($diagnostic.stdout_path)).TrimEnd() -cne ([string]$case.Out).TrimEnd() -or ([IO.File]::ReadAllText($diagnostic.stderr_path)).TrimEnd() -cne ([string]$case.Err).TrimEnd()) { throw 'Full subprocess output was not preserved in UTF-8 logs.' }
                if ($null -ne $case.Mess -and (Read-CodeAsterText $diagnostic.mess_path) -cne $case.Mess) { throw 'Full solver message was not preserved.' }
                $copied = Join-Path $workspace ('failed-' + (Split-Path $diagnostic.stage -Leaf))
                if (-not (Test-Path -LiteralPath (Join-Path $copied 'astermax-runner-diagnostic.json'))) { throw 'Failure diagnostic was not copied into the workspace.' }
                if ($null -ne $case.Mess -and [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $copied 'case.mess'))) -cne [Convert]::ToBase64String([IO.File]::ReadAllBytes($diagnostic.mess_path))) { throw 'Failed .mess bytes changed during diagnostic preservation.' }
            }
            $processPassed++
            Write-Host "PASS runner failure process: $($case.Name) (command stub; not solver evidence)"
        }
    } else {
        Write-Host 'C1207_RUNNER_FAILURE_PROCESSES=NOT_RUN (Windows PowerShell 5.1 only)'
    }

    $summary = [ordered]@{ schema='astermax-runner-failure-contract-tests/v1'; status='PASS'; test_kind='fixtures_and_command_stubs'; fea_verified=$false; fixture_passed=$fixturePassed; probe_exception_fixture_passed=$probePassed; encoding_passed=$encodingPassed; environment_passed=$environmentPassed; windows_process_passed=$processPassed; windows_process_executed=($env:OS -eq 'Windows_NT') }
    if ($OutDir) {
        New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
        [IO.File]::WriteAllText((Join-Path $OutDir 'runner-failure-contract.json'), ($summary | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    }
    Write-Host "C1207_RUNNER_FAILURE_FIXTURES=$fixturePassed/$($fixtures.Count) PASS"
    Write-Host "C1207_PROBE_EXCEPTION_FIXTURES=$probePassed/$($probeFixtures.Count) PASS"
    Write-Host "C1207_RUNNER_ENCODING=$encodingPassed/4 PASS"
    Write-Host "C1207_RUNNER_CHILD_ENVIRONMENT=$environmentPassed/2 PASS"
    if ($env:OS -eq 'Windows_NT') { Write-Host "C1207_RUNNER_FAILURE_PROCESSES=$processPassed/$($processCases.Count) PASS (not FEA validation)" }
} finally {
    [Environment]::SetEnvironmentVariable('PYTHONIOENCODING', $previousIo, 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONUTF8', $previousUtf8, 'Process')
    foreach ($stage in $stages) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
