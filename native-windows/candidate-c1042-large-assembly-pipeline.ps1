param([string]$Root)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
foreach($p in @($vtkPath,$controllerPath,$uiPath)){ if(!(Test-Path $p)){ throw "C10.42 missing: $p" } }

$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")
$activeDecl='        private bool _asterMaxRenderRequestActive;'
$pendingDecl='        private bool _asterMaxRenderPending;'
$scheduledDecl='        private bool _asterMaxRenderScheduled;'
if(-not $v.Contains($activeDecl) -or -not $v.Contains($pendingDecl)){ throw 'C10.42 C10.30 render guard fields missing.' }
if(-not $v.Contains('_asterMaxRenderScheduled')){ $v=$v.Replace($pendingDecl,$pendingDecl+"`n"+$scheduledDecl) }
$signature='        private void RenderSceene()'
$methodStart=$v.IndexOf($signature); if($methodStart -lt 0){ throw 'C10.42 RenderSceene method missing.' }
$braceStart=$v.IndexOf('{',$methodStart); if($braceStart -lt 0){ throw 'C10.42 RenderSceene opening brace missing.' }
$depth=0; $methodEnd=-1
for($n=$braceStart; $n -lt $v.Length; $n++){ if($v[$n] -eq '{'){ $depth++ } elseif($v[$n] -eq '}'){ $depth--; if($depth -eq 0){ $methodEnd=$n+1; break } } }
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

$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$stateAnchor='        [NonSerialized] protected bool _animating;'
if(-not $c.Contains('_asterMaxCadImportDepth')){ if(-not $c.Contains($stateAnchor)){ throw 'C10.42 Controller state anchor missing.' }; $c=$c.Replace($stateAnchor,$stateAnchor+"`n        [NonSerialized] private int _asterMaxCadImportDepth;") }
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
    $methodStartOld=$methodStartOld.TrimStart("`r","`n").Replace("`r`n","`n")
    $methodStartNew=$methodStartNew.TrimStart("`r","`n").Replace("`r`n","`n")
    if(-not $c.Contains($methodStartOld)){ throw 'C10.42 ImportCADAssemblyFile start anchor missing.' }
    $c=$c.Replace($methodStartOld,$methodStartNew)
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
    $methodEndOld=$methodEndOld.TrimStart("`r","`n").Replace("`r`n","`n")
    $methodEndNew=$methodEndNew.TrimStart("`r","`n").Replace("`r`n","`n")
    if(-not $c.Contains($methodEndOld)){ throw 'C10.42 ImportCADAssemblyFile end anchor missing.' }
    $c=$c.Replace($methodEndOld,$methodEndNew)
}
$compoundMethod=$c.IndexOf('        private void ImportBrepCompoundPart('); if($compoundMethod -lt 0){ throw 'C10.42 ImportBrepCompoundPart method missing.' }
$compoundUpdate='            UpdateAfterImport(".brep");'
$compoundUpdatePos=$c.IndexOf($compoundUpdate,$compoundMethod)
if($compoundUpdatePos -lt 0 -and -not $c.Contains('if (_asterMaxCadImportDepth == 0)')){ throw 'C10.42 compound UpdateAfterImport anchor missing.' }
if($compoundUpdatePos -ge 0){ $c=$c.Substring(0,$compoundUpdatePos)+'            if (_asterMaxCadImportDepth == 0)'+"`n"+'                UpdateAfterImport(".brep");'+$c.Substring($compoundUpdatePos+$compoundUpdate.Length) }
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
                if (!String.IsNullOrWhiteSpace(asterMaxThresholdText) && Int32.TryParse(asterMaxThresholdText, out asterMaxConfiguredThreshold) && asterMaxConfiguredThreshold > 1) asterMaxLargeAssemblyThreshold = asterMaxConfiguredThreshold;
                int asterMaxGeometryPartCount = (_model != null && _model.Geometry != null && _model.Geometry.Parts != null) ? _model.Geometry.Parts.Count : 0;
                if (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold) CurrentEdgesVisibility = vtkEdgesVisibility.NoEdges;
                if (_asterMaxCadImportDepth == 0) _form.WriteDataToOutput("AsterMax visualización CAD: " + asterMaxGeometryPartCount + " pieza(s); render inicial " + (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold ? "sin aristas." : "normal."));
                DrawGeometry(false);
'@
if(-not $c.Contains('ASTERMAX_LARGE_ASSEMBLY_PARTS')){ $importAnchor=$importAnchor.TrimStart("`r","`n").Replace("`r`n","`n"); $importNew=$importNew.TrimStart("`r","`n").Replace("`r`n","`n"); if(-not $c.Contains($importAnchor)){ throw 'C10.42 CAD import draw anchor missing.' }; $c=$c.Replace($importAnchor,$importNew) }
Set-Content $controllerPath $c -Encoding UTF8

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
