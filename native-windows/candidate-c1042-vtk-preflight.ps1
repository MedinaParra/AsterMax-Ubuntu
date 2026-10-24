param([string]$Root)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
if(!(Test-Path $vtkPath)){ throw "C10.42 VTK preflight missing: $vtkPath" }

$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")

# Later baseline patches can move the C10.30 fields apart. Anchor to the
# individual pending field instead of requiring an exact adjacent block.
if(-not $v.Contains('private bool _asterMaxRenderScheduled;')){
    $pending='        private bool _asterMaxRenderPending;'
    if(-not $v.Contains($pending)){ throw 'C10.42 VTK preflight: _asterMaxRenderPending field missing.' }
    $v=$v.Replace($pending,$pending+"`n        private bool _asterMaxRenderScheduled;")
}

# Replace RenderSceene structurally so later patches/guards do not make this
# candidate depend on an obsolete exact method body.
$signature='        private void RenderSceene()'
$methodStart=$v.IndexOf($signature)
if($methodStart -lt 0){ throw 'C10.42 VTK preflight: RenderSceene missing.' }
$braceStart=$v.IndexOf('{',$methodStart)
if($braceStart -lt 0){ throw 'C10.42 VTK preflight: RenderSceene opening brace missing.' }
$depth=0
$methodEnd=-1
for($n=$braceStart; $n -lt $v.Length; $n++){
    if($v[$n] -eq '{'){ $depth++ }
    elseif($v[$n] -eq '}'){
        $depth--
        if($depth -eq 0){ $methodEnd=$n+1; break }
    }
}
if($methodEnd -lt 0){ throw 'C10.42 VTK preflight: RenderSceene closing brace missing.' }

$newRender=@'
        private void RenderSceene()
        {
            if (!_renderingOn || IsDisposed || !IsHandleCreated) return;
            if (_asterMaxRenderRequestActive)
            {
                _asterMaxRenderPending = true;
                return;
            }
            if (InvokeRequired)
            {
                BeginInvoke(new Action(RenderSceene));
                return;
            }

            // C10.42 large-assembly path: one queued paint per message-loop turn.
            if (_asterMaxRenderScheduled) return;
            _asterMaxRenderScheduled = true;
            BeginInvoke(new Action(() =>
            {
                _asterMaxRenderScheduled = false;
                if (_renderingOn && !IsDisposed && IsHandleCreated) Invalidate();
            }));
        }
'@
$v=$v.Substring(0,$methodStart)+$newRender.TrimEnd()+$v.Substring($methodEnd)
Set-Content $vtkPath $v -Encoding UTF8

Write-Host 'C10.42 VTK structural preflight applied.' -ForegroundColor Green
