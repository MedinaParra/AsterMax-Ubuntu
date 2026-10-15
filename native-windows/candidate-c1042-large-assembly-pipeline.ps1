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
# C10.69d: validate behavior semantically instead of matching a historical
# method body byte-for-byte.
# ----------------------------------------------------------------------
$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")
$activeDecl='        private bool _asterMaxRenderRequestActive;'
$pendingDecl='        private bool _asterMaxRenderPending;'
$scheduledDecl='        private bool _asterMaxRenderScheduled;'
if(-not $v.Contains($activeDecl) -or -not $v.Contains($pendingDecl)){ throw 'C10.42 C10.30 render guard fields missing.' }
if(-not $v.Contains('_asterMaxRenderScheduled')){
    $v=$v.Replace($pendingDecl,$pendingDecl+"`n"+$scheduledDecl)
}

$signature='        private void RenderSceene()'
$methodStart=$v.IndexOf($signature)
if($methodStart -lt 0){ throw 'C10.42 RenderSceene method missing.' }
$braceStart=$v.IndexOf('{',$methodStart)
if($braceStart -lt 0){ throw 'C10.42 RenderSceene opening brace missing.' }
$depth=0; $methodEnd=-1
for($n=$braceStart; $n -lt $v.Length; $n++){
    if($v[$n] -eq '{'){ $depth++ }
    elseif($v[$n] -eq '}'){ $depth--; if($depth -eq 0){ $methodEnd=$n+1; break } }
}
if($methodEnd -lt 0){ throw 'C10.42 RenderSceene closing brace missing.' }
$currentRender=$v.Substring($methodStart,$methodEnd-$methodStart)
$required=@('if (!_renderingOn || IsDisposed || !IsHandleCreated) return;','if (_asterMaxRenderRequestActive)','_asterMaxRenderPending = true;','BeginInvoke(new Action(RenderSceene));')
foreach($token in $required){ if(-not $currentRender.Contains($token)){ throw "C10.42 RenderSceene semantic prerequisite missing: $token" } }
if(-not $currentRender.Contains('C10.42 large-assembly path: one queued paint')){
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
}
Set-Content $vtkPath $v -Encoding UTF8

