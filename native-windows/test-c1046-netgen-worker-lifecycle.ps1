param([string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.46 missing: $controllerPath"}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

function Get-CSharpMethod([string]$text,[string]$signature){
  $start=$text.IndexOf($signature)
  if($start -lt 0){throw "C10.46 method missing: $signature"}
  $brace=$text.IndexOf('{',$start)
  if($brace -lt 0){throw "C10.46 opening brace missing: $signature"}
  $depth=0;$end=-1
  for($n=$brace;$n -lt $text.Length;$n++){
    if($text[$n] -eq '{'){$depth++}
    elseif($text[$n] -eq '}'){
      $depth--
      if($depth -eq 0){$end=$n+1;break}
    }
  }
  if($end -lt 0){throw "C10.46 closing brace missing: $signature"}
  return $text.Substring($start,$end-$start)
}

$method=Get-CSharpMethod $c '        private AsterMaxPreparedBrepVisualization AsterMaxPrepareBrepVisualization(string brepFileName,'
$required=@(
  '"AsterMaxVis_" + Guid.NewGuid().ToString("N")',
  'psi.WorkingDirectory = processWorkDirectory;',
  'if (!process.WaitForExit(180000))',
  'process.Kill();',
  'process.WaitForExit(5000);',
  'catch (Exception killEx)',
  'AsterMax CAD NetGen shutdown warning:',
  'catch (Exception cleanupEx)',
  'Directory.Delete(processWorkDirectory, true);',
  'AsterMax CAD NetGen cleanup warning:'
)
foreach($token in $required){
  if(-not $method.Contains($token)){throw "C10.46 FAIL missing worker token: $token"}
}
if($method.Contains('catch { }')){throw 'C10.46 FAIL: silent empty catch remains inside AsterMaxPrepareBrepVisualization'}

# Worker fan-out policy lives outside the worker method, so validate it against Controller.cs.
$controllerRequired=@(
  'int workers = Math.Min(2, Math.Max(1, Environment.ProcessorCount));',
  'workers = Math.Max(1, Math.Min(4, configuredWorkers));'
)
foreach($token in $controllerRequired){
  if(-not $c.Contains($token)){throw "C10.46 FAIL missing controller token: $token"}
}

Write-Host 'C10.46 PASS: worker-local lifecycle guard confirms isolated scratch, bounded kill wait, visible cleanup warnings and conservative worker caps.' -ForegroundColor Green
