param([string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.50 missing: $vtkPath"}
$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")

# C10.50 is telemetry only. C10.49 proved AddCells is called once per synthetic CAD body.
# PrePoMax does not configure the mapper directly in AddCells: vtkMaxActor(data) owns that
# construction path and AddActorGeometry dispatches the actor to the renderer. Count those
# concrete operations instead of assuming SetInputData/SetInputConnection live in AddCells.
$fieldAnchor='        private long _asterMaxSceneBatchRenderRequests;'
if(-not $v.Contains('_asterMaxSceneBatchActorConstructions')){
  if(-not $v.Contains($fieldAnchor)){throw 'C10.50 C10.49 telemetry anchor missing.'}
  $fields=$fieldAnchor+"`n"+
    '        private long _asterMaxSceneBatchActorConstructions;'+"`n"+
    '        private long _asterMaxSceneBatchGeometryAdds;'
  $v=$v.Replace($fieldAnchor,$fields)
}
$apiAnchor='        public long AsterMaxSceneBatchRenderRequests { get { return _asterMaxSceneBatchRenderRequests; } }'
if(-not $v.Contains('AsterMaxSceneBatchActorConstructions')){
  if(-not $v.Contains($apiAnchor)){throw 'C10.50 telemetry API anchor missing.'}
  $api=$apiAnchor+"`n"+
    '        public long AsterMaxSceneBatchActorConstructions { get { return _asterMaxSceneBatchActorConstructions; } }'+"`n"+
    '        public long AsterMaxSceneBatchGeometryAdds { get { return _asterMaxSceneBatchGeometryAdds; } }'
  $v=$v.Replace($apiAnchor,$api)
}
$reset='                _asterMaxSceneBatchRenderRequests = 0;'
if(-not $v.Contains('_asterMaxSceneBatchActorConstructions = 0;')){
  if(-not $v.Contains($reset)){throw 'C10.50 reset anchor missing.'}
  $v=$v.Replace($reset,$reset+"`n                _asterMaxSceneBatchActorConstructions = 0;`n                _asterMaxSceneBatchGeometryAdds = 0;")
}

$sig='        public void AddCells(vtkMaxActorData data)'
$start=$v.IndexOf($sig);if($start -lt 0){throw 'C10.50 AddCells missing.'}
$brace=$v.IndexOf('{',$start);$depth=0;$end=-1
for($n=$brace;$n -lt $v.Length;$n++){if($v[$n]-eq '{'){$depth++}elseif($v[$n]-eq '}'){$depth--;if($depth-eq 0){$end=$n+1;break}}}
if($end -lt 0){throw 'C10.50 AddCells closing brace missing.'}
$m=$v.Substring($start,$end-$start)

if(-not $m.Contains('_asterMaxSceneBatchActorConstructions++;')){
  $token='vtkMaxActor actor = new vtkMaxActor(data);'
  $pos=$m.IndexOf($token)
  if($pos -lt 0){throw 'C10.50 vtkMaxActor construction not found inside AddCells.'}
  $line=$m.LastIndexOf("`n",$pos);if($line -lt 0){throw 'C10.50 actor construction line boundary missing.'};$line++
  $indent=[regex]::Match($m.Substring($line,$pos-$line),'^\s*').Value
  $m=$m.Insert($line,$indent+'if (_asterMaxSceneBatchDepth > 0) _asterMaxSceneBatchActorConstructions++;'+"`n")
}
if(-not $m.Contains('_asterMaxSceneBatchGeometryAdds++;')){
  $token='AddActorGeometry(actor, data.Layer);'
  $pos=$m.IndexOf($token)
  if($pos -lt 0){throw 'C10.50 AddActorGeometry dispatch not found inside AddCells.'}
  $line=$m.LastIndexOf("`n",$pos);if($line -lt 0){throw 'C10.50 geometry add line boundary missing.'};$line++
  $indent=[regex]::Match($m.Substring($line,$pos-$line),'^\s*').Value
  $m=$m.Insert($line,$indent+'if (_asterMaxSceneBatchDepth > 0) _asterMaxSceneBatchGeometryAdds++;'+"`n")
}
$v=$v.Substring(0,$start)+$m+$v.Substring($end)
Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.50: telemetry only; instruments vtkMaxActor construction and AddActorGeometry dispatch inside AddCells.' -ForegroundColor Green
