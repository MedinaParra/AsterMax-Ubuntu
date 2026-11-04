param([string]$Original, [string]$Patched, [string]$OutDir)
$ErrorActionPreference = 'Stop'
$script:checks = 0
function Check([bool]$Ok, [string]$Message) {
    if (-not $Ok) { throw $Message }
    $script:checks++
    Write-Host ('PASS ' + $Message)
}
function Import-Copy([string]$Path) {
    $tokens=$null; $errors=$null
    $ast=[Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
    $func=@($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Copy-Workspace'},$false))
    Check ($func.Count -eq 1) ('one parsed Copy-Workspace function in ' + (Split-Path $Path -Leaf))
    return $func[0].Extent.Text
}
New-Item -ItemType Directory -Path $OutDir | Out-Null
$originalCode = Import-Copy $Original
$patchedCode = Import-Copy $Patched
foreach ($kind in @('original','patched')) {
    $root=Join-Path $OutDir $kind
    $work=Join-Path $root 'workspace'
    $stage=Join-Path $root 'stage'
    New-Item -ItemType Directory -Path $work,$stage | Out-Null
    Invoke-Expression $(if ($kind -eq 'original') {$originalCode} else {$patchedCode})
    $logPath=Join-Path $work 'CODE_ASTER_RUNNER_STDERR.log'
    $writer=[IO.StreamWriter]::new($logPath,$false,[Text.UTF8Encoding]::new($false))
    $writer.AutoFlush=$true
    try {
        $writer.Write('live-before')
        [IO.File]::WriteAllText((Join-Path $stage 'CODE_ASTER_RUNNER_STDERR.log'),'stale-stage')
        [IO.File]::WriteAllText((Join-Path $work 'ASTERMAX_SOLVE_STATE.json'),'CANCELLING:2')
        [IO.File]::WriteAllText((Join-Path $stage 'ASTERMAX_SOLVE_STATE.json'),'RUNNING:1')
        $threw=$false; $errorMessage=$null
        try { Copy-Workspace $stage $work } catch { $threw=$true; $errorMessage=$_.Exception.Message }
        $writer.Write(':live-after')
    } finally { $writer.Dispose() }
    $contents=[IO.File]::ReadAllText($logPath)
    $state=[IO.File]::ReadAllText((Join-Path $work 'ASTERMAX_SOLVE_STATE.json'))
    if ($kind -eq 'original') {
        Check ($threw -or $contents -ne 'live-before:live-after' -or $state -ne 'CANCELLING:2') 'original implementation demonstrates copy-back conflict or corruption'
        Write-Output ('ORIGINAL_OUTCOME=' + (@{threw=$threw; error=$errorMessage; log=$contents; state=$state} | ConvertTo-Json -Compress))
    } else {
        Check (-not $threw) 'patched copy-back does not fail on parent-owned log'
        Check ($contents -ceq 'live-before:live-after') 'parent log remains exact and can continue writing'
        Check ($state -ceq 'CANCELLING:2') 'parent cancelling state is not rolled back'
    }
}
Invoke-Expression $patchedCode
$source=Join-Path $OutDir 'precise-input'
$target=Join-Path $OutDir 'precise-output'
New-Item -ItemType Directory -Path $source,$target | Out-Null
$reserved=@('code_aster_runner_stdout.LOG','CoDe_AsTeR_RuNnEr_StDeRr.LoG','aStErMaX_sOlVe_StAtE.JsOn','ASTERMAX_SOLVE_STATE.json.0123456789abcdef.tmp')
$allowed=@('astermax-native.stdout.log','astermax-native.stderr.log','ASTERMAX_SOLVE_TRANSACTION.json','astermax-runner-diagnostic.json','model.comm','model.mail','model.mess','model.rmed','CODE_ASTER_RUNNER_STDERR.log.bak','ASTERMAX_SOLVE_STATE.json.backup','résultat [1].txt')
foreach ($name in ($reserved + $allowed)) { [IO.File]::WriteAllText((Join-Path $source $name),$name) }
$nested=Join-Path $source 'subfolder [literal]'
[IO.Directory]::CreateDirectory($nested) | Out-Null
[IO.File]::WriteAllText((Join-Path $nested 'CODE_ASTER_RUNNER_STDERR.log'),'nested-owned-by-solver')
Copy-Workspace $source $target
foreach ($name in $reserved) { Check (-not (Test-Path -LiteralPath (Join-Path $target $name))) ('excluded reserved name case-insensitively: '+$name) }
foreach ($name in $allowed) { Check ([IO.File]::ReadAllText((Join-Path $target $name)) -ceq $name) ('preserved exact content: '+$name) }
Check ([IO.File]::ReadAllText((Join-Path (Join-Path $target 'subfolder [literal]') 'CODE_ASTER_RUNNER_STDERR.log')) -ceq 'nested-owned-by-solver') 'nested homonymous log is preserved'
$threw=$false
try { Copy-Workspace (Join-Path $OutDir 'does-not-exist') $target } catch { $threw=$true }
Check $threw 'missing input directory fails closed'
Write-Output ('PASS ' + $script:checks + ' assertions on PowerShell ' + $PSVersionTable.PSVersion + ' / ' + [Environment]::OSVersion)
Write-Output ('TEST_PLATFORM=' + [Environment]::OSVersion + '; PowerShell=' + $PSVersionTable.PSVersion)
Write-Output 'Real Code_Aster execution NOT RUN; synthetic file-ownership regression only.'
