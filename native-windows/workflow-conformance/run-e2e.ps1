param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [Parameter(Mandatory=$true)][string]$Step,
    [Parameter(Mandatory=$true)][string]$OutDir,
    [int]$TimeoutSeconds=600
)
$ErrorActionPreference='Stop'
$exePath=(Resolve-Path $Exe).Path
$stepPath=(Resolve-Path $Step).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
$outPath=(Resolve-Path $OutDir).Path
$session=Join-Path $outPath 'workflow-conformance-session.json'
$report=Join-Path $outPath 'workflow-conformance-report.json'
Remove-Item $session,$report -Force -ErrorAction SilentlyContinue

$args=@($stepPath,'-US','MM_TON_S_C',"--astermax-c1020-workflow=$outPath")
$p=Start-Process -FilePath $exePath -WorkingDirectory (Split-Path $exePath -Parent) -ArgumentList $args -PassThru
if(-not $p.WaitForExit($TimeoutSeconds*1000)) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    throw "C10.20 workflow conformance timed out after $TimeoutSeconds seconds."
}
if(-not(Test-Path $session)) { throw "C10.20 executable exited without workflow-conformance-session.json. ExitCode=$($p.ExitCode)" }

$builder=Join-Path $PSScriptRoot 'build-report.py'
$contract=Join-Path $PSScriptRoot 'workflow-contract.json'
& python $builder --contract $contract --session $session --outdir $outPath
if($LASTEXITCODE -ne 0 -or -not(Test-Path $report)) { throw 'C10.20 report generation failed.' }
$data=Get-Content $report -Raw | ConvertFrom-Json
$data | ConvertTo-Json -Depth 30 | Write-Host
$mandatoryFailures=[int]$data.summary.mandatory_failures
if($mandatoryFailures -gt 0) { throw "C10.20 has $mandatoryFailures mandatory stage FAIL result(s)." }
if($p.ExitCode -ne 0) { throw "C10.20 native audit process failed before a clean completion. ExitCode=$($p.ExitCode)" }
Write-Host "ASTERMAX_C1020_MANDATORY_PASS=$($data.summary.mandatory_pass)"
Write-Host "ASTERMAX_C1020_MANDATORY_NOT_EXERCISED=$($data.summary.mandatory_not_exercised)"
Write-Host "ASTERMAX_C1020_CLOSURE_CANDIDATE=$($data.summary.closure_candidate)"
