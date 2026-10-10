param([string]$Dist,[int]$ExpectedParts=25,[int]$CaseTimeoutMs=90000)
$ErrorActionPreference='Stop'
$Dist=(Resolve-Path $Dist).Path
$root=Join-Path $Dist 'Audit/C10.46/diagnostic-25'
New-Item -ItemType Directory -Force $root | Out-Null
$step=Join-Path $root 'diagnostic-25-spheres.step'
$python=Join-Path $Dist 'AsterMaxRuntime/Python/python.exe'
$exe=Join-Path $Dist 'AsterMax Mechanical.exe'
if(!(Test-Path $python)){throw 'C10.46 packaged Python missing.'}
if(!(Test-Path $exe)){throw 'C10.46 AsterMax Mechanical.exe missing.'}

$code="import gmsh; gmsh.initialize(); gmsh.model.add('C1046_25'); [gmsh.model.occ.addSphere((i%5)*16,(i//5)*16,0,5) for i in range($ExpectedParts)]; gmsh.model.occ.synchronize(); gmsh.write(r'$step'); gmsh.finalize()"
& $python -c $code
if($LASTEXITCODE -ne 0 -or !(Test-Path $step)){throw 'C10.46 25-sphere STEP fixture generation failed.'}
$stepHash=(Get-FileHash $step -Algorithm SHA256).Hash.ToLowerInvariant()

function Get-NetGenSnapshot {
  $procs=@(Get-Process -Name 'NetGenMesher' -ErrorAction SilentlyContinue)
  $scratch=@(Get-ChildItem (Join-Path $Dist 'Temp') -Directory -Filter 'AsterMaxVis_*' -ErrorAction SilentlyContinue)
  return [ordered]@{
    netgen_process_count=$procs.Count
    netgen_process_ids=@($procs | ForEach-Object {$_.Id})
    scratch_count=$scratch.Count
    scratch_names=@($scratch | ForEach-Object {$_.Name})
  }
}

function Invoke-DiagnosticCase([string]$Label,[int]$RequestedWorkers){
  $out=Join-Path $root $Label
  New-Item -ItemType Directory -Force $out | Out-Null
  $env:ASTERMAX_C1043_AUDIT_DIR=$out
  $env:ASTERMAX_C1043_EXPECTED_PARTS=$ExpectedParts.ToString()
  $env:ASTERMAX_LARGE_ASSEMBLY_PARTS='8'
  $env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION='0.04'
  $env:ASTERMAX_CAD_TESSELLATION_WORKERS=$RequestedWorkers.ToString()
  try {
    $started=(Get-Date).ToUniversalTime()
    $before=Get-NetGenSnapshot
    $p=$null
    $timedOut=$false
    $errorText=$null
    try {
      $p=Start-Process -FilePath $exe -WorkingDirectory $Dist -ArgumentList @($step,'-US','MM_TON_S_C') -PassThru
      if(-not $p.WaitForExit($CaseTimeoutMs)){
        $timedOut=$true
        try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch { $errorText='AsterMax stop failed: '+$_.Exception.Message }
      }
    }
    catch { $errorText=$_.Exception.Message }
    Start-Sleep -Seconds 2
    $after=Get-NetGenSnapshot
    $reportPath=Join-Path $out 'c1043-import-report.json'
    $report=$null
    if(Test-Path $reportPath){
      try { $report=Get-Content $reportPath -Raw | ConvertFrom-Json } catch { $errorText='Report parse failed: '+$_.Exception.Message }
    }
    $exitCode=$null
    if($p -and -not $timedOut){ try {$exitCode=$p.ExitCode} catch {} }
    $result=[ordered]@{
      label=$Label
      requested_workers=$RequestedWorkers
      expected_parts=$ExpectedParts
      process_timeout_ms=$CaseTimeoutMs
      timed_out=$timedOut
      process_exit_code=$exitCode
      report_present=(Test-Path $reportPath)
      report_pass=if($report){[bool]$report.pass}else{$null}
      cad_bodies=if($report){$report.cad_bodies}else{$null}
      controller_errors=if($report){$report.controller_errors}else{$null}
      elapsed_ms_upper_bound=if($report){$report.elapsed_ms_upper_bound}else{$null}
      before=$before
      after=$after
      error=$errorText
      started_utc=$started.ToString('o')
      completed_utc=(Get-Date).ToUniversalTime().ToString('o')
    }
    $result | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $out 'case-result.json') -Encoding UTF8
    return $result
  }
  finally {
    Remove-Item Env:ASTERMAX_C1043_AUDIT_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_C1043_EXPECTED_PARTS -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_PARTS -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_CAD_TESSELLATION_WORKERS -ErrorAction SilentlyContinue
  }
}

$sequential=Invoke-DiagnosticCase 'requested-workers1' 1
Get-Process -Name 'NetGenMesher' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
$requestedTwo=Invoke-DiagnosticCase 'requested-workers2' 2

$status=if($requestedTwo.timed_out){'REQUESTED2_TIMEOUT'}elseif(-not $requestedTwo.report_present){'REQUESTED2_NO_REPORT'}elseif($requestedTwo.report_pass -ne $true){'REQUESTED2_REPORT_FAIL'}elseif($sequential.report_pass -eq $true){'REQUESTED2_SAFE_SINGLEFLIGHT_COMPLETES'}else{'SEQUENTIAL_NOT_CONFIRMED'}
$summary=[ordered]@{
  fixture='25 analytic spheres STEP'
  step_sha256=$stepHash
  expected_parts=$ExpectedParts
  visualization_deflection=0.04
  status=$status
  sequential=$sequential
  requested_two=$requestedTwo
  policy_note='C10.46c static guard fixes effective NetGen external concurrency at one; requested_workers=2 tests that the unsafe request is safely serialized.'
  interpretation='DIAGNOSTIC_ONLY: one run per request; no speedup/FPS claim.'
}
$summary | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $root 'diagnostic-summary.json') -Encoding UTF8
$summary | ConvertTo-Json -Depth 10
