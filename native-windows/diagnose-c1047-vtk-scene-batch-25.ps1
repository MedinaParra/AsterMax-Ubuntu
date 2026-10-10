param([string]$Dist,[int]$ExpectedParts=25,[int]$CaseTimeoutMs=90000)
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

$env:ASTERMAX_C1047_AUDIT_DIR=$out
$env:ASTERMAX_C1047_EXPECTED_PARTS=$ExpectedParts.ToString()
$env:ASTERMAX_LARGE_ASSEMBLY_PARTS='8'
$env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION='0.04'
$env:ASTERMAX_CAD_TESSELLATION_WORKERS='1'
try {
    $started=(Get-Date).ToUniversalTime()
    $p=Start-Process -FilePath $exe -WorkingDirectory $Dist -ArgumentList @($step,'-US','MM_TON_S_C') -PassThru
    $timedOut=$false
    if(-not $p.WaitForExit($CaseTimeoutMs)){
        $timedOut=$true
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    $reportPath=Join-Path $out 'c1047-scene-batch-report.json'
    $report=$null
    if(Test-Path $reportPath){ $report=Get-Content $reportPath -Raw | ConvertFrom-Json }
    $summary=[ordered]@{
        fixture='25 analytic spheres STEP'
        step_sha256=$stepHash
        expected_parts=$ExpectedParts
        visualization_deflection=0.04
        effective_netgen_workers=1
        timed_out=$timedOut
        process_exit_code=if($timedOut){$null}else{$p.ExitCode}
        report_present=(Test-Path $reportPath)
        report_pass=if($report){[bool]$report.pass}else{$null}
        cad_bodies=if($report){$report.cad_bodies}else{$null}
        controller_errors=if($report){$report.controller_errors}else{$null}
        deferred_camera_adjusts=if($report){$report.deferred_camera_adjusts}else{$null}
        batch_camera_flushes=if($report){$report.batch_camera_flushes}else{$null}
        batch_depth_after_import=if($report){$report.batch_depth_after_import}else{$null}
        camera_adjust_calls_avoided_lower_bound=if($report){$report.camera_adjust_calls_avoided_lower_bound}else{$null}
        elapsed_ms_upper_bound=if($report){$report.elapsed_ms_upper_bound}else{$null}
        started_utc=$started.ToString('o')
        completed_utc=(Get-Date).ToUniversalTime().ToString('o')
        interpretation='DIAGNOSTIC_ONLY: validates camera-work coalescing; not a speedup/FPS benchmark.'
    }
    $summary | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $root 'diagnostic-summary.json') -Encoding UTF8
    $summary | ConvertTo-Json -Depth 6
    if($timedOut -or -not $report -or $report.pass -ne $true){ throw 'C10.47 scene-batch runtime diagnostic failed.' }
}
finally {
    Remove-Item Env:ASTERMAX_C1047_AUDIT_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_C1047_EXPECTED_PARTS -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_PARTS -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_CAD_TESSELLATION_WORKERS -ErrorAction SilentlyContinue
}
