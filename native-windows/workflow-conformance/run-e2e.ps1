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

$env:ASTERMAX_C1020_AUDIT_DIR=$outPath
$args=@($stepPath,'-US','MM_TON_S_C',"--astermax-c1020-workflow=$outPath")
$p=Start-Process -FilePath $exePath -WorkingDirectory (Split-Path $exePath -Parent) -ArgumentList $args -PassThru
$timedOut=$false
if(-not $p.WaitForExit($TimeoutSeconds*1000)) {
    $timedOut=$true
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    try { $p.WaitForExit(10000) | Out-Null } catch {}
}
$exitCode=-1
try { $exitCode=$p.ExitCode } catch {}

# Preserve the exact native meshing workspace after the GUI process exits.
# This captures NetGen inputs/outputs without fabricating or modifying solver data.
$meshPreflight=Join-Path $outPath 'mesh-command-preflight.json'
if(Test-Path $meshPreflight) {
    try {
        $meshInfo=Get-Content $meshPreflight -Raw | ConvertFrom-Json
        $meshWork=[string]$meshInfo.work_directory
        if(-not [String]::IsNullOrWhiteSpace($meshWork) -and (Test-Path $meshWork)) {
            $meshEvidence=Join-Path $outPath 'mesh-workdir'
            New-Item -ItemType Directory -Force $meshEvidence | Out-Null
            Copy-Item (Join-Path $meshWork '*') $meshEvidence -Recurse -Force -ErrorAction Continue
            $entries=@()
            Get-ChildItem $meshEvidence -Recurse -File | ForEach-Object {
                $entries += [ordered]@{
                    relative_path=$_.FullName.Substring($meshEvidence.Length).TrimStart('\')
                    bytes=$_.Length
                    sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                }
            }
            [ordered]@{
                source_work_directory=$meshWork
                captured_utc=[DateTime]::UtcNow.ToString('o')
                files=$entries
            } | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $outPath 'mesh-workdir-manifest.json') -Encoding UTF8
        }
    } catch {
        Write-Warning "Could not preserve meshing workspace: $($_.Exception.Message)"
    }
}
if(-not(Test-Path $session)) {
    [ordered]@{
        release='C10.20.8';pass=$false;partial=$true;
        error=($(if($timedOut){"Workflow timed out after $TimeoutSeconds seconds."}else{"Executable exited without workflow session."}));
        rows=@();process_exit_code=$exitCode;historical_pending_closed=$false
    } | ConvertTo-Json -Depth 20 | Set-Content $session -Encoding UTF8
}

$sessionData=Get-Content $session -Raw | ConvertFrom-Json
$sessionData | Add-Member -NotePropertyName process_exit_code -NotePropertyValue $exitCode -Force
if($timedOut) {
    $sessionData | Add-Member -NotePropertyName pass -NotePropertyValue $false -Force
    $sessionData | Add-Member -NotePropertyName partial -NotePropertyValue $true -Force
    $sessionData | Add-Member -NotePropertyName error -NotePropertyValue "Workflow timed out after $TimeoutSeconds seconds." -Force
}
$sessionData | ConvertTo-Json -Depth 60 | Set-Content $session -Encoding UTF8

$builder=Join-Path $PSScriptRoot 'build-report.py'
$contract=Join-Path $PSScriptRoot 'workflow-contract.json'
& python $builder --contract $contract --session $session --outdir $outPath
if($LASTEXITCODE -ne 0 -or -not(Test-Path $report)) { throw 'C10.20 report generation failed.' }
$data=Get-Content $report -Raw | ConvertFrom-Json
$data | ConvertTo-Json -Depth 30 | Write-Host
$mandatoryFailures=[int]$data.summary.mandatory_failures
if(-not $data.summary.release_gate_pass){ throw 'Workflow incomplete or failed; see session and mandatory-stage evidence.' }
if($mandatoryFailures -gt 0) { throw "C10.20 has $mandatoryFailures mandatory stage FAIL result(s)." }
if($timedOut) { throw "C10.20.8 workflow conformance timed out after $TimeoutSeconds seconds; report was preserved." }
if($exitCode -ne 0) { throw "C10.20.8 native audit process failed before a clean completion. ExitCode=$exitCode" }
Write-Host "ASTERMAX_C1020_MANDATORY_PASS=$($data.summary.mandatory_pass)"
Write-Host "ASTERMAX_C1020_MANDATORY_NOT_EXERCISED=$($data.summary.mandatory_not_exercised)"
Write-Host "ASTERMAX_C1020_CLOSURE_CANDIDATE=$($data.summary.closure_candidate)"
