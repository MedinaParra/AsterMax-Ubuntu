param([string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.46 missing: $controllerPath"}
$c=Get-Content $controllerPath -Raw
$required=@(
  '"AsterMaxVis_" + Guid.NewGuid().ToString("N")',
  'psi.WorkingDirectory = processWorkDirectory;',
  'if (!process.WaitForExit(180000))',
  'process.Kill();',
  'process.WaitForExit(5000);',
  'AsterMax CAD NetGen shutdown warning:',
  'AsterMax CAD NetGen cleanup warning:',
  'int workers = Math.Min(2, Math.Max(1, Environment.ProcessorCount));',
  'workers = Math.Max(1, Math.Min(4, configuredWorkers));'
)
foreach($token in $required){
  if(-not $c.Contains($token)){throw "C10.46 FAIL missing token: $token"}
}
if($c.Contains('catch { }')){throw 'C10.46 FAIL: silent empty catch remains in Controller.cs'}
Write-Host 'C10.46 PASS: isolated scratch, bounded kill wait, visible cleanup warnings and conservative worker caps present.' -ForegroundColor Green
