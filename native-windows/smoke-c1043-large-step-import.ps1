param([string]$Dist,[int]$ExpectedParts=100)
$ErrorActionPreference='Stop'
$Dist=(Resolve-Path $Dist).Path
$out=Join-Path $Dist 'Audit/C10.43'
New-Item -ItemType Directory -Force $out | Out-Null
$step=Join-Path $out 'large-assembly.step'
$python=Join-Path $Dist 'AsterMaxRuntime/Python/python.exe'
if(!(Test-Path $python)){throw 'C10.43 packaged Python missing.'}

$code="import gmsh; gmsh.initialize(); gmsh.model.add('C1043'); [gmsh.model.occ.addBox((i%10)*20,(i//10)*20,0,10,10,10) for i in range($ExpectedParts)]; gmsh.model.occ.synchronize(); gmsh.write(r'$step'); gmsh.finalize()"
& $python -c $code
if($LASTEXITCODE -ne 0 -or !(Test-Path $step)){throw 'C10.43 large STEP fixture generation failed.'}

$env:ASTERMAX_C1043_AUDIT_DIR=$out
$env:ASTERMAX_C1043_EXPECTED_PARTS=$ExpectedParts.ToString()
try {
  $exe=Join-Path $Dist 'AsterMax Mechanical.exe'
  if(!(Test-Path $exe)){throw 'C10.43 AsterMax Mechanical.exe missing.'}
  $p=Start-Process -FilePath $exe -WorkingDirectory $Dist -ArgumentList @($step,'-US','MM_TON_S_C') -PassThru
  if(-not $p.WaitForExit(210000)){
    Stop-Process -Id $p.Id -Force
    throw 'C10.43 100-body STEP import timed out.'
  }
  $reportPath=Join-Path $out 'c1043-import-report.json'
  if(!(Test-Path $reportPath)){throw 'C10.43 import report missing.'}
  $report=Get-Content $reportPath -Raw | ConvertFrom-Json
  $report | ConvertTo-Json -Depth 10
  if(-not $report.pass){throw 'C10.43 runtime import audit FAIL.'}
  if([int]$report.cad_bodies -lt $ExpectedParts){throw "C10.43 imported $($report.cad_bodies), expected at least $ExpectedParts bodies."}
  if([int]$report.controller_errors -ne 0){throw "C10.43 controller reported $($report.controller_errors) import errors."}
  if($p.ExitCode -ne 0){throw "C10.43 process exit failed: $($p.ExitCode)"}
  'PASS' | Set-Content (Join-Path $out 'runtime-import-pass.txt') -Encoding ASCII
} finally {
  Remove-Item Env:ASTERMAX_C1043_AUDIT_DIR -ErrorAction SilentlyContinue
  Remove-Item Env:ASTERMAX_C1043_EXPECTED_PARTS -ErrorAction SilentlyContinue
}
