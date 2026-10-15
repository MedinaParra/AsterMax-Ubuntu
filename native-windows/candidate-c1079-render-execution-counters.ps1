param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){throw "C10.79 missing: $vtkPath"}
$v=[regex]::Replace((Get-Content $vtkPath -Raw),'\r\n?',"`n")
if(!$v.Contains('_asterMaxRenderScheduled')){throw 'C10.79 requires C10.42 render coalescing.'}
if(!$v.Contains('_asterMaxPerfRenderRequests')){throw 'C10.79 requires C10.78 runtime counters.'}
$fieldAnchor='        private long _asterMaxPerfRenderRequests;'
if(!$v.Contains('_asterMaxPerfRenderQueued')){
 $fields=@'
        private long _asterMaxPerfRenderQueued;
        private long _asterMaxPerfRenderExecuted;
'@
 $v=$v.Replace($fieldAnchor,$fieldAnchor+"`n"+$fields.TrimEnd())
}
$queueAnchor='            _asterMaxRenderScheduled = true;'
if(!$v.Contains('ASTERMAX_PERF_RENDER queued=')){
 if(!$v.Contains($queueAnchor)){throw 'C10.79 render queue anchor missing.'}
 $queueLines=@'
            _asterMaxPerfRenderQueued++;
            if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace("ASTERMAX_PERF_RENDER queued=" + _asterMaxPerfRenderQueued + " requests=" + _asterMaxPerfRenderRequests);
'@
 $v=$v.Replace($queueAnchor,$queueAnchor+"`n"+$queueLines.TrimEnd())
}
$executeAnchor='                if (_renderingOn && !IsDisposed && IsHandleCreated) Invalidate();'
if(!$v.Contains('ASTERMAX_PERF_RENDER executed=')){
 if(!$v.Contains($executeAnchor)){throw 'C10.79 render execution anchor missing.'}
 $executeNew=@'
                if (_renderingOn && !IsDisposed && IsHandleCreated)
                {
                    _asterMaxPerfRenderExecuted++;
                    if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace("ASTERMAX_PERF_RENDER executed=" + _asterMaxPerfRenderExecuted + " queued=" + _asterMaxPerfRenderQueued + " requests=" + _asterMaxPerfRenderRequests);
                    Invalidate();
                }
'@
 $v=$v.Replace($executeAnchor,$executeNew.TrimEnd())
}
Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.79 diagnostic counters for render requests, queued paints and executed invalidations applied; scheduling semantics unchanged.' -ForegroundColor Green
