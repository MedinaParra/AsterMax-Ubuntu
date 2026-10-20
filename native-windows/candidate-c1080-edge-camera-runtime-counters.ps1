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
# Edge visibility API names vary across the reconstructed PrePoMax lineage.
# Instrument one effective public/protected/private visibility entry point structurally,
# without assuming the historical SetEdgesVisibility name or changing its semantics.
$edgePatterns=@(
 '(?m)^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:void|bool)\s+SetEdgesVisibility\s*\(',
 '(?m)^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:void|bool)\s+SetElementEdgesVisibility\s*\(',
 '(?m)^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:void|bool)\s+SetEdgeVisibility\s*\('
)
$edgeMatch=$null
foreach($pattern in $edgePatterns){$m=[regex]::Match($v,$pattern);if($m.Success){$edgeMatch=$m;break}}
if($null -ne $edgeMatch){
 $brace=$v.IndexOf('{',$edgeMatch.Index)
 if($brace -lt 0){throw 'C10.80 edge visibility method brace missing.'}
 $snippet=$v.Substring($brace,[Math]::Min(1200,$v.Length-$brace))
 if(!$snippet.Contains('ASTERMAX_PERF_EDGE request=')){
  $line1='            _asterMaxPerfEdgeRequests++;'
  $line2='            if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace("ASTERMAX_PERF_EDGE request=" + _asterMaxPerfEdgeRequests);'
  $v=$v.Insert($brace+1,"`n"+$line1+"`n"+$line2)
 }
} else {
 # C10.48 guarantees an on-demand edge materialization entry point when historical visibility APIs are absent.
 # Count that effective request path instead of failing on a stale method name.
 $fallbackPattern='(?m)^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:void|bool)\s+AsterMaxEnsureElementEdges\s*\('
 $fallback=[regex]::Match($v,$fallbackPattern)
 if(!$fallback.Success){throw 'C10.80 no effective edge visibility/materialization entry point found.'}
 $brace=$v.IndexOf('{',$fallback.Index)
 if($brace -lt 0){throw 'C10.80 edge materialization method brace missing.'}
 $snippet=$v.Substring($brace,[Math]::Min(1200,$v.Length-$brace))
 if(!$snippet.Contains('ASTERMAX_PERF_EDGE request=')){
  $line1='            _asterMaxPerfEdgeRequests++;'
  $line2='            if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace("ASTERMAX_PERF_EDGE request=" + _asterMaxPerfEdgeRequests);'
  $v=$v.Insert($brace+1,"`n"+$line1+"`n"+$line2)
 }
}
Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.80 diagnostic edge/camera request counters applied to an effective edge entry point; rendering semantics unchanged.' -ForegroundColor Green
