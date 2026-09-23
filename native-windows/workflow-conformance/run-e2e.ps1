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

    $inventoryPath=Join-Path $outPath 'timeout-window-thread-inventory.json'
    try {
        $windowProbe=@'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class AsterMaxTimeoutWindowProbe {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")] static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
    [DllImport("user32.dll")] static extern int GetClassName(IntPtr hWnd, StringBuilder text, int maxCount);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hWnd);
    public static string[] ForProcess(int targetPid) {
        var rows=new List<string>();
        EnumWindows((hWnd,lParam) => {
            uint pid; GetWindowThreadProcessId(hWnd,out pid);
            if(pid==(uint)targetPid) {
                var title=new StringBuilder(1024); GetWindowText(hWnd,title,title.Capacity);
                var cls=new StringBuilder(256); GetClassName(hWnd,cls,cls.Capacity);
                rows.Add("0x"+hWnd.ToInt64().ToString("X")+"|visible="+IsWindowVisible(hWnd)+"|class="+cls+"|title="+title);
            }
            return true;
        },IntPtr.Zero);
        return rows.ToArray();
    }
}
'@
        Add-Type -TypeDefinition $windowProbe -ErrorAction SilentlyContinue
        $proc=Get-Process -Id $p.Id -ErrorAction Stop
        $threads=@()
        foreach($thread in $proc.Threads) {
            $waitReason=$null
            try { $waitReason=$thread.WaitReason.ToString() } catch {}
            $threads += [ordered]@{
                id=$thread.Id
                state=$thread.ThreadState.ToString()
                wait_reason=$waitReason
                total_processor_time_ms=$thread.TotalProcessorTime.TotalMilliseconds
            }
        }
        $windows=@()
        try { $windows=[AsterMaxTimeoutWindowProbe]::ForProcess($p.Id) } catch {}
        [ordered]@{
            captured_utc=[DateTime]::UtcNow.ToString('O')
            process_id=$p.Id
            process_name=$proc.ProcessName
            main_window_title=$proc.MainWindowTitle
            responding=$proc.Responding
            handle_count=$proc.HandleCount
            thread_count=$proc.Threads.Count
            threads=$threads
            windows=$windows
        } | ConvertTo-Json -Depth 10 | Set-Content $inventoryPath -Encoding UTF8
    }
    catch {
        [ordered]@{captured_utc=[DateTime]::UtcNow.ToString('O');process_id=$p.Id;error=$_.Exception.ToString()} |
            ConvertTo-Json -Depth 5 | Set-Content $inventoryPath -Encoding UTF8
    }

    $dumpPath=Join-Path $outPath 'timeout-process.dmp'
    $dumpEvidence=Join-Path $outPath 'timeout-process-dump.json'
    try {
        $rundll=Join-Path $env:WINDIR 'System32\rundll32.exe'
        $comsvcs=Join-Path $env:WINDIR 'System32\comsvcs.dll'
        $dumpProc=Start-Process -FilePath $rundll -ArgumentList @("$comsvcs,MiniDump",$p.Id,$dumpPath,'full') -PassThru -Wait
        [ordered]@{
            attempted=$true
            tool='comsvcs.dll MiniDump'
            helper_exit_code=$dumpProc.ExitCode
            dump_present=(Test-Path $dumpPath)
            dump_bytes=$(if(Test-Path $dumpPath){(Get-Item $dumpPath).Length}else{0})
        } | ConvertTo-Json -Depth 5 | Set-Content $dumpEvidence -Encoding UTF8
    }
    catch {
        [ordered]@{attempted=$true;tool='comsvcs.dll MiniDump';dump_present=(Test-Path $dumpPath);error=$_.Exception.ToString()} |
            ConvertTo-Json -Depth 5 | Set-Content $dumpEvidence -Encoding UTF8
    }

    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    try { $p.WaitForExit(10000) | Out-Null } catch {}
}
$exitCode=-1
try { $exitCode=$p.ExitCode } catch {}

# Keep Windows' own crash diagnosis; an abnormal exit must never become PASS.
if($exitCode -ne 0) {
    try {
        $events=@(Get-WinEvent -FilterHashtable @{
            LogName='Application'; StartTime=(Get-Date).AddMinutes(-15)
        } -ErrorAction Stop | Where-Object {
            $_.ProviderName -in @('Application Error','.NET Runtime','Windows Error Reporting')
        } | Select-Object TimeCreated,Id,ProviderName,Message)
        $events | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $outPath 'windows-exit-events.json') -Encoding UTF8
    } catch {
        $_.Exception.ToString() | Set-Content (Join-Path $outPath 'windows-exit-events-error.txt')
    }
}

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
