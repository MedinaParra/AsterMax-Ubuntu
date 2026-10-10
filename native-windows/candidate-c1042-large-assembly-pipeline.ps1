param([string]$Root)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
foreach($p in @($vtkPath,$controllerPath,$uiPath)){ if(!(Test-Path $p)){ throw "C10.42 missing: $p" } }

# ----------------------------------------------------------------------
# 1. Coalesce VTK render requests.
# C10.30 prevents render re-entry. C10.42 also collapses the many render
# requests emitted while a large CAD assembly is adding actors.
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
if(-not $v.Contains('C10.42 large-assembly path: one queued paint')){
    if(-not $v.Contains($oldRender.TrimEnd())){ throw 'C10.42 C10.30 RenderSceene body not recognized.' }
    $v=$v.Replace($oldRender.TrimEnd(),$newRender.TrimEnd())
}
Set-Content $vtkPath $v -Encoding UTF8

# ----------------------------------------------------------------------
# 2. Treat a STEP/IGES/BREP assembly as one import transaction.
# PrePoMax recursively imports compounds. Historically every compound called
# UpdateAfterImport(), which redraws the whole geometry and regenerates the
# tree before the top-level STEP has finished. Suppress those nested redraws;
# the existing top-level ImportFile() still performs exactly one final update.
# ----------------------------------------------------------------------
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$stateAnchor='        [NonSerialized] protected bool _animating;'
if(-not $c.Contains('_asterMaxCadImportDepth')){
    if(-not $c.Contains($stateAnchor)){ throw 'C10.42 Controller state anchor missing.' }
    $c=$c.Replace($stateAnchor,$stateAnchor+"`n        [NonSerialized] private int _asterMaxCadImportDepth;")
}

$methodStartOld=@'
        public string[] ImportCADAssemblyFile(string assemblyFileName, string splitCommand)
        {
            string[] filesToImport = SplitAssembly(assemblyFileName, splitCommand);
'@
$methodStartNew=@'
        public string[] ImportCADAssemblyFile(string assemblyFileName, string splitCommand)
        {
            bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;
            _asterMaxCadImportDepth++;
            var asterMaxCadImportWatch = System.Diagnostics.Stopwatch.StartNew();
            try
            {
                string[] filesToImport = SplitAssembly(assemblyFileName, splitCommand);
                if (asterMaxTopLevelCadImport)
                    _form.WriteDataToOutput("AsterMax CAD split: " +
                        (filesToImport == null ? 0 : filesToImport.Length) + " item(s) temporales.");
'@
if(-not $c.Contains('bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;')){
    if(-not $c.Contains($methodStartOld.TrimEnd())){ throw 'C10.42 ImportCADAssemblyFile start anchor missing.' }
    $c=$c.Replace($methodStartOld.TrimEnd(),$methodStartNew.TrimEnd())

    $methodEndOld=@'
            return allAddedPartNames.ToArray();
        }
        //
        public string[] SplitAssembly(string assemblyFileName, string splitCommand)
'@
    $methodEndNew=@'
                asterMaxCadImportWatch.Stop();
                if (asterMaxTopLevelCadImport)
                    _form.WriteDataToOutput("AsterMax CAD import: " + allAddedPartNames.Count +
                        " pieza(s) preparadas en " + asterMaxCadImportWatch.ElapsedMilliseconds +
                        " ms. Visualización final diferida hasta completar el conjunto.");
                return allAddedPartNames.ToArray();
            }
            finally
            {
                _asterMaxCadImportDepth--;
            }
        }
        //
        public string[] SplitAssembly(string assemblyFileName, string splitCommand)
'@
    if(-not $c.Contains($methodEndOld.TrimEnd())){ throw 'C10.42 ImportCADAssemblyFile end anchor missing.' }
    $c=$c.Replace($methodEndOld.TrimEnd(),$methodEndNew.TrimEnd())
}

