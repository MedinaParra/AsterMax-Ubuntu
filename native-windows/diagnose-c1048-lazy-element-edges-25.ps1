param([string]$Dist,[int]$ExpectedParts=25,[int]$CaseTimeoutMs=90000,[int]$ShutdownTimeoutMs=10000)
$ErrorActionPreference='Stop'
$Dist=(Resolve-Path $Dist).Path
$root=Join-Path $Dist 'Audit/C10.48/diagnostic-25'
New-Item -ItemType Directory -Force $root | Out-Null
$step=Join-Path $root 'diagnostic-25-spheres.step'
$python=Join-Path $Dist 'AsterMaxRuntime/Python/python.exe'
$exe=Join-Path $Dist 'AsterMax Mechanical.exe'
if(!(Test-Path $python)){throw 'C10.48 packaged Python missing.'}
if(!(Test-Path $exe)){throw 'C10.48 AsterMax Mechanical.exe missing.'}
$code="import gmsh; gmsh.initialize(); gmsh.model.add('C1048_25'); [gmsh.model.occ.addSphere((i%5)*16,(i//5)*16,0,5) for i in range($ExpectedParts)]; gmsh.model.occ.synchronize(); gmsh.write(r'$step'); gmsh.finalize()"
& $python -c $code
if($LASTEXITCODE -ne 0 -or !(Test-Path $step)){throw 'C10.48 STEP fixture generation failed.'}
$stepHash=(Get-FileHash $step -Algorithm SHA256).Hash.ToLowerInvariant()
$out=Join-Path $root 'lazy-edges'
New-Item -ItemType Directory -Force $out | Out-Null
$reportPath=Join-Path $out 'c1048-lazy-edges-report.json'
Remove-Item $reportPath -Force -ErrorAction SilentlyContinue
$env:ASTERMAX_C1048_AUDIT_DIR=$out
$env:ASTERMAX_C1048_EXPECTED_PARTS=$ExpectedParts.ToString()
$env:ASTERMAX_LARGE_ASSEMBLY_PARTS='8'
$env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION='0.04'
$env:ASTERMAX_CAD_TESSELLATION_WORKERS='1'
try {
  $wall=[System.Diagnostics.Stopwatch]::StartNew()
  $p=Start-Process -FilePath $exe -WorkingDirectory $Dist -ArgumentList @($step,'-US','MM_TON_S_C') -PassThru
  $report=$null
  while($wall.ElapsedMilliseconds -lt $CaseTimeoutMs){
    if(Test-Path $reportPath){
      try {$report=Get-Content $reportPath -Raw|ConvertFrom-Json;if($report){break}}catch{}
    }
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
    deferred_edge_actors=if($report){$report.deferred_edge_actors}else{$null}
    materialized_before_toggle=if($report){$report.materialized_before_toggle}else{$null}
    remaining_before_toggle=if($report){$report.remaining_before_toggle}else{$null}
    materialized_after_toggle=if($report){$report.materialized_after_toggle}else{$null}
    remaining_after_toggle=if($report){$report.remaining_after_toggle}else{$null}
    deferred_phase_pass=if($report){$report.deferred_phase_pass}else{$null}
    materialize_phase_pass=if($report){$report.materialize_phase_pass}else{$null}
    controller_errors_before=if($report){$report.controller_errors_before}else{$null}
    controller_errors_after=if($report){$report.controller_errors_after}else{$null}
    total_harness_wall_ms=$wall.ElapsedMilliseconds
    interpretation='DIAGNOSTIC_ONLY: proves deferred element-edge construction and synchronous on-demand materialization; not a speedup/FPS benchmark.'
  }
  $summary|ConvertTo-Json -Depth 6|Set-Content (Join-Path $root 'diagnostic-summary.json') -Encoding UTF8
  $summary|ConvertTo-Json -Depth 6
  if(-not $pass){throw 'C10.48 lazy element-edge runtime diagnostic failed.'}
  if($shutdownTimedOut){throw 'C10.48 scene passed but graceful shutdown timed out.'}
}
finally{
  Remove-Item Env:ASTERMAX_C1048_AUDIT_DIR -ErrorAction SilentlyContinue
  Remove-Item Env:ASTERMAX_C1048_EXPECTED_PARTS -ErrorAction SilentlyContinue
  Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_PARTS -ErrorAction SilentlyContinue
  Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION -ErrorAction SilentlyContinue
  Remove-Item Env:ASTERMAX_CAD_TESSELLATION_WORKERS -ErrorAction SilentlyContinue
}
