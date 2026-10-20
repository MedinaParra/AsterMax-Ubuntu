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
# Camera request counters are attached to stable public camera methods used by C10.42 finalization.
foreach($sig in @('        public void SetZoomToFit(','        public void SetIsometricView(')){
 $start=$v.IndexOf($sig)
 if($start -lt 0){throw "C10.80 camera method missing: $sig"}
 $brace=$v.IndexOf('{',$start)
 if($brace -lt 0){throw "C10.80 camera brace missing: $sig"}
 $snippet=$v.Substring($brace,[Math]::Min(500,$v.Length-$brace))
 if(!$snippet.Contains('ASTERMAX_PERF_CAMERA')){
  $name=if($sig.Contains('Zoom')){'zoom_fit'}else{'isometric'}
  $line1='            _asterMaxPerfCameraRequests++;'
  $line2='            if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace("ASTERMAX_PERF_CAMERA type='+$name+' request=" + _asterMaxPerfCameraRequests);'
  $v=$v.Insert($brace+1,"`n"+$line1+"`n"+$line2)
 }
}
# Instrument the actual SetEdgesVisibility method, not the first textual mention/call site.
# This remains diagnostic-only: it counts requests before existing edge visibility semantics execute.
$edgePattern='(?m)^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:void|bool)\s+SetEdgesVisibility\s*\('
$edgeMatch=[regex]::Match($v,$edgePattern)
if(!$edgeMatch.Success){throw 'C10.80 SetEdgesVisibility method declaration missing.'}
$edgeMethod=$edgeMatch.Index
$brace=$v.IndexOf('{',$edgeMethod)
if($brace -lt 0){throw 'C10.80 SetEdgesVisibility method brace missing.'}
$snippet=$v.Substring($brace,[Math]::Min(1200,$v.Length-$brace))
if(!$snippet.Contains('ASTERMAX_PERF_EDGE request=')){
 $line1='            _asterMaxPerfEdgeRequests++;'
 $line2='            if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace("ASTERMAX_PERF_EDGE request=" + _asterMaxPerfEdgeRequests);'
 $v=$v.Insert($brace+1,"`n"+$line1+"`n"+$line2)
}
Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.80 diagnostic edge/camera request counters applied at method declarations; rendering and camera semantics unchanged.' -ForegroundColor Green
