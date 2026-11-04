param(
    [Parameter(Mandatory=$true)][string]$Runner,
    [Parameter(Mandatory=$true)][string]$OutDir,
    [switch]$ExpectOriginalFailure
)
$ErrorActionPreference = 'Stop'
$passed = 0
function Check([bool]$Condition, [string]$Label) {
    if (-not $Condition) { throw ('FAIL: ' + $Label) }
    $script:passed++
    Write-Output ('PASS: ' + $Label)
}
function Read-LiveLog([string]$Path) {
    # Keep the writer open: the reader must share writes on Windows. The default
    # File.ReadAllText reader denies existing writers and creates a test-only lock.
    $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
    $reader=New-Object IO.StreamReader($stream)
    try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
}
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Runner,[ref]$tokens,[ref]$errors)
Check ($errors.Count -eq 0) 'runner parses'
$definition=@($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Copy-Workspace'},$false))
Check ($definition.Count -eq 1) 'one copy function'
Invoke-Expression $definition[0].Extent.Text
$root = Join-Path ([IO.Path]::GetFullPath($OutDir)) ('workspace-test-' + [Guid]::NewGuid().ToString('N'))
$workspace = Join-Path $root 'workspace con espacios [literal]'
$stage = Join-Path $root 'stage'
New-Item -ItemType Directory -Path $workspace,$stage -Force | Out-Null
$utf8 = New-Object Text.UTF8Encoding($false)
$stdoutPath = Join-Path $workspace 'CODE_ASTER_RUNNER_STDOUT.log'
$stderrPath = Join-Path $workspace 'CODE_ASTER_RUNNER_STDERR.log'
$stdout = New-Object IO.StreamWriter($stdoutPath,$false,$utf8)
$stderr = New-Object IO.StreamWriter($stderrPath,$false,$utf8)
$stdout.AutoFlush=$true; $stderr.AutoFlush=$true
try {
    $stdout.Write('caller-out-before|'); $stderr.Write('caller-err-before|')
    [IO.File]::WriteAllText((Join-Path $workspace 'ASTERMAX_SOLVE_STATE.json'),'CANCELLING:revision=5',$utf8)
    [IO.File]::WriteAllText((Join-Path $workspace 'ASTERMAX_SOLVE_STATE.json.0123456789abcdef.tmp'),'state-temp-live',$utf8)
    [IO.File]::WriteAllText((Join-Path $workspace 'ASTERMAX_SOLVE_TRANSACTION.json'),'immutable-transaction',$utf8)
    [IO.File]::WriteAllText((Join-Path $workspace 'study.comm'),'synthetic-test-input',$utf8)
    [IO.File]::WriteAllText((Join-Path $workspace 'study.mail'),'synthetic-test-mesh',$utf8)
    [IO.File]::WriteAllText((Join-Path $workspace 'study.export'),'synthetic-test-export',$utf8)
    $unicodeName = 'archivo-' + [char]0x00F1 + '.txt'
    New-Item -ItemType Directory -Path (Join-Path $workspace 'nested') | Out-Null
    [IO.File]::WriteAllText((Join-Path (Join-Path $workspace 'nested') $unicodeName),'unicode-path-data',$utf8)
    if ($ExpectOriginalFailure) {
        $observed=$false
        try {
            Copy-Workspace $workspace $stage
            # Reproduce a stale stage artifact regardless of platform copy-in behavior.
            [IO.File]::WriteAllText((Join-Path $stage 'CODE_ASTER_RUNNER_STDOUT.log'),'stale-stage-out',$utf8)
            [IO.File]::WriteAllText((Join-Path $stage 'CODE_ASTER_RUNNER_STDERR.log'),'stale-stage-err',$utf8)
            Copy-Workspace $stage $workspace
            $stdout.Write('caller-out-after|'); $stderr.Write('caller-err-after|')
            $observed=((Read-LiveLog $stdoutPath) -ne 'caller-out-before|caller-out-after|' -or (Read-LiveLog $stderrPath) -ne 'caller-err-before|caller-err-after|')
        } catch { $observed=$true; Write-Output ('BASELINE ERROR: ' + $_.Exception.Message) }
        Check $observed 'original rejects live log copy or corrupts caller bytes'
    } else {
        Copy-Workspace $workspace $stage
        Check (-not (Test-Path -LiteralPath (Join-Path $stage 'CODE_ASTER_RUNNER_STDOUT.log'))) 'stdout excluded from stage'
        Check (-not (Test-Path -LiteralPath (Join-Path $stage 'CODE_ASTER_RUNNER_STDERR.log'))) 'stderr excluded from stage'
        Check (-not (Test-Path -LiteralPath (Join-Path $stage 'ASTERMAX_SOLVE_STATE.json'))) 'live state excluded from stage'
        Check (-not (Test-Path -LiteralPath (Join-Path $stage 'ASTERMAX_SOLVE_STATE.json.0123456789abcdef.tmp'))) 'state temporary excluded from stage'
        foreach ($name in @('study.comm','study.mail','study.export','ASTERMAX_SOLVE_TRANSACTION.json')) {
            Check ([IO.File]::ReadAllText((Join-Path $workspace $name)) -eq [IO.File]::ReadAllText((Join-Path $stage $name))) ('input preserved: ' + $name)
        }
        Check ([IO.File]::ReadAllText((Join-Path (Join-Path $stage 'nested') $unicodeName)) -eq 'unicode-path-data') 'nested Unicode file and literal brackets preserved'
        foreach ($name in @('CODE_ASTER_RUNNER_STDOUT.log','CODE_ASTER_RUNNER_STDERR.log','ASTERMAX_SOLVE_STATE.json','ASTERMAX_SOLVE_STATE.json.0123456789abcdef.tmp')) {
            [IO.File]::WriteAllText((Join-Path $stage $name),'stale-stage-copy',$utf8)
        }
        foreach ($name in @('study.mess','study.rmed','astermax-native.stdout.log','astermax-native.stderr.log','astermax-runner-diagnostic.json')) {
            [IO.File]::WriteAllText((Join-Path $stage $name),('synthetic-result-' + $name),$utf8)
        }
        Copy-Workspace $stage $workspace
        $stdout.Write('caller-out-after|'); $stderr.Write('caller-err-after|')
        Check ((Read-LiveLog $stdoutPath) -eq 'caller-out-before|caller-out-after|') 'stdout stays intact and writable'
        Check ((Read-LiveLog $stderrPath) -eq 'caller-err-before|caller-err-after|') 'stderr stays intact and writable'
        Check ([IO.File]::ReadAllText((Join-Path $workspace 'ASTERMAX_SOLVE_STATE.json')) -eq 'CANCELLING:revision=5') 'cancellation state not overwritten'
        Check ([IO.File]::ReadAllText((Join-Path $workspace 'ASTERMAX_SOLVE_STATE.json.0123456789abcdef.tmp')) -eq 'state-temp-live') 'live state temporary not overwritten'
        foreach ($name in @('study.mess','study.rmed','astermax-native.stdout.log','astermax-native.stderr.log','astermax-runner-diagnostic.json')) {
            Check ([IO.File]::ReadAllText((Join-Path $workspace $name)) -eq ('synthetic-result-' + $name)) ('output preserved: ' + $name)
        }
        $caseSource=Join-Path $root 'case-source'; $caseTarget=Join-Path $root 'case-target'
        New-Item -ItemType Directory -Path $caseSource,$caseTarget | Out-Null
        foreach ($name in @('code_aster_runner_stdout.LOG','code_aster_runner_stderr.LOG','astermax_solve_state.JSON','astermax_solve_state.json.UPPER.TMP')) {
            [IO.File]::WriteAllText((Join-Path $caseSource $name),'case',$utf8)
        }
        Copy-Workspace $caseSource $caseTarget
        Check (@(Get-ChildItem -LiteralPath $caseTarget -Force).Count -eq 0) 'reserved names case-insensitive'
        $missingFailed=$false
        try { Copy-Workspace (Join-Path $root 'missing') $stage } catch { $missingFailed=$true }
        Check $missingFailed 'missing source fails closed'
        $blockedSource=Join-Path $root 'blocked-source'; $blockedTarget=Join-Path $root 'blocked-target'
        New-Item -ItemType Directory -Path $blockedSource,$blockedTarget | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $blockedSource 'input-directory') | Out-Null
        [IO.File]::WriteAllText((Join-Path (Join-Path $blockedSource 'input-directory') 'required.txt'),'required-input',$utf8)
        [IO.File]::WriteAllText((Join-Path $blockedTarget 'input-directory'),'blocking-leaf',$utf8)
        $copyFailed=$false
        try { Copy-Workspace $blockedSource $blockedTarget } catch { $copyFailed=$true }
        Check $copyFailed 'unrelated copy error is not swallowed'
    }
    Write-Output ('TOTAL PASS: ' + $passed)
    Write-Output ('PLATFORM: ' + [Environment]::OSVersion.ToString() + '; PowerShell=' + $PSVersionTable.PSVersion.ToString())
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        Write-Output 'WINDOWS_SHARING_SEMANTICS: NOT_RUN; Linux checks cannot validate Windows file locking.'
    }
} finally {
    $stdout.Dispose(); $stderr.Dispose()
    Write-Output ('TEST_WORKSPACE: ' + $root)
}
