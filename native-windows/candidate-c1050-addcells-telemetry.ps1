param([string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.50 missing: $vtkPath"}
$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")

# Telemetry only. Count the AddCells actor-construction dispatch once per call, not individual
# constructor expressions. C10.48 deliberately changes the old single construction into a
# conditional expression (deferred edges vs historical constructor), so instrument the unique
# assignment statement that owns that conditional rather than either branch of the ternary.
$fieldAnchor='        private long _asterMaxSceneBatchRenderRequests;'
if(-not $v.Contains('_asterMaxSceneBatchActorConstructions')){
  if(-not $v.Contains($fieldAnchor)){throw 'C10.50 C10.49 telemetry anchor missing.'}
  $v=$v.Replace($fieldAnchor,$fieldAnchor+"`n        private long _asterMaxSceneBatchActorConstructions;`n        private long _asterMaxSceneBatchGeometryAdds;")
}
$apiAnchor='        public long AsterMaxSceneBatchRenderRequests { get { return _asterMaxSceneBatchRenderRequests; } }'
if(-not $v.Contains('AsterMaxSceneBatchActorConstructions')){
  if(-not $v.Contains($apiAnchor)){throw 'C10.50 telemetry API anchor missing.'}
  $v=$v.Replace($apiAnchor,$apiAnchor+"`n        public long AsterMaxSceneBatchActorConstructions { get { return _asterMaxSceneBatchActorConstructions; } }`n        public long AsterMaxSceneBatchGeometryAdds { get { return _asterMaxSceneBatchGeometryAdds; } }")
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

function Insert-BeforeUniqueMatch([string]$text,[string]$pattern,[string]$counter,[string]$label){
  $matches=[regex]::Matches($text,$pattern,[System.Text.RegularExpressions.RegexOptions]::Multiline)
  if($matches.Count -ne 1){throw "C10.50 $label expected exactly 1 structural match, got $($matches.Count)."}
  if($text.Contains($counter)){return $text}
  $match=$matches[0]
  $line=$text.LastIndexOf("`n",$match.Index);if($line -lt 0){throw "C10.50 $label line boundary missing."};$line++
  $indent=[regex]::Match($text.Substring($line,$match.Index-$line),'^\s*').Value
  return $text.Insert($line,$indent+"if (_asterMaxSceneBatchDepth > 0) $counter`n")
}

# C10.48 turns the actor assignment into a multiline ternary containing two vtkMaxActor
# constructor expressions. The stable semantic boundary is the single declaration/assignment.
# Match through its terminating semicolon, while requiring vtkMaxActor to occur in the RHS.
$m=Insert-BeforeUniqueMatch $m '(?ms)^\s*vtkMaxActor\s+\w+\s*=\s*(?=[^;]*new\s+vtkMaxActor\s*\()[^;]+;' '_asterMaxSceneBatchActorConstructions++;' 'vtkMaxActor assignment'
$m=Insert-BeforeUniqueMatch $m '(?m)^\s*AddActorGeometry\s*\([^;]+\)\s*;' '_asterMaxSceneBatchGeometryAdds++;' 'AddActorGeometry dispatch'

$v=$v.Substring(0,$start)+$m+$v.Substring($end)
Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.50: telemetry only; instruments the unique vtkMaxActor assignment and AddActorGeometry dispatch inside AddCells, including C10.48 conditional construction.' -ForegroundColor Green