# Suppress UpdateAfterImport only for compound imports that are nested inside
# ImportCADAssemblyFile. Direct compound creation retains the historical update.
$compoundMethod=$c.IndexOf('        private void ImportBrepCompoundPart(')
if($compoundMethod -lt 0){ throw 'C10.42 ImportBrepCompoundPart method missing.' }
$compoundUpdate='            UpdateAfterImport(".brep");'
$compoundUpdatePos=$c.IndexOf($compoundUpdate,$compoundMethod)
if($compoundUpdatePos -lt 0 -and -not $c.Contains('if (_asterMaxCadImportDepth == 0)')){
    throw 'C10.42 compound UpdateAfterImport anchor missing.'
}
if($compoundUpdatePos -ge 0){
    $guarded=@'
            if (_asterMaxCadImportDepth == 0)
                UpdateAfterImport(".brep");
'@
    $c=$c.Substring(0,$compoundUpdatePos)+$guarded.TrimEnd()+$c.Substring($compoundUpdatePos+$compoundUpdate.Length)
}

# ----------------------------------------------------------------------
# 3. Large-assembly initial graphics policy.
# Exact CAD/BREP stays untouched. Only edge rendering is suppressed for the
# first display of a large assembly. The user can turn edges back on later.
# ----------------------------------------------------------------------
$importAnchor=@'
                _currentView = ViewGeometryModelResults.Geometry;
                _form.SetCurrentView(_currentView);
                DrawGeometry(false);
'@
$importNew=@'
                _currentView = ViewGeometryModelResults.Geometry;
                _form.SetCurrentView(_currentView);

                // Keep the CAD/BREP exact; only simplify the initial graphics path.
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

                if (_asterMaxCadImportDepth == 0)
                    _form.WriteDataToOutput("AsterMax visualización CAD: " + asterMaxGeometryPartCount +
                        " pieza(s); render inicial " +
                        (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold ? "sin aristas." : "normal."));
                DrawGeometry(false);
'@
if(-not $c.Contains('ASTERMAX_LARGE_ASSEMBLY_PARTS')){
    if(-not $c.Contains($importAnchor.TrimEnd())){ throw 'C10.42 CAD import draw anchor missing.' }
    $c=$c.Replace($importAnchor.TrimEnd(),$importNew.TrimEnd())
}
Set-Content $controllerPath $c -Encoding UTF8

# ----------------------------------------------------------------------
# 4. Camera-only post import finalization.
# C10.23 called Controller.Redraw() a second time after UpdateAfterImport had
# already built every actor. On a large assembly that duplicated the expensive
# geometry draw and could race the VTK paint pipeline. Center only the camera,
# always on the UI thread, one message-loop turn after the final draw.
# ----------------------------------------------------------------------
$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")
$signature='        private void AsterMaxCenterImportedGeometry()'
$methodStart=$u.IndexOf($signature)
if($methodStart -lt 0){ throw 'C10.42 AsterMaxCenterImportedGeometry missing.' }
$braceStart=$u.IndexOf('{',$methodStart)
if($braceStart -lt 0){ throw 'C10.42 center method opening brace missing.' }
$depth=0
$methodEnd=-1
for($n=$braceStart; $n -lt $u.Length; $n++){
    if($u[$n] -eq '{'){ $depth++ }
    elseif($u[$n] -eq '}'){
        $depth--
        if($depth -eq 0){ $methodEnd=$n+1; break }
    }
}
if($methodEnd -lt 0){ throw 'C10.42 center method closing brace missing.' }
$centerNew=@'
        private void AsterMaxCenterImportedGeometry()
        {
            if (InvokeRequired)
            {
                BeginInvoke(new Action(AsterMaxCenterImportedGeometry));
                return;
            }
            if (_controller == null || _vtk == null || _vtk.IsDisposed) return;

            // Geometry actors are already created by UpdateAfterImport. Do not
            // call Controller.Redraw() again; only finalize viewport and camera.
            UpdateVtkControlSize();
            _vtk.RenderingOn = true;
            _vtk.Visible = true;
            _vtk.Enabled = true;
            _vtk.BringToFront();

            BeginInvoke(new Action(() =>
            {
                if (_vtk == null || _vtk.IsDisposed) return;
                _vtk.SetIsometricView(false, true);
                _vtk.SetZoomToFit(false);
                _vtk.Refresh();
            }));
        }
'@
$existingCenter=$u.Substring($methodStart,$methodEnd-$methodStart)
if(-not $existingCenter.Contains('Geometry actors are already created by UpdateAfterImport')){
    $u=$u.Substring(0,$methodStart)+$centerNew.TrimEnd()+$u.Substring($methodEnd)
}
Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.42: single CAD import transaction + coalesced VTK render + camera-only finalization applied.' -ForegroundColor Green
