param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string[]]$Patches,
    [string]$OutDir = (Join-Path $PWD 'astermax-patch-harness')
)
$ErrorActionPreference='Stop'

function Get-CriticalHashes([string]$TargetRoot)
{
    $relative=@(
        'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs',
        'PrePoMax/Forms/AsterMaxIntegratedResults.cs',
        'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs',
        'PrePoMax/Forms/AsterMaxButtonAudit.cs',
        'PrePoMax/Forms/AsterMaxNativeUi.cs'
    )
    $result=[ordered]@{}
    foreach($rel in $relative)
    {
        $p=Join-Path $TargetRoot $rel
        if(Test-Path $p)
        {
            $result[$rel]=(Get-FileHash $p -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        else
        {
            $result[$rel]=$null
        }
    }
    return $result
}

function Copy-FailureSnapshot([string]$TargetRoot,[string]$Destination)
{
    New-Item -ItemType Directory -Force $Destination | Out-Null
    foreach($rel in @(
        'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs',
        'PrePoMax/Forms/AsterMaxIntegratedResults.cs',
        'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs',
        'PrePoMax/Forms/AsterMaxButtonAudit.cs',
        'PrePoMax/Forms/AsterMaxNativeUi.cs'
    ))
    {
        $src=Join-Path $TargetRoot $rel
        if(Test-Path $src)
        {
            $name=($rel -replace '[\\/]','__')
            Copy-Item $src (Join-Path $Destination $name) -Force
        }
    }
}

New-Item -ItemType Directory -Force $OutDir | Out-Null
$outDirPath=(Resolve-Path $OutDir).Path
$rootPath=(Resolve-Path $Root).Path
$pwsh=(Get-Command pwsh -ErrorAction Stop).Source
$rows=New-Object System.Collections.Generic.List[object]
$failed=$false
$failedPatch=$null
$failureClass=$null

for($i=0;$i -lt $Patches.Count;$i++)
{
    $patch=$Patches[$i]
    $patchPath=Join-Path $PSScriptRoot $patch
    if(-not(Test-Path $patchPath))
    {
        $failed=$true
        $failedPatch=$patch
        $failureClass='PATCH_FILE_MISSING'
        $rows.Add([ordered]@{
            ordinal=$i+1;patch=$patch;status='FAIL';exit_code=-2;
            failure_class=$failureClass;message='Patch file does not exist.'
        })
        break
    }

    $stem=('{0:D2}-{1}' -f ($i+1),([IO.Path]::GetFileNameWithoutExtension($patch)))
    $stdout=Join-Path $outDirPath ($stem+'.stdout.log')
    $stderr=Join-Path $outDirPath ($stem+'.stderr.log')
    $before=Get-CriticalHashes $rootPath
    $started=[DateTime]::UtcNow
    Write-Host ("HARNESS_PATCH_START ordinal={0} patch={1}" -f ($i+1),$patch)

    $proc=Start-Process -FilePath $pwsh -ArgumentList @(
        '-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
        '-File',$patchPath,'-Root',$rootPath
    ) -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

    $finished=[DateTime]::UtcNow
    $after=Get-CriticalHashes $rootPath
    $stderrText=if(Test-Path $stderr){Get-Content $stderr -Raw}else{''}
    $stdoutText=if(Test-Path $stdout){Get-Content $stdout -Raw}else{''}
    $status=if($proc.ExitCode -eq 0){'PASS'}else{'FAIL'}
    $class=$null

    if($status -eq 'FAIL')
    {
        if($stderrText -match 'anchor missing|structural anchor missing')
        {
            $class='ANCHOR_DRIFT'
        }
        elseif($stderrText -match 'ParserError|parse error')
        {
            $class='PATCH_PARSE_ERROR'
        }
        elseif($stderrText -match 'Cannot find path|does not exist')
        {
            $class='TARGET_PATH_MISSING'
        }
        else
        {
            $class='PATCH_RUNTIME_FAILURE'
        }
    }

    $rows.Add([ordered]@{
        ordinal=$i+1
        patch=$patch
        status=$status
        exit_code=$proc.ExitCode
        failure_class=$class
        started_utc=$started.ToString('o')
        finished_utc=$finished.ToString('o')
        duration_ms=[int][Math]::Round(($finished-$started).TotalMilliseconds)
        stdout_file=[IO.Path]::GetFileName($stdout)
        stderr_file=[IO.Path]::GetFileName($stderr)
        stdout_tail=(($stdoutText -split "\r?\n" | Select-Object -Last 20) -join "`n")
        stderr_tail=(($stderrText -split "\r?\n" | Select-Object -Last 40) -join "`n")
        critical_hashes_before=$before
        critical_hashes_after=$after
    })

    Write-Host ("HARNESS_PATCH_END ordinal={0} patch={1} status={2} exit={3}" -f ($i+1),$patch,$status,$proc.ExitCode)
    if($status -eq 'FAIL')
    {
        $failed=$true
        $failedPatch=$patch
        $failureClass=$class
        Copy-FailureSnapshot $rootPath (Join-Path $outDirPath 'failure-snapshot')
        break
    }
}

$report=[ordered]@{
    schema='astermax-patch-harness/v1'
    generated_utc=[DateTime]::UtcNow.ToString('o')
    root=$rootPath
    requested_patch_count=$Patches.Count
    executed_patch_count=$rows.Count
    passed_patch_count=@($rows | Where-Object {$_.status -eq 'PASS'}).Count
    failed=$failed
    failed_patch=$failedPatch
    failure_class=$failureClass
    rows=$rows
}
$reportPath=Join-Path $outDirPath 'patch-chain-harness.json'
$report | ConvertTo-Json -Depth 12 | Set-Content $reportPath -Encoding UTF8

if($failed)
{
    $failure=[ordered]@{
        failed_patch=$failedPatch
        failure_class=$failureClass
        report=$reportPath
        guidance=@(
            'Inspect the failing patch stderr log.',
            'Compare failure-snapshot against the anchor expected by the patch.',
            'Prefer structural/semantic anchors over exact historical method bodies.',
            'Do not continue dependent patches until the failed patch is repaired.'
        )
    }
    $failure | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $outDirPath 'PATCH_FAILURE.json') -Encoding UTF8
    Write-Error "ASTERMAX_PATCH_HARNESS_FAIL patch=$failedPatch class=$failureClass report=$reportPath"
    exit 1
}

Copy-FailureSnapshot $rootPath (Join-Path $outDirPath 'final-snapshot')
Write-Host "ASTERMAX_PATCH_HARNESS_PASS patches=$($rows.Count) report=$reportPath"
exit 0
