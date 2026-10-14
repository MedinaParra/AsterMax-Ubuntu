param([string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.46c test missing: $controllerPath"}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

function Get-CSharpMethod([string]$text,[string]$signature){
  $start=$text.IndexOf($signature)
  if($start -lt 0){throw "C10.46c method missing: $signature"}
  $brace=$text.IndexOf('{',$start)
  if($brace -lt 0){throw "C10.46c opening brace missing: $signature"}
  $depth=0;$end=-1
  for($n=$brace;$n -lt $text.Length;$n++){
    if($text[$n] -eq '{'){$depth++}
    elseif($text[$n] -eq '}'){$depth--;if($depth -eq 0){$end=$n+1;break}}
  }
  if($end -lt 0){throw "C10.46c closing brace missing: $signature"}
  return $text.Substring($start,$end-$start)
}

$m=Get-CSharpMethod $c '        private Dictionary<string, AsterMaxPreparedBrepVisualization> AsterMaxPrepareLeafBrepVisualizations(string[] filesToImport)'
$checks=[ordered]@{
  'effective worker count fixed at one'=$m.Contains('int workers = 1;')
  'requested worker count remains observable'=$m.Contains('int requestedWorkers = 1;') -and $m.Contains('ASTERMAX_CAD_TESSELLATION_WORKERS')
  'unsafe request is reported'=$m.Contains('AsterMax CAD NetGen concurrency disabled: requested ')
  'parallel foreach removed from preview preparation'=(-not $m.Contains('Parallel.ForEach'))
  'serial foreach prepares each leaf'=$m.Contains('foreach (string brepFileName in leaves)') -and $m.Contains('prepared[brepFileName] = AsterMaxPrepareBrepVisualization')
  'single-flight telemetry present'=$m.Contains('AsterMax CAD single-flight preview: ')
  'exact BREP retention explicit'=$m.Contains('BREP exacto conservado.')
}
$failed=@($checks.GetEnumerator()|Where-Object{-not $_.Value})
foreach($item in $checks.GetEnumerator()){
  $status=if($item.Value){'PASS'}else{'FAIL'}
  Write-Host ($status+' - '+$item.Key)
}
if($failed.Count -gt 0){throw ('C10.46c regression guard failed: '+(($failed|ForEach-Object{$_.Key}) -join ', '))}
Write-Host 'C10.46c PASS: NetGen BREP->VIS is single-flight and exact CAD/model/VTK semantics remain outside this policy change.' -ForegroundColor Green
