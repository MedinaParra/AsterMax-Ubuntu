param([string]$Dist)
$ErrorActionPreference='Stop'
$Dist=(Resolve-Path $Dist).Path
$out=Join-Path $Dist 'Audit/C10.35-runtime'
New-Item -ItemType Directory -Force $out | Out-Null
$step=Join-Path $out 'two-touching-solids.step'
$python=Join-Path $Dist 'AsterMaxRuntime/Python/python.exe'
if(-not (Test-Path $python)){ throw "AsterMax packaged Python runtime not found: $python" }

& $python -c "import gmsh; gmsh.initialize(); gmsh.model.add('C1035'); gmsh.model.occ.addBox(0,0,0,50,20,20,1); gmsh.model.occ.addBox(50,0,0,50,20,20,2); gmsh.model.occ.synchronize(); gmsh.write(r'$step'); gmsh.finalize()"
if($LASTEXITCODE -ne 0){ throw 'C10.35 CAD fixture generation failed.' }
if(-not (Test-Path $step)){ throw 'C10.35 STEP fixture was not produced.' }

$env:ASTERMAX_C1035_AUDIT_DIR=$out
try {
  $exe=Join-Path $Dist 'AsterMax Mechanical.exe'
  if(-not (Test-Path $exe)){ throw "Executable not found: $exe" }
  $p=Start-Process -FilePath $exe -WorkingDirectory $Dist -ArgumentList @($step,'-US','MM_TON_S_C') -PassThru
  if(-not $p.WaitForExit(240000)){
    Stop-Process -Id $p.Id -Force
    throw 'C10.35 runtime defaults/contact audit timed out.'
  }
  $reportPath=Join-Path $out 'defaults-autocontact-report.json'
  if(-not (Test-Path $reportPath)){ throw 'C10.35 runtime report was not produced.' }
  $report=Get-Content $reportPath -Raw | ConvertFrom-Json
  $report | ConvertTo-Json -Depth 20
  if(-not $report.pass){ throw "C10.35 runtime defaults/contact audit FAIL: $($report.error)" }
  if($p.ExitCode -ne 0){ throw "C10.35 audited process exit failed: $($p.ExitCode)" }
} finally {
  Remove-Item Env:ASTERMAX_C1035_AUDIT_DIR -ErrorAction SilentlyContinue
}
