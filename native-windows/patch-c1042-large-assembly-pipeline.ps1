param([string]$Root)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
foreach($p in @($vtkPath,$controllerPath)){ if(!(Test-Path $p)){ throw "C10.42 missing: $p" } }

# ----------------------------------------------------------------------
# 1. Coalesce VTK render requests.
# C10.30 prevents re-entry, but every RenderSceene request can still enqueue
# another paint. Large assemblies issue many requests while actors are being
# created. Schedule one UI invalidation per message-loop turn and collapse
# the rest into that request.
# ----------------------------------------------------------------------
$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")
$fieldAnchor=@'
        private bool _asterMaxRenderRequestActive;
        private bool _asterMaxRenderPending;
'@
$fieldNew=@'
        private bool _asterMaxRenderRequestActive;
        private bool _asterMaxRenderPending;
        private bool _asterMaxRenderScheduled;
'@
if(-not $v.Contains('_asterMaxRenderScheduled')){
    if(-not $v.Contains($fieldAnchor.TrimEnd())){ throw 'C10.42 C10.30 render guard fields missing.' }
    $v=$v.Replace($fieldAnchor.TrimEnd(),$fieldNew.TrimEnd())
}

$oldRender=@'
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
            Invalidate();
        }
'@
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

            // Large-assembly path: collapse all render requests generated while
            // geometry actors are added into a single paint on the UI queue.
            if (_asterMaxRenderScheduled) return;
            _asterMaxRenderScheduled = true;
            BeginInvoke(new Action(() =>
            {
                _asterMaxRenderScheduled = false;
                if (_renderingOn && !IsDisposed && IsHandleCreated) Invalidate();
            }));
        }
'@
if(-not $v.Contains('Large-assembly path: collapse all render requests')){
    if(-not $v.Contains($oldRender.TrimEnd())){ throw 'C10.42 C10.30 RenderSceene body not recognized.' }
    $v=$v.Replace($oldRender.TrimEnd(),$newRender.TrimEnd())
}
Set-Content $vtkPath $v -Encoding UTF8

# ----------------------------------------------------------------------
# 2. Large-assembly visual policy for imported CAD.
# Preserve exact BREP/model data. Only suppress expensive edge rendering on
# first draw when the imported geometry has many parts. The threshold is
# configurable for benchmarking through ASTERMAX_LARGE_ASSEMBLY_PARTS.
# ----------------------------------------------------------------------
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$importAnchor=@'
                _currentView = ViewGeometryModelResults.Geometry;
                _form.SetCurrentView(_currentView);
                DrawGeometry(false);
'@
$importNew=@'
                _currentView = ViewGeometryModelResults.Geometry;
                _form.SetCurrentView(_currentView);

                // Keep the CAD/BREP exact; only simplify the initial graphics path.
                // Detailed edges remain user-selectable after the model is visible.
                int asterMaxLargeAssemblyThreshold = 80;
                string asterMaxThresholdText = Environment.GetEnvironmentVariable("ASTERMAX_LARGE_ASSEMBLY_PARTS");
                int asterMaxConfiguredThreshold;
                if (!String.IsNullOrWhiteSpace(asterMaxThresholdText) &&
                    Int32.TryParse(asterMaxThresholdText, out asterMaxConfiguredThreshold) &&
                    asterMaxConfiguredThreshold > 1)
                    asterMaxLargeAssemblyThreshold = asterMaxConfiguredThreshold;

                int asterMaxGeometryPartCount = (_model != null && _model.Geometry != null && _model.Geometry.Parts != null)
                    ? _model.Geometry.Parts.Count : 0;
                if (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold)
                    CurrentEdgesVisibility = vtkEdgesVisibility.NoEdges;

                DrawGeometry(false);
'@
if(-not $c.Contains('ASTERMAX_LARGE_ASSEMBLY_PARTS')){
    if(-not $c.Contains($importAnchor.TrimEnd())){ throw 'C10.42 CAD import draw anchor missing.' }
    $c=$c.Replace($importAnchor.TrimEnd(),$importNew.TrimEnd())
}
Set-Content $controllerPath $c -Encoding UTF8

Write-Host 'C10.42: large-assembly graphics policy + coalesced VTK render queue applied.' -ForegroundColor Green
