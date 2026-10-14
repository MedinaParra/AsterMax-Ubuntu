param([string]$Dist,[int]$ExpectedParts=100)
$ErrorActionPreference='Stop'
$Dist=(Resolve-Path $Dist).Path
$root=Join-Path $Dist 'Audit/C10.44'
New-Item -ItemType Directory -Force $root | Out-Null
$step=Join-Path $root 'benchmark-spheres.step'
$python=Join-Path $Dist 'AsterMaxRuntime/Python/python.exe'
$exe=Join-Path $Dist 'AsterMax Mechanical.exe'
if(!(Test-Path $python)){throw 'C10.44 packaged Python missing.'}
if(!(Test-Path $exe)){throw 'C10.44 AsterMax Mechanical.exe missing.'}

$code="import gmsh; gmsh.initialize(); gmsh.model.add('C1044'); [gmsh.model.occ.addSphere((i%10)*16,(i//10)*16,0,5) for i in range($ExpectedParts)]; gmsh.model.occ.synchronize(); gmsh.write(r'$step'); gmsh.finalize()"
& $python -c $code
if($LASTEXITCODE -ne 0 -or !(Test-Path $step)){throw 'C10.44 sphere STEP fixture generation failed.'}

function Invoke-ImportCase([string]$Label,[string]$Deflection){
  $out=Join-Path $root $Label
  New-Item -ItemType Directory -Force $out | Out-Null
  $env:ASTERMAX_C1043_AUDIT_DIR=$out
  $env:ASTERMAX_C1043_EXPECTED_PARTS=$ExpectedParts.ToString()
  $env:ASTERMAX_LARGE_ASSEMBLY_PARTS='80'
  $env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION=$Deflection
  try {
    $p=Start-Process -FilePath $exe -WorkingDirectory $Dist -ArgumentList @($step,'-US','MM_TON_S_C') -PassThru
    if(-not $p.WaitForExit(240000)){Stop-Process -Id $p.Id -Force;throw "C10.44 $Label timed out."}
    $reportPath=Join-Path $out 'c1043-import-report.json'
    if(!(Test-Path $reportPath)){throw "C10.44 $Label report missing."}
    $r=Get-Content $reportPath -Raw | ConvertFrom-Json
    if(-not $r.pass -or [int]$r.cad_bodies -lt $ExpectedParts -or [int]$r.controller_errors -ne 0){throw "C10.44 $Label import validation failed."}
    if($p.ExitCode -ne 0){throw "C10.44 $Label process exit=$($p.ExitCode)."}
    return [double]$r.elapsed_ms_upper_bound
  }
  finally {
    Remove-Item Env:ASTERMAX_C1043_AUDIT_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_C1043_EXPECTED_PARTS -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_PARTS -ErrorAction SilentlyContinue
    Remove-Item Env:ASTERMAX_LARGE_ASSEMBLY_DEFLECTION -ErrorAction SilentlyContinue
  }
}

# Alternating order reduces first-run/cache bias without pretending timer precision is exact.
$b1=Invoke-ImportCase 'baseline-1' '0.01'
$a1=Invoke-ImportCase 'adaptive-1' '0.04'
$a2=Invoke-ImportCase 'adaptive-2' '0.04'
$b2=Invoke-ImportCase 'baseline-2' '0.01'
$baseline=[math]::Round(($b1+$b2)/2.0,1)
$adaptive=[math]::Round(($a1+$a2)/2.0,1)
$delta=[math]::Round($baseline-$adaptive,1)
$improvement=if($baseline -gt 0){[math]::Round(100.0*$delta/$baseline,1)}else{0}
$status=if($delta -ge 250){'PASS'}elseif($delta -gt -1000){'INCONCLUSIVE'}else{'FAIL'}
$result=[ordered]@{
  fixture='100 analytic spheres STEP'
  expected_parts=$ExpectedParts
  baseline_deflection=0.01
  adaptive_deflection=0.04
  baseline_runs_ms=@($b1,$b2)
  adaptive_runs_ms=@($a1,$a2)
  baseline_average_ms=$baseline
  adaptive_average_ms=$adaptive
  delta_ms=$delta
  improvement_percent=$improvement
  timer_resolution_ms=500
  timing_semantics='upper bound from in-app 500 ms audit timer; includes startup+STEP split+tessellation+model import+initial visualization until idle'
  status=$status
}
$result|ConvertTo-Json -Depth 5|Set-Content (Join-Path $root 'benchmark.json') -Encoding UTF8
$result|ConvertTo-Json -Depth 5
if($status -eq 'FAIL'){throw 'C10.44 adaptive preview caused a material measured regression.'}
