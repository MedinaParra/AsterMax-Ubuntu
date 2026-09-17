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
Remove-Item $session -Force -ErrorAction SilentlyContinue
$args=@($stepPath,'-US','MM_TON_S_C',"--astermax-c1020-workflow=$outPath")
$p=Start-Process -FilePath $exePath -WorkingDirectory (Split-Path $exePath -Parent) -ArgumentList $args -PassThru
if(-not $p.WaitForExit($TimeoutSeconds*1000)) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    throw "C10.20 workflow conformance timed out after $TimeoutSeconds seconds."
}
if(-not(Test-Path $session)) { throw "C10.20 executable exited without workflow-conformance-session.json. ExitCode=$($p.ExitCode)" }
$data=Get-Content $session -Raw | ConvertFrom-Json
$data | ConvertTo-Json -Depth 20 | Write-Host
if($p.ExitCode -ne 0 -or -not $data.pass) { throw "C10.20 mandatory-stage session failed. ExitCode=$($p.ExitCode)" }
Write-Host 'ASTERMAX_C1020_MANDATORY_STAGE_SESSION=PASS'
