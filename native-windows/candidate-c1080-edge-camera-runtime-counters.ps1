param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.80 missing: $vtkPath"}
$v=[regex]::Replace((Get-Content $vtkPath -Raw),'\r\n?',"`n")
if(!$v.Contains('_asterMaxPerfRenderExecuted')){throw 'C10.80 requires C10.79 render execution counters.'}
$fieldAnchor='        private long _asterMaxPerfRenderExecuted;'
if(!$v.Contains('_asterMaxPerfEdgeRequests')){
 $fields=@'
        private long _asterMaxPerfEdgeRequests;
        private long _asterMaxPerfCameraRequests;
'@
 $v=$v.Replace($fieldAnchor,$fieldAnchor+"`n"+$fields.TrimEnd())
}
# Count edge-related actor additions at the existing geometry actor entry point without changing edge construction.
$actorMarker='ASTERMAX_PERF_ACTOR add='
$actorPos=$v.IndexOf($actorMarker)
if($actorPos -lt 0){throw 'C10.80 requires C10.78 actor instrumentation.'}
# Camera request counters are attached to the stable public camera methods used by C10.42 finalization.
foreach($sig in @('        public void SetZoomToFit(','        public void SetIsometricView(')){
 $start=$v.IndexOf($sig)
 if($start -lt 0){throw "C10.80 camera method missing: $sig"}
 $brace=$v.IndexOf('{',$start)
 if($brace -lt 0){throw "C10.80 camera brace missing: $sig"}
 $methodEnd=$v.IndexOf('}', $brace)
 $snippet=$v.Substring($brace,[Math]::Min(500,$v.Length-$brace))
 if(!$snippet.Contains('ASTERMAX_PERF_CAMERA')){
  $name=if($sig.Contains('Zoom')){'zoom_fit'}else{'isometric'}
  $line="`n            _asterMaxPerfCameraRequests++;`n            if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace(\"ASTERMAX_PERF_CAMERA type=$name request=\" + _asterMaxPerfCameraRequests);"
  $v=$v.Insert($brace+1,$line)
 }
}
# Instrument edge visibility requests, a safe proxy for expensive edge-path activation; no visibility semantics change.
$edgeToken='CurrentEdgesVisibility'
$edgeMethod=$v.IndexOf('SetEdgesVisibility')
if($edgeMethod -ge 0 -and !$v.Substring($edgeMethod,[Math]::Min(900,$v.Length-$edgeMethod)).Contains('ASTERMAX_PERF_EDGE')){
 $brace=$v.IndexOf('{',$edgeMethod)
 if($brace -ge 0){
  $line="`n            _asterMaxPerfEdgeRequests++;`n            if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace(\"ASTERMAX_PERF_EDGE request=\" + _asterMaxPerfEdgeRequests);"
  $v=$v.Insert($brace+1,$line)
 }
}
Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.80 diagnostic edge/camera request counters applied; rendering and camera semantics unchanged.' -ForegroundColor Green
