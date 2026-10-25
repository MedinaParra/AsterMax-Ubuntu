param([string]$Dist,[int]$ExpectedParts=25,[int]$CaseTimeoutMs=90000,[int]$ShutdownTimeoutMs=10000)
$ErrorActionPreference='Stop'
$Dist=(Resolve-Path $Dist).Path
$root=Join-Path $Dist 'Audit/C10.49/diagnostic-25'
New-Item -ItemType Directory -Force $root | Out-Null
$step=Join-Path $root 'diagnostic-25-spheres.step'
$python=Join-Path $Dist 'AsterMaxRuntime/Python/python.exe'
$exe=Join-Path $Dist 'AsterMax Mechanical.exe'
if(!(Test-Path $python)){throw 'C10.49 packaged Python missing.'}
if(!(Test-Path $exe)){throw 'C10.49 AsterMax Mechanical.exe missing.'}
$code="import gmsh; gmsh.initialize(); gmsh.model.add('C1049_25'); [gmsh.model.occ.addSphere((i%5)*16,(i//5)*16,0,5) for i in range($ExpectedParts)]; gmsh.model.occ.synchronize(); gmsh.write(r'$step'); gmsh.finalize()"
& $python -c $code
if($LASTEXITCODE -ne 0 -or !(Test-Path $step)){throw 'C10.49 STEP fixture generation failed.'}
$stepHash=(Get-FileHash $step -Algorithm SHA256).Hash.ToLowerInvariant()
$out=Join-Path $root 'telemetry'
New-Item -ItemType Directory -Force $out | Out-Null
$reportPath=Join-Path $out 'c1049-import-telemetry-report.json'
Remove-Item $reportPath -Force -ErrorAction SilentlyContinue
$env:ASTERMAX_C1049_AUDIT_DIR=$out
$env:ASTERMAX_C1049_EXPECTED_PARTS=$ExpectedParts.ToString()
$env:ASTERMAX_LARGE_ASSEMBLY_PARTS='8'
$env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION='0.04'
$env:ASTERMAX_CAD_TESSELLATION_WORKERS='1'
try {
  $wall=[System.Diagnostics.Stopwatch]::StartNew()
  $p=Start-Process -FilePath $exe -WorkingDirectory $Dist -ArgumentList @($step,'-US','MM_TON_S_C') -PassThru
  $report=$null
  while($wall.ElapsedMilliseconds -lt $CaseTimeoutMs){
    if(Test-Path $reportPath){try{$report=Get-Content $reportPath -Raw|ConvertFrom-Json;if($report){break}}catch{}}
    if($p.HasExited){break}
    Start-Sleep -Milliseconds 100
    $p.Refresh()
  }
  $auditReadyMs=$wall.ElapsedMilliseconds
  $auditTimedOut=($report -eq $null -and -not $p.HasExited)
  $graceful=$false;$shutdownTimedOut=$false;$exitCode=$null
  if(-not $p.HasExited){
    if($p.WaitForExit($ShutdownTimeoutMs)){$graceful=$true;$exitCode=$p.ExitCode}
    else{$shutdownTimedOut=$true;Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue;try{$p.WaitForExit(5000)|Out-Null}catch{}}
  }else{$graceful=$true;$exitCode=$p.ExitCode}
  $wall.Stop()
  if($report -eq $null -and (Test-Path $reportPath)){try{$report=Get-Content $reportPath -Raw|ConvertFrom-Json}catch{}}
  $pass=($report -ne $null -and $report.pass -eq $true)
  $summary=[ordered]@{
    fixture='25 analytic spheres STEP';step_sha256=$stepHash;expected_parts=$ExpectedParts
    visualization_deflection=0.04;effective_netgen_workers=1
    audit_report_timeout=$auditTimedOut;audit_ready_wall_ms=$auditReadyMs
    graceful_shutdown=$graceful;shutdown_timeout=$shutdownTimedOut;process_exit_code=$exitCode
    report_present=($report-ne $null);report_pass=if($report){[bool]$report.pass}else{$null}
    cad_bodies=if($report){$report.cad_bodies}else{$null}
    controller_errors=if($report){$report.controller_errors}else{$null}
    scene_batch_depth=if($report){$report.scene_batch_depth}else{$null}
    camera_flushes=if($report){$report.camera_flushes}else{$null}
    deferred_camera_adjusts=if($report){$report.deferred_camera_adjusts}else{$null}
    add_cells_calls=if($report){$report.add_cells_calls}else{$null}
    render_requests_during_batch=if($report){$report.render_requests_during_batch}else{$null}
    diagnostic_readiness_upper_bound_ms=if($report){$report.elapsed_ms_upper_bound_diagnostic_only}else{$null}
    total_harness_wall_ms=$wall.ElapsedMilliseconds
    interpretation='DIAGNOSTIC_ONLY: counts import/scene work for a reproducible synthetic 25-part STEP; not a speedup/FPS benchmark.'
  }
  $summary|ConvertTo-Json -Depth 6|Set-Content (Join-Path $root 'diagnostic-summary.json') -Encoding UTF8
  $summary|ConvertTo-Json -Depth 6
  if(-not $pass){throw 'C10.49 import telemetry runtime diagnostic failed.'}
  if($shutdownTimedOut){throw 'C10.49 telemetry passed but graceful shutdown timed out.'}
}
finally{
  Remove-Item Env:ASTERMAX_C1049_AUDIT_DIR -ErrorAction SilentlyContinue
  Remove-Item Env:ASTERMAX_C1049_EXPECTED_PARTS -ErrorAction SilentlyContinue
  Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_PARTS -ErrorAction SilentlyContinue
  Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION -ErrorAction SilentlyContinue
  Remove-Item Env:ASTERMAX_CAD_TESSELLATION_WORKERS -ErrorAction SilentlyContinue
}
