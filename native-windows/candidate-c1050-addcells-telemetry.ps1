param([string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.50 missing: $vtkPath"}
$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")

# C10.50 is telemetry only. It records whether AddCells performs mapper/actor/renderer
# work once per logical part while the final CAD scene batch is active.
$fieldAnchor='        private long _asterMaxSceneBatchRenderRequests;'
if(-not $v.Contains('_asterMaxSceneBatchMapperInputs')){
  if(-not $v.Contains($fieldAnchor)){throw 'C10.50 C10.49 telemetry anchor missing.'}
  $fields=$fieldAnchor+"`n"+
    '        private long _asterMaxSceneBatchMapperInputs;'+"`n"+
    '        private long _asterMaxSceneBatchRendererAdds;'
  $v=$v.Replace($fieldAnchor,$fields)
}
$apiAnchor='        public long AsterMaxSceneBatchRenderRequests { get { return _asterMaxSceneBatchRenderRequests; } }'
if(-not $v.Contains('AsterMaxSceneBatchMapperInputs')){
  if(-not $v.Contains($apiAnchor)){throw 'C10.50 telemetry API anchor missing.'}
  $api=$apiAnchor+"`n"+
    '        public long AsterMaxSceneBatchMapperInputs { get { return _asterMaxSceneBatchMapperInputs; } }'+"`n"+
    '        public long AsterMaxSceneBatchRendererAdds { get { return _asterMaxSceneBatchRendererAdds; } }'
  $v=$v.Replace($apiAnchor,$api)
}
$reset='                _asterMaxSceneBatchRenderRequests = 0;'
if(-not $v.Contains('_asterMaxSceneBatchMapperInputs = 0;')){
  if(-not $v.Contains($reset)){throw 'C10.50 reset anchor missing.'}
  $v=$v.Replace($reset,$reset+"`n                _asterMaxSceneBatchMapperInputs = 0;`n                _asterMaxSceneBatchRendererAdds = 0;")
}

$sig='        public void AddCells(vtkMaxActorData data)'
$start=$v.IndexOf($sig);if($start -lt 0){throw 'C10.50 AddCells missing.'}
$brace=$v.IndexOf('{',$start);$depth=0;$end=-1
for($n=$brace;$n -lt $v.Length;$n++){if($v[$n]-eq '{'){$depth++}elseif($v[$n]-eq '}'){$depth--;if($depth-eq 0){$end=$n+1;break}}}
if($end -lt 0){throw 'C10.50 AddCells closing brace missing.'}
$m=$v.Substring($start,$end-$start)

# Count concrete pipeline operations by inserting counters immediately before
# the first mapper-input and renderer-add calls that already exist in AddCells.
if(-not $m.Contains('_asterMaxSceneBatchMapperInputs++;')){
  $patterns=@('.SetInputData(','.SetInputConnection(')
  $pos=-1
  foreach($p in $patterns){$q=$m.IndexOf($p);if($q -ge 0 -and ($pos -lt 0 -or $q -lt $pos)){$pos=$q}}
  if($pos -lt 0){throw 'C10.50 no mapper input operation found inside AddCells.'}
  $line=$m.LastIndexOf("`n",$pos);if($line -lt 0){throw 'C10.50 mapper input line boundary missing.'};$line++
  $indent=$m.Substring($line,$pos-$line);$indent=[regex]::Match($indent,'^\s*').Value
  $m=$m.Insert($line,$indent+'if (_asterMaxSceneBatchDepth > 0) _asterMaxSceneBatchMapperInputs++;'+"`n")
}
if(-not $m.Contains('_asterMaxSceneBatchRendererAdds++;')){
  $tokens=@('.AddActor(','.AddViewProp(');$pos=-1
  foreach($p in $tokens){$q=$m.IndexOf($p);if($q -ge 0 -and ($pos -lt 0 -or $q -lt $pos)){$pos=$q}}
  if($pos -lt 0){throw 'C10.50 no renderer add operation found inside AddCells.'}
  $line=$m.LastIndexOf("`n",$pos);if($line -lt 0){throw 'C10.50 renderer add line boundary missing.'};$line++
  $indent=$m.Substring($line,$pos-$line);$indent=[regex]::Match($indent,'^\s*').Value
  $m=$m.Insert($line,$indent+'if (_asterMaxSceneBatchDepth > 0) _asterMaxSceneBatchRendererAdds++;'+"`n")
}
$v=$v.Substring(0,$start)+$m+$v.Substring($end)
Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.50: telemetry only; instruments mapper-input and renderer-add work inside AddCells.' -ForegroundColor Green