# ----------------------------------------------------------------------
# 2. Treat a STEP/IGES/BREP assembly as one import transaction.
# ----------------------------------------------------------------------
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$stateAnchor='        [NonSerialized] protected bool _animating;'
if(-not $c.Contains('_asterMaxCadImportDepth')){
    if(-not $c.Contains($stateAnchor)){ throw 'C10.42 Controller state anchor missing.' }
    $c=$c.Replace($stateAnchor,$stateAnchor+"`n        [NonSerialized] private int _asterMaxCadImportDepth;")
}
$methodStartOld="        public string[] ImportCADAssemblyFile(string assemblyFileName, string splitCommand)`n        {`n            string[] filesToImport = SplitAssembly(assemblyFileName, splitCommand);"
$methodStartNew="        public string[] ImportCADAssemblyFile(string assemblyFileName, string splitCommand)`n        {`n            bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;`n            _asterMaxCadImportDepth++;`n            var asterMaxCadImportWatch = System.Diagnostics.Stopwatch.StartNew();`n            try`n            {`n                string[] filesToImport = SplitAssembly(assemblyFileName, splitCommand);`n                if (asterMaxTopLevelCadImport)`n                    _form.WriteDataToOutput(\"AsterMax CAD split: \" +`n                        (filesToImport == null ? 0 : filesToImport.Length) + \" item(s) temporales.\");"
if(-not $c.Contains('bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;')){
    if(-not $c.Contains($methodStartOld)){ throw 'C10.42 ImportCADAssemblyFile start anchor missing.' }
    $c=$c.Replace($methodStartOld,$methodStartNew)
    $methodEndOld="            return allAddedPartNames.ToArray();`n        }`n        //`n        public string[] SplitAssembly(string assemblyFileName, string splitCommand)"
    $methodEndNew="                asterMaxCadImportWatch.Stop();`n                if (asterMaxTopLevelCadImport)`n                    _form.WriteDataToOutput(\"AsterMax CAD import: \" + allAddedPartNames.Count +`n                        \" pieza(s) preparadas en \" + asterMaxCadImportWatch.ElapsedMilliseconds +`n                        \" ms. Visualización final diferida hasta completar el conjunto.\");`n                return allAddedPartNames.ToArray();`n            }`n            finally`n            {`n                _asterMaxCadImportDepth--;`n            }`n        }`n        //`n        public string[] SplitAssembly(string assemblyFileName, string splitCommand)"
    if(-not $c.Contains($methodEndOld)){ throw 'C10.42 ImportCADAssemblyFile end anchor missing.' }
    $c=$c.Replace($methodEndOld,$methodEndNew)
}
$compoundMethod=$c.IndexOf('        private void ImportBrepCompoundPart(')
if($compoundMethod -lt 0){ throw 'C10.42 ImportBrepCompoundPart method missing.' }
$compoundUpdate='            UpdateAfterImport(".brep");'
$compoundUpdatePos=$c.IndexOf($compoundUpdate,$compoundMethod)
if($compoundUpdatePos -lt 0 -and -not $c.Contains('if (_asterMaxCadImportDepth == 0)')){ throw 'C10.42 compound UpdateAfterImport anchor missing.' }
if($compoundUpdatePos -ge 0){ $c=$c.Substring(0,$compoundUpdatePos)+'            if (_asterMaxCadImportDepth == 0)'+"`n"+'                UpdateAfterImport(".brep");'+$c.Substring($compoundUpdatePos+$compoundUpdate.Length) }
$importAnchor="                _currentView = ViewGeometryModelResults.Geometry;`n                _form.SetCurrentView(_currentView);`n                DrawGeometry(false);"
$importNew="                _currentView = ViewGeometryModelResults.Geometry;`n                _form.SetCurrentView(_currentView);`n`n                // Keep the CAD/BREP exact; only simplify the initial graphics path.`n                int asterMaxLargeAssemblyThreshold = 80;`n                string asterMaxThresholdText = Environment.GetEnvironmentVariable(\"ASTERMAX_LARGE_ASSEMBLY_PARTS\");`n                int asterMaxConfiguredThreshold;`n                if (!String.IsNullOrWhiteSpace(asterMaxThresholdText) && Int32.TryParse(asterMaxThresholdText, out asterMaxConfiguredThreshold) && asterMaxConfiguredThreshold > 1) asterMaxLargeAssemblyThreshold = asterMaxConfiguredThreshold;`n                int asterMaxGeometryPartCount = (_model != null && _model.Geometry != null && _model.Geometry.Parts != null) ? _model.Geometry.Parts.Count : 0;`n                if (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold) CurrentEdgesVisibility = vtkEdgesVisibility.NoEdges;`n                if (_asterMaxCadImportDepth == 0) _form.WriteDataToOutput(\"AsterMax visualización CAD: \" + asterMaxGeometryPartCount + \" pieza(s); render inicial \" + (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold ? \"sin aristas.\" : \"normal.\"));`n                DrawGeometry(false);"
if(-not $c.Contains('ASTERMAX_LARGE_ASSEMBLY_PARTS')){ if(-not $c.Contains($importAnchor)){ throw 'C10.42 CAD import draw anchor missing.' }; $c=$c.Replace($importAnchor,$importNew) }
Set-Content $controllerPath $c -Encoding UTF8

# 4. Camera-only post import finalization.
$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")
$signature2='        private void AsterMaxCenterImportedGeometry()'
$ms=$u.IndexOf($signature2); if($ms -lt 0){ throw 'C10.42 AsterMaxCenterImportedGeometry missing.' }
$bs=$u.IndexOf('{',$ms); $depth=0; $me=-1
for($n=$bs; $n -lt $u.Length; $n++){ if($u[$n] -eq '{'){ $depth++ } elseif($u[$n] -eq '}'){ $depth--; if($depth -eq 0){ $me=$n+1; break } } }
if($me -lt 0){ throw 'C10.42 center method closing brace missing.' }
$existing=$u.Substring($ms,$me-$ms)
if(-not $existing.Contains('Geometry actors are already created by UpdateAfterImport')){
$centerNew=@'
        private void AsterMaxCenterImportedGeometry()
        {
            if (InvokeRequired) { BeginInvoke(new Action(AsterMaxCenterImportedGeometry)); return; }
            if (_controller == null || _vtk == null || _vtk.IsDisposed) return;
            // Geometry actors are already created by UpdateAfterImport. Do not redraw.
            UpdateVtkControlSize();
            _vtk.RenderingOn = true; _vtk.Visible = true; _vtk.Enabled = true; _vtk.BringToFront();
            BeginInvoke(new Action(() => { if (_vtk == null || _vtk.IsDisposed) return; _vtk.SetIsometricView(false, true); _vtk.SetZoomToFit(false); _vtk.Refresh(); }));
        }
'@
    $u=$u.Substring(0,$ms)+$centerNew.TrimEnd()+$u.Substring($me)
}
Set-Content $uiPath $u -Encoding UTF8
Write-Host 'C10.42: semantic render coalescing + single CAD import transaction + camera-only finalization applied.' -ForegroundColor Green
