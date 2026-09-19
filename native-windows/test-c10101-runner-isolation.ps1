# Filesystem and process regression tests. No solver is substituted or FEA generated.
$ErrorActionPreference='Stop'
$runner=Join-Path $PSScriptRoot 'runtime/CodeAster/astermax-codeaster-runner.ps1'
$tokens=$null; $parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($runner,[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count){throw ($parseErrors | Out-String)}
# Load the actual functions without launching Code_Aster or the script entrypoint.
foreach($fn in $ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)) {
    . ([scriptblock]::Create($fn.Extent.Text))
}
$root=Join-Path ([IO.Path]::GetTempPath()) ('astermax-regression-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $root | Out-Null
$checks=0
function Assert-True($Value,[string]$Name) {
    if(-not $Value){throw "FAIL: $Name"}
    $script:checks++; Write-Host "PASS: $Name"
}
function Assert-Rejected([scriptblock]$Action,[string]$Name) {
    $rejected=$false
    try { & $Action | Out-Null } catch { $rejected=$true }
    Assert-True $rejected $Name
}
try {
    $source=Join-Path $root 'source'; $stage=Join-Path $root 'stage'
    New-Item -ItemType Directory $source,$stage | Out-Null
    $export="F comm ./case.comm D 1`nF mail ./case.mail D 20`nF mess ./case.mess R 6`nF rmed ./case.rmed R 81"
    $records=@(Get-ExportFiles $export)
    Assert-True ($records.Count -eq 4) 'parse native exported file contract'
    foreach($name in @('case.comm','case.mail','case.mess','case.rmed','unrelated.rmed')) {
        [IO.File]::WriteAllText((Join-Path $source $name),'INVALID TEST INPUT - NOT FEA OUTPUT')
    }
    Initialize-ExportStage $records $source $stage
    Assert-True ((Test-Path (Join-Path $stage 'case.comm')) -and (Test-Path (Join-Path $stage 'case.mail'))) 'copy declared inputs'
    Assert-True (@(Get-ChildItem $stage).Count -eq 2) 'exclude recent old outputs and unrelated files'
    Assert-Rejected { Confirm-ExportOutputs $records $stage } 'reject absent exact outputs'
    [IO.File]::WriteAllText((Join-Path $stage 'unrelated.mess'),'INVALID NEGATIVE TEST')
    [IO.File]::WriteAllText((Join-Path $stage 'unrelated.rmed'),'INVALID NEGATIVE TEST')
    Assert-Rejected { Confirm-ExportOutputs $records $stage } 'unrelated fresh files cannot satisfy contract'
    [IO.File]::WriteAllText((Join-Path $stage 'case.mess'),'')
    Assert-Rejected { Confirm-ExportOutputs $records $stage } 'reject empty declared output'
    Assert-Rejected { Get-ExportFiles ($export.Replace('./case.rmed','../case.rmed')) } 'reject parent traversal'
    Assert-Rejected { Get-ExportFiles ($export.Replace('./case.rmed','C:/case.rmed')) } 'reject absolute path'
    Assert-Rejected { Get-ExportFiles ($export.Replace('./case.rmed','./case.comm')) } 'reject input output collision'
    Assert-Rejected { Get-ExportFiles ($export.Replace(' R 81',' DR 81')) } 'reject unsupported update record'
    Assert-Rejected { Get-ExportFiles ($export.Replace('F rmed','F resu')) } 'require declared MED output'
    $normalized=Convert-ToWindowsExport ($export.Replace('./','/analysis/'))
    Assert-True (@(Get-ExportFiles $normalized).Count -eq 4) 'accept historical analysis prefix after normalization'

    # Exercise actual concurrent pipe reads with a real child process, no solver mock.
    $child=Join-Path $root 'pipe-child.ps1'
    [IO.File]::WriteAllText($child, '[Console]::Error.Write(("e" * 200000)); [Console]::Out.Write("pipe-complete")')
    $hostExe=Join-Path $PSHOME $(if($env:OS -eq 'Windows_NT'){ 'powershell.exe' }else{ 'pwsh' })
    if(-not(Test-Path $hostExe)){ $hostExe=Join-Path $PSHOME 'pwsh.exe' }
    $result=Invoke-NativeProcess $hostExe ('-NoProfile -File "'+$child+'"') $root 10000
    Assert-True ($result.ExitCode -eq 0 -and $result.Stdout -eq 'pipe-complete' -and $result.Stderr.Length -eq 200000) 'drain saturated stderr concurrently'
    if($env:OS -eq 'Windows_NT') {
        [IO.File]::WriteAllText($child, '[Console]::Out.WriteLine("timeout-diagnostic"); Start-Sleep -Seconds 20')
        Assert-Rejected { Invoke-NativeProcess $hostExe ('-NoProfile -File "'+$child+'"') $root 2000 } 'timeout terminates child'
        Assert-True ((Get-Content (Join-Path $root 'NATIVE_STDOUT.log') -Raw).Contains('timeout-diagnostic')) 'retain timeout process diagnostic'
    }
    Write-Host "CHECKS_PASSED=$checks; SOLVER_EXECUTED=false"
}
finally { Remove-Item -LiteralPath $root -Recurse -Force }
