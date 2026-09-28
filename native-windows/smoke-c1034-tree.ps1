param([string]$Dist)
$ErrorActionPreference='Stop'
$Dist=(Resolve-Path $Dist).Path
$out=Join-Path $Dist 'Audit/C10.34'
New-Item -ItemType Directory -Force $out | Out-Null
$step=Join-Path $out 'two-bodies.step'
$python=Join-Path $Dist 'AsterMaxRuntime/Python/python.exe'
& $python -c "import gmsh; gmsh.initialize(); gmsh.model.add('C1034'); gmsh.model.occ.addBox(0,0,0,100,10,10); gmsh.model.occ.addBox(0,20,0,100,10,10); gmsh.model.occ.synchronize(); gmsh.write(r'$step'); gmsh.finalize()"
if($LASTEXITCODE -ne 0){throw 'C10.34 CAD fixture generation failed.'}
$env:ASTERMAX_C1034_AUDIT_DIR=$out
try {
 $p=Start-Process -FilePath (Join-Path $Dist 'AsterMax Mechanical.exe') -WorkingDirectory $Dist -ArgumentList @($step,'-US','MM_TON_S_C') -PassThru
 if(-not $p.WaitForExit(110000)){
  Stop-Process -Id $p.Id -Force
  throw 'C10.34 native tree audit timed out.'
 }
 $report=Get-Content (Join-Path $out 'mechanical-tree-report.json') -Raw | ConvertFrom-Json
 $report | ConvertTo-Json -Depth 10
 if(-not $report.pass){throw 'C10.34 native tree audit FAIL.'}
 if($p.ExitCode -ne 0){throw "C10.34 process exit failed: $($p.ExitCode)"}
} finally { Remove-Item Env:ASTERMAX_C1034_AUDIT_DIR -ErrorAction SilentlyContinue }
