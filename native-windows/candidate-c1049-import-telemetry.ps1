param([string]$Root)
$ErrorActionPreference='Stop'

$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.49 missing: $vtkPath"}
$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")

$fieldAnchor='        private long _asterMaxSceneBatchCameraFlushes;'
if(-not $v.Contains('_asterMaxSceneBatchAddCellsCalls')){
  if(-not $v.Contains($fieldAnchor)){throw 'C10.49 C10.47 telemetry anchor missing.'}
  $fields=@'
        private long _asterMaxSceneBatchCameraFlushes;
        private long _asterMaxSceneBatchAddCellsCalls;
        private long _asterMaxSceneBatchRenderRequests;
'@
  $v=$v.Replace($fieldAnchor,$fields.TrimEnd())
}

$apiAnchor='        public int AsterMaxSceneBatchDepth { get { return _asterMaxSceneBatchDepth; } }'
if(-not $v.Contains('AsterMaxSceneBatchAddCellsCalls')){
  if(-not $v.Contains($apiAnchor)){throw 'C10.49 scene batch API anchor missing.'}
  $api=$apiAnchor+"`n"+
       '        public long AsterMaxSceneBatchAddCellsCalls { get { return _asterMaxSceneBatchAddCellsCalls; } }'+"`n"+
       '        public long AsterMaxSceneBatchRenderRequests { get { return _asterMaxSceneBatchRenderRequests; } }'
  $v=$v.Replace($apiAnchor,$api)
}

$resetAnchor='                _asterMaxSceneBatchCameraFlushes = 0;'
if(-not $v.Contains('_asterMaxSceneBatchAddCellsCalls = 0;')){
  if(-not $v.Contains($resetAnchor)){throw 'C10.49 batch reset anchor missing.'}
  $v=$v.Replace($resetAnchor,$resetAnchor+"`n                _asterMaxSceneBatchAddCellsCalls = 0;`n                _asterMaxSceneBatchRenderRequests = 0;")
}

# Count scene additions without changing rendering semantics.
$methodSig='        public void AddCells(vtkMaxActorData data)'
$start=$v.IndexOf($methodSig)
if($start -lt 0){throw 'C10.49 AddCells missing.'}
$brace=$v.IndexOf('{',$start);$depth=0;$end=-1
for($n=$brace;$n -lt $v.Length;$n++){
  if($v[$n] -eq '{'){$depth++}elseif($v[$n] -eq '}'){$depth--;if($depth -eq 0){$end=$n+1;break}}
}
if($end -lt 0){throw 'C10.49 AddCells closing brace missing.'}
$m=$v.Substring($start,$end-$start)
if(-not $m.Contains('_asterMaxSceneBatchAddCellsCalls++;')){
  $open=$m.IndexOf('{')+1
  $m=$m.Substring(0,$open)+"`n            if (_asterMaxSceneBatchDepth > 0) _asterMaxSceneBatchAddCellsCalls++;"+$m.Substring($open)
  $v=$v.Substring(0,$start)+$m+$v.Substring($end)
}

# Instrument render scheduling requests only; do not suppress or coalesce anything in C10.49.
$renderToken='        private void AsterMaxRequestRender()'
$rstart=$v.IndexOf($renderToken)
if($rstart -ge 0){
  $rbrace=$v.IndexOf('{',$rstart);$rdepth=0;$rend=-1
  for($n=$rbrace;$n -lt $v.Length;$n++){
    if($v[$n] -eq '{'){$rdepth++}elseif($v[$n] -eq '}'){$rdepth--;if($rdepth -eq 0){$rend=$n+1;break}}
  }
  if($rend -lt 0){throw 'C10.49 render request closing brace missing.'}
  $rm=$v.Substring($rstart,$rend-$rstart)
  if(-not $rm.Contains('_asterMaxSceneBatchRenderRequests++;')){
    $ropen=$rm.IndexOf('{')+1
    $rm=$rm.Substring(0,$ropen)+"`n            if (_asterMaxSceneBatchDepth > 0) _asterMaxSceneBatchRenderRequests++;"+$rm.Substring($ropen)
    $v=$v.Substring(0,$rstart)+$rm+$v.Substring($rend)
  }
}

Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.49: telemetry only; counts AddCells and render requests during the final CAD scene batch.' -ForegroundColor Green
