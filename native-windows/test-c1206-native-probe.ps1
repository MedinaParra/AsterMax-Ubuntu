# Contract regression tests use deliberately labelled command stubs only.
# A PASS here is NOT evidence of Code_Aster execution or FEA correctness.
# The release workflow must also run test-c1011-native-windows.ps1 with the
# genuine provider runtime and validate the resulting numerical MED fields.
$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'runtime/CodeAster/astermax-codeaster-runner.ps1'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($runner, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
$helper = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-CodeAsterProbeEvidence' }, $true)
if (-not $helper) { throw 'Probe evidence helper is missing.' }
. ([scriptblock]::Create($helper.Extent.Text))

$header = '-- CODE_ASTER -- VERSION : 16.9.0 (contract test fixture)'
$normal = $header + "`r`n<I> <FIN> ARRET NORMAL DANS FIN`r`n"
$cases = @(
    @{ Name='normal-ascii'; Mess=$normal; Out=''; Err=''; Code=0; Ready=$true },
    @{ Name='normal-french-accent'; Mess=($header + "`r`nArr" + [char]0xEA + "t normal dans FIN."); Out=''; Err=''; Code=0; Ready=$true },
    @{ Name='normal-legacy-oem'; Mess=($header + "`r`nArr" + [char]0xFFFD + "t normal dans FIN."); Out=''; Err=''; Code=0; Ready=$true },
    @{ Name='normal-exit-in-mess'; Mess=($header + "`nEXECUTION_CODE_ASTER_EXIT_12345=0"); Out=''; Err=''; Code=0; Ready=$true },
    @{ Name='normal-exit-in-stdout'; Mess=$header; Out='EXECUTION_CODE_ASTER_EXIT_12345=0'; Err=''; Code=0; Ready=$true },
    @{ Name='alarm-with-normal-stop'; Mess=($normal + "`n<A> An informational alarm occurred."); Out=''; Err=''; Code=0; Ready=$true },
    @{ Name='empty-mess'; Mess=''; Out='EXIT_CODE=0'; Err=''; Code=0; Ready=$false },
    @{ Name='missing-mess'; Mess=$null; Out=$normal; Err=''; Code=0; Ready=$false },
    @{ Name='no-solver-identity'; Mess='ARRET NORMAL'; Out=''; Err=''; Code=0; Ready=$false },
    @{ Name='exit-marker-is-not-identity'; Mess='EXECUTION_CODE_ASTER_EXIT_12345=0'; Out=''; Err=''; Code=0; Ready=$false },
    @{ Name='no-normal-stop'; Mess=($header + "`nStarting solver"); Out=''; Err=''; Code=0; Ready=$false },
    @{ Name='fatal-before-normal'; Mess=($header + "`n<F> <SUPERVIS> failed`nARRET NORMAL"); Out=''; Err=''; Code=0; Ready=$false },
    @{ Name='fatal-after-normal'; Mess=($normal + "`n! <F> <SUPERVIS> failed !"); Out=''; Err=''; Code=0; Ready=$false },
    @{ Name='french-fatal'; Mess=($normal + "`nERREUR_FATALE during cleanup"); Out=''; Err=''; Code=0; Ready=$false },
    @{ Name='traceback-in-stderr'; Mess=$normal; Out=''; Err='Traceback (most recent call last):'; Code=0; Ready=$false },
    @{ Name='abnormal-abort'; Mess=$normal; Out='Code_Aster run ended, diagnostic : _ABNORMAL_ABORT'; Err=''; Code=0; Ready=$false },
    @{ Name='nonzero-exit-marker'; Mess=$normal; Out='EXECUTION_CODE_ASTER_EXIT_12345=4'; Err=''; Code=0; Ready=$false },
    @{ Name='invalid-exit-marker'; Mess=$normal; Out='EXIT_CODE=unknown'; Err=''; Code=0; Ready=$false },
    @{ Name='nonzero-process'; Mess=$normal; Out=''; Err=''; Code=7; Ready=$false }
)

$evidencePassed = 0
foreach ($case in $cases) {
    $evidence = Get-CodeAsterProbeEvidence $case.Mess $case.Out $case.Err
    $ready = ($case.Code -eq 0 -and -not [string]::IsNullOrWhiteSpace($case.Mess) -and $evidence.Ready)
    if ($ready -ne $case.Ready) { throw "Probe evidence contract failed: $($case.Name), actual=$ready expected=$($case.Ready)" }
    if ($case.Ready -and (-not $evidence.IdentityVerified -or -not $evidence.NormalStop)) { throw "Missing success evidence: $($case.Name)" }
    $evidencePassed++
    Write-Host "PASS probe evidence fixture: $($case.Name) (contract only; not solver evidence)"
}
Write-Host "C1206_NATIVE_PROBE_EVIDENCE_CONTRACT=$evidencePassed/$($cases.Count) PASS"

if ($env:OS -ne 'Windows_NT') {
    Write-Host 'C1206_NATIVE_PROBE_STUB_PROCESSES=NOT_RUN (Windows only; evidence fixtures above are platform independent)'
    exit 0
}

$root = Join-Path ([IO.Path]::GetTempPath()) ('astermax probe contract stubs ' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $root | Out-Null
$powershell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$processPassed = 0
try {
    foreach ($case in $cases) {
        $directory = Join-Path $root $case.Name
        New-Item -ItemType Directory $directory | Out-Null
        $data = Join-Path $directory 'contract-fixture.json'
        $case | ConvertTo-Json | Set-Content -LiteralPath $data -Encoding UTF8
        $stub = Join-Path $directory 'contract-stub.ps1'
        @'
# Deliberate process stub for the AsterMax readiness contract. Not Code_Aster.
param([string]$Fixture)
$data = Get-Content -LiteralPath $Fixture -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -ne $data.Mess) {
    [IO.File]::WriteAllText((Join-Path (Get-Location).Path 'probe.mess'), [string]$data.Mess, (New-Object Text.UTF8Encoding($false)))
}
if ($data.Out) { [Console]::Out.WriteLine([string]$data.Out) }
if ($data.Err) { [Console]::Error.WriteLine([string]$data.Err) }
exit ([int]$data.Code)
'@ | Set-Content -LiteralPath $stub -Encoding UTF8
        $backend = Join-Path $directory 'contract-stub.cmd'
        @(
            '@echo off',
            'rem Contract test stub. This is not a solver.',
            '"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0contract-stub.ps1" "%~dp0contract-fixture.json"',
            'exit /b %errorlevel%'
        ) | Set-Content -LiteralPath $backend -Encoding ASCII
        $process = New-Object Diagnostics.Process
        $process.StartInfo.FileName = $powershell
        $process.StartInfo.Arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $runner + '" probe'
        $process.StartInfo.UseShellExecute = $false
        $process.StartInfo.CreateNoWindow = $true
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        $process.StartInfo.EnvironmentVariables['ASTERMAX_WINDOWS_CODE_ASTER_COMMAND'] = $backend
        try {
            if (-not $process.Start()) { throw 'Could not start the probe contract process.' }
            $stdout = $process.StandardOutput.ReadToEndAsync()
            $stderr = $process.StandardError.ReadToEndAsync()
            if (-not $process.WaitForExit(30000)) {
                & (Join-Path $env:SystemRoot 'System32/taskkill.exe') /PID $process.Id /T /F 2>&1 | Out-Null
                throw "Probe contract process timed out: $($case.Name)"
            }
            $code = $process.ExitCode
            $text = $stdout.Result
            $errorText = $stderr.Result
        } finally { $process.Dispose() }
        try { $probe = $text | ConvertFrom-Json } catch { throw "Invalid probe JSON for $($case.Name): $text $errorText" }
        if ([bool]$probe.ready -ne $case.Ready -or (($code -eq 0) -ne $case.Ready)) {
            throw "Probe contract accepted/rejected the wrong process: $($case.Name), exit=$code, output=$text, stderr=$errorText"
        }
        if ($probe.transport -ne 'WINDOWS_NATIVE' -or $probe.wsl_required -ne $false -or $probe.synthetic_results_allowed -ne $false) {
            throw "Native probe contract metadata changed: $($case.Name)"
        }
        if ($case.Ready -and ($probe.solver_probe_identity_verified -ne $true -or $probe.solver_probe_normal_stop -ne $true)) {
            throw "Successful probe is missing its identity/normal-stop evidence: $($case.Name)"
        }
        if (-not $case.Ready -and [string]::IsNullOrWhiteSpace([string]$probe.message)) {
            throw "Rejected probe has no actionable diagnostic: $($case.Name)"
        }
        $processPassed++
        Write-Host "PASS native probe process: $($case.Name) (command stub; not solver evidence)"
    }
    Write-Host "C1206_NATIVE_PROBE_STUB_PROCESSES=$processPassed/$($cases.Count) PASS (not FEA validation)"
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
