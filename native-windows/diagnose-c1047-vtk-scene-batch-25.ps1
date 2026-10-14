param([string]$Dist,[int]$ExpectedParts=25,[int]$CaseTimeoutMs=90000,[int]$ShutdownTimeoutMs=10000)
$ErrorActionPreference='Stop'
$Dist=(Resolve-Path $Dist).Path
$root=Join-Path $Dist 'Audit/C10.47/diagnostic-25'
New-Item -ItemType Directory -Force $root | Out-Null
$step=Join-Path $root 'diagnostic-25-spheres.step'
$python=Join-Path $Dist 'AsterMaxRuntime/Python/python.exe'
$exe=Join-Path $Dist 'AsterMax Mechanical.exe'
if(!(Test-Path $python)){throw 'C10.47 packaged Python missing.'}
if(!(Test-Path $exe)){throw 'C10.47 AsterMax Mechanical.exe missing.'}

$code="import gmsh; gmsh.initialize(); gmsh.model.add('C1047_25'); [gmsh.model.occ.addSphere((i%5)*16,(i//5)*16,0,5) for i in range($ExpectedParts)]; gmsh.model.occ.synchronize(); gmsh.write(r'$step'); gmsh.finalize()"
& $python -c $code
if($LASTEXITCODE -ne 0 -or !(Test-Path $step)){throw 'C10.47 STEP fixture generation failed.'}
$stepHash=(Get-FileHash $step -Algorithm SHA256).Hash.ToLowerInvariant()
$out=Join-Path $root 'scene-batch'
New-Item -ItemType Directory -Force $out | Out-Null
$reportPath=Join-Path $out 'c1047-scene-batch-report.json'
Remove-Item $reportPath -Force -ErrorAction SilentlyContinue

$env:ASTERMAX_C1047_AUDIT_DIR=$out
$env:ASTERMAX_C1047_EXPECTED_PARTS=$ExpectedParts.ToString()
$env:ASTERMAX_LARGE_ASSEMBLY_PARTS='8'
$env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION='0.04'
$env:ASTERMAX_CAD_TESSELLATION_WORKERS='1'
try {
    $started=(Get-Date).ToUniversalTime()
    $wall=[System.Diagnostics.Stopwatch]::StartNew()
    $p=Start-Process -FilePath $exe -WorkingDirectory $Dist -ArgumentList @($step,'-US','MM_TON_S_C') -PassThru

    # The optimization is ready when the in-app audit report exists, not when
    # the WinForms process has completed all native/window teardown. Poll the
    # report explicitly so scene correctness and shutdown lifecycle are separate.
    $report=$null
    $processExitedBeforeReport=$false
    while($wall.ElapsedMilliseconds -lt $CaseTimeoutMs){
        if(Test-Path $reportPath){
            try {
                $report=Get-Content $reportPath -Raw | ConvertFrom-Json
                if($report -ne $null){ break }
            }
            catch {
                # Writer may still be replacing/flushing the JSON; retry briefly.
            }
        }
        if($p.HasExited){
            $processExitedBeforeReport=$true
            break
        }
        Start-Sleep -Milliseconds 100
        $p.Refresh()
    }
    $auditReadyMs=$wall.ElapsedMilliseconds
    $auditTimedOut=($report -eq $null -and -not $processExitedBeforeReport)

    # Once the scene report is available, allow a bounded graceful WinForms/VTK
    # shutdown. A shutdown timeout is recorded independently and cleaned up, but
    # it does not rewrite a valid scene-batch result into a false performance FAIL.
    $gracefulShutdown=$false
    $shutdownTimedOut=$false
    $processExitCode=$null
    if(-not $p.HasExited){
        if($p.WaitForExit($ShutdownTimeoutMs)){
            $gracefulShutdown=$true
            $processExitCode=$p.ExitCode
        }
        else{
            $shutdownTimedOut=$true
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            try { $p.WaitForExit(5000) | Out-Null } catch { }
        }
    }
    else{
        $gracefulShutdown=$true
        $processExitCode=$p.ExitCode
    }
    $wall.Stop()

    # If report appeared after the last polling read but before teardown, consume
    # it now. This preserves evidence while still distinguishing a real audit timeout.
    if($report -eq $null -and (Test-Path $reportPath)){
        try { $report=Get-Content $reportPath -Raw | ConvertFrom-Json } catch { }
    }

    $scenePass=($report -ne $null -and $report.pass -eq $true)
    $summary=[ordered]@{
        fixture='25 analytic spheres STEP'
        step_sha256=$stepHash
        expected_parts=$ExpectedParts
        visualization_deflection=0.04
        effective_netgen_workers=1
        audit_report_timeout=$auditTimedOut
        process_exited_before_report=$processExitedBeforeReport
        audit_ready_wall_ms=$auditReadyMs
        graceful_shutdown=$gracefulShutdown
        shutdown_timeout=$shutdownTimedOut
        process_exit_code=$processExitCode
        report_present=($report -ne $null)
        report_pass=if($report){[bool]$report.pass}else{$null}
        scene_batch_status=if($scenePass){'PASS'}elseif($report){'FAIL'}else{'NOT_RUN'}
        shutdown_status=if($gracefulShutdown){'PASS'}elseif($shutdownTimedOut){'FAIL'}else{'NOT_RUN'}
        cad_bodies=if($report){$report.cad_bodies}else{$null}
        controller_errors=if($report){$report.controller_errors}else{$null}
        deferred_camera_adjusts=if($report){$report.deferred_camera_adjusts}else{$null}
        batch_camera_flushes=if($report){$report.batch_camera_flushes}else{$null}
        batch_depth_after_import=if($report){$report.batch_depth_after_import}else{$null}
        camera_adjust_calls_avoided_lower_bound=if($report){$report.camera_adjust_calls_avoided_lower_bound}else{$null}
        elapsed_ms_upper_bound=if($report){$report.elapsed_ms_upper_bound}else{$null}
        total_harness_wall_ms=$wall.ElapsedMilliseconds
        started_utc=$started.ToString('o')
        completed_utc=(Get-Date).ToUniversalTime().ToString('o')
        interpretation='DIAGNOSTIC_ONLY: scene-batch counters validate redundant camera-work removal; audit/shutdown timing is not an opening/FPS benchmark.'
    }
    $summary | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $root 'diagnostic-summary.json') -Encoding UTF8
    $summary | ConvertTo-Json -Depth 6

    if(-not $scenePass){ throw 'C10.47 scene-batch runtime diagnostic failed.' }
    if($shutdownTimedOut){ Write-Warning 'C10.47 scene batch PASS but graceful shutdown timed out; recorded as independent lifecycle regression.' }
}
finally {
    Remove-Item Env:ASTERMAX_C1047_AUDIT_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_C1047_EXPECTED_PARTS -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_PARTS -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_CAD_TESSELLATION_WORKERS -ErrorAction SilentlyContinue
}
