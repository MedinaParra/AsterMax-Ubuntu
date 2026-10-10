param([string]$Root)
$ErrorActionPreference='Stop'

$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
foreach($p in @($controllerPath,$vtkPath,$uiPath)){ if(!(Test-Path $p)){ throw "C10.43 missing: $p" } }

# C10.43 does not alter CAD tolerances, FEM meshing, contacts, loads or solver behavior.
# It adds measurement around the already-existing C10.42 import/graphics path so that
# preparation time cannot be confused with time-to-visible/interactable viewport.

# ----------------------------------------------------------------------
# 1. Controller: end-to-end CAD-open transaction telemetry.
# ----------------------------------------------------------------------
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$fieldAnchor='        [NonSerialized] private int _asterMaxCadImportDepth;'
$fieldBlock=@'
        [NonSerialized] private int _asterMaxCadImportDepth;
        [NonSerialized] private System.Diagnostics.Stopwatch _asterMaxCadOpenWatch;
        [NonSerialized] private string _asterMaxCadSourceFile;
        [NonSerialized] private string _asterMaxCadSourceSha256;
        [NonSerialized] private long _asterMaxCadSplitMs;
        [NonSerialized] private long _asterMaxCadBrepVisualizationMs;
        [NonSerialized] private long _asterMaxCadModelIncorporationMs;
        [NonSerialized] private long _asterMaxCadSceneBuildMs;
        [NonSerialized] private int _asterMaxCadExternalProcessCount;
        [NonSerialized] private int _asterMaxCadBrepVisualizationCount;
        [NonSerialized] private int _asterMaxCadUpdateAfterImportCount;
        [NonSerialized] private int _asterMaxCadRedrawCount;
        [NonSerialized] private int _asterMaxCadImportedPartCount;
'@
if(-not $c.Contains('_asterMaxCadOpenWatch')){
    if(-not $c.Contains($fieldAnchor)){ throw 'C10.43 Controller C10.42 import-depth field missing.' }
    $c=$c.Replace($fieldAnchor,$fieldBlock.TrimEnd())
}

$importStart=@'
            bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;
            _asterMaxCadImportDepth++;
            var asterMaxCadImportWatch = System.Diagnostics.Stopwatch.StartNew();
'@
$importStartNew=@'
            bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;
            if (asterMaxTopLevelCadImport)
            {
                AsterMaxBeginCadOpenTelemetry(assemblyFileName);
                _form.AsterMaxResetCadViewportCounters();
            }
            _asterMaxCadImportDepth++;
            var asterMaxCadImportWatch = System.Diagnostics.Stopwatch.StartNew();
'@
if(-not $c.Contains('AsterMaxBeginCadOpenTelemetry(assemblyFileName);')){
    if(-not $c.Contains($importStart.TrimEnd())){ throw 'C10.43 ImportCADAssemblyFile C10.42 start anchor missing.' }
    $c=$c.Replace($importStart.TrimEnd(),$importStartNew.TrimEnd())
}

$preparedLog=@'
                    _form.WriteDataToOutput("AsterMax CAD import: " + allAddedPartNames.Count +
                        " pieza(s) preparadas en " + asterMaxCadImportWatch.ElapsedMilliseconds +
                        " ms. Visualización final diferida hasta completar el conjunto.");
'@
$preparedLogNew=@'
                    _asterMaxCadImportedPartCount = allAddedPartNames.Count;
                    _form.WriteDataToOutput("AsterMax CAD import: " + allAddedPartNames.Count +
                        " pieza(s) preparadas en " + asterMaxCadImportWatch.ElapsedMilliseconds +
                        " ms. Este valor NO es el tiempo total de apertura; la medición continúa hasta el viewport final.");
'@
if(-not $c.Contains('Este valor NO es el tiempo total de apertura')){
    if(-not $c.Contains($preparedLog.TrimEnd())){ throw 'C10.43 C10.42 prepared log anchor missing.' }
    $c=$c.Replace($preparedLog.TrimEnd(),$preparedLogNew.TrimEnd())
}

# Split STEP/IGES/BREP external process timing.
$splitSubmit=@'
            _netgenJob = new NetgenJob("SplitStep", executable, argument, settings.WorkDirectory);
            _netgenJob.AppendOutput += netgenJob_AppendOutput;
            _netgenJob.Submit();
'@
$splitSubmitNew=@'
            _netgenJob = new NetgenJob("SplitStep", executable, argument, settings.WorkDirectory);
            _netgenJob.AppendOutput += netgenJob_AppendOutput;
            var asterMaxSplitWatch = System.Diagnostics.Stopwatch.StartNew();
            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning)
                _asterMaxCadExternalProcessCount++;
            _netgenJob.Submit();
            asterMaxSplitWatch.Stop();
            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning)
                _asterMaxCadSplitMs += asterMaxSplitWatch.ElapsedMilliseconds;
'@
if(-not $c.Contains('asterMaxSplitWatch')){
    if(-not $c.Contains($splitSubmit.TrimEnd())){ throw 'C10.43 SplitAssembly Netgen anchor missing.' }
    $c=$c.Replace($splitSubmit.TrimEnd(),$splitSubmitNew.TrimEnd())
}

# Per-BREP visualization/tessellation external process timing.
$brepSubmit=@'
            _netgenJob = new NetgenJob("Brep", executable, argument, calculixSettings.WorkDirectory);
            _netgenJob.AppendOutput += netgenJob_AppendOutput;
            _netgenJob.Submit();
'@
$brepSubmitNew=@'
            _netgenJob = new NetgenJob("Brep", executable, argument, calculixSettings.WorkDirectory);
            _netgenJob.AppendOutput += netgenJob_AppendOutput;
            var asterMaxBrepWatch = System.Diagnostics.Stopwatch.StartNew();
            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning)
            {
                _asterMaxCadExternalProcessCount++;
                _asterMaxCadBrepVisualizationCount++;
            }
            _netgenJob.Submit();
            asterMaxBrepWatch.Stop();
            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning)
                _asterMaxCadBrepVisualizationMs += asterMaxBrepWatch.ElapsedMilliseconds;
'@
if(-not $c.Contains('asterMaxBrepWatch')){
    if(-not $c.Contains($brepSubmit.TrimEnd())){ throw 'C10.43 BREP_VISUALIZATION Netgen anchor missing.' }
    $c=$c.Replace($brepSubmit.TrimEnd(),$brepSubmitNew.TrimEnd())
}

$modelImport='                string[] addedPartNames = _model.ImportGeometryFromBrepFile(visFileName, brepFileName);'
$modelImportNew=@'
                var asterMaxModelWatch = System.Diagnostics.Stopwatch.StartNew();
                string[] addedPartNames = _model.ImportGeometryFromBrepFile(visFileName, brepFileName);
                asterMaxModelWatch.Stop();
                if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning)
                    _asterMaxCadModelIncorporationMs += asterMaxModelWatch.ElapsedMilliseconds;
'@
if(-not $c.Contains('asterMaxModelWatch')){
    if(-not $c.Contains($modelImport)){ throw 'C10.43 BREP model incorporation anchor missing.' }
    $c=$c.Replace($modelImport,$modelImportNew.TrimEnd())
}

# Measure final geometry scene build separately from BREP conversion.
$sceneAnchor=@'
                if (_asterMaxCadImportDepth == 0)
                    _form.WriteDataToOutput("AsterMax visualización CAD: " + asterMaxGeometryPartCount +
                        " pieza(s); render inicial " +
                        (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold ? "sin aristas." : "normal."));
                DrawGeometry(false);
'@
$sceneNew=@'
                if (_asterMaxCadImportDepth == 0)
                    _form.WriteDataToOutput("AsterMax visualización CAD: " + asterMaxGeometryPartCount +
                        " pieza(s); render inicial " +
                        (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold ? "sin aristas." : "normal."));
                var asterMaxSceneWatch = System.Diagnostics.Stopwatch.StartNew();
                DrawGeometry(false);
                asterMaxSceneWatch.Stop();
                if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning)
                    _asterMaxCadSceneBuildMs += asterMaxSceneWatch.ElapsedMilliseconds;
'@
if(-not $c.Contains('asterMaxSceneWatch')){
    if(-not $c.Contains($sceneAnchor.TrimEnd())){ throw 'C10.43 C10.42 scene-build anchor missing.' }
    $c=$c.Replace($sceneAnchor.TrimEnd(),$sceneNew.TrimEnd())
}

$updateAnchor=@'
        private void UpdateAfterImport(string extension)
        {
'@
$updateNew=@'
        private void UpdateAfterImport(string extension)
        {
            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning)
                _asterMaxCadUpdateAfterImportCount++;
'@
if(-not $c.Contains('_asterMaxCadUpdateAfterImportCount++;')){
    if(-not $c.Contains($updateAnchor.TrimEnd())){ throw 'C10.43 UpdateAfterImport anchor missing.' }
    $c=$c.Replace($updateAnchor.TrimEnd(),$updateNew.TrimEnd())
}

$redrawAnchor=@'
        public void Redraw(bool resetCamera = false)
        {
'@
$redrawNew=@'
        public void Redraw(bool resetCamera = false)
        {
            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning)
                _asterMaxCadRedrawCount++;
'@
if(-not $c.Contains('_asterMaxCadRedrawCount++;')){
    if(-not $c.Contains($redrawAnchor.TrimEnd())){ throw 'C10.43 Redraw anchor missing.' }
    $c=$c.Replace($redrawAnchor.TrimEnd(),$redrawNew.TrimEnd())
}

$splitMethod='        public string[] SplitAssembly(string assemblyFileName, string splitCommand)'
$telemetryMethods=@'
        private void AsterMaxBeginCadOpenTelemetry(string fileName)
        {
            _asterMaxCadSourceFile = fileName;
            _asterMaxCadSourceSha256 = null;
            _asterMaxCadSplitMs = 0;
            _asterMaxCadBrepVisualizationMs = 0;
            _asterMaxCadModelIncorporationMs = 0;
            _asterMaxCadSceneBuildMs = 0;
            _asterMaxCadExternalProcessCount = 0;
            _asterMaxCadBrepVisualizationCount = 0;
            _asterMaxCadUpdateAfterImportCount = 0;
            _asterMaxCadRedrawCount = 0;
            _asterMaxCadImportedPartCount = 0;
            try
            {
                using (var stream = System.IO.File.OpenRead(fileName))
                using (var sha = System.Security.Cryptography.SHA256.Create())
                    _asterMaxCadSourceSha256 = System.BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
            }
            catch (Exception ex)
            {
                _asterMaxCadSourceSha256 = "ERROR:" + ex.GetType().Name;
            }
            _asterMaxCadOpenWatch = System.Diagnostics.Stopwatch.StartNew();
            _form.WriteDataToOutput("AsterMax PERF CAD begin: file=" + System.IO.Path.GetFileName(fileName) +
                "; sha256=" + _asterMaxCadSourceSha256 + "; process=" + System.Diagnostics.Process.GetCurrentProcess().Id);
        }

        public void AsterMaxCompleteCadOpenTelemetry(long vtkRenderRequests, long vtkAddCells,
                                                     long vtkCameraAdjustRedraws)
        {
            if (_asterMaxCadOpenWatch == null || !_asterMaxCadOpenWatch.IsRunning) return;
            _asterMaxCadOpenWatch.Stop();
            var process = System.Diagnostics.Process.GetCurrentProcess();
            long workingSetMb = process.WorkingSet64 / (1024L * 1024L);
            long peakWorkingSetMb = process.PeakWorkingSet64 / (1024L * 1024L);
            _form.WriteDataToOutput("AsterMax PERF CAD complete: total_to_visible_refresh_ms=" + _asterMaxCadOpenWatch.ElapsedMilliseconds +
                "; split_ms=" + _asterMaxCadSplitMs +
                "; brep_visualization_ms=" + _asterMaxCadBrepVisualizationMs +
                "; model_incorporation_ms=" + _asterMaxCadModelIncorporationMs +
                "; scene_build_ms=" + _asterMaxCadSceneBuildMs +
                "; parts=" + _asterMaxCadImportedPartCount +
                "; brep_jobs=" + _asterMaxCadBrepVisualizationCount +
                "; external_processes=" + _asterMaxCadExternalProcessCount +
                "; update_after_import=" + _asterMaxCadUpdateAfterImportCount +
                "; controller_redraw=" + _asterMaxCadRedrawCount +
                "; vtk_render_requests=" + vtkRenderRequests +
                "; vtk_add_cells=" + vtkAddCells +
                "; vtk_camera_adjust_redraw=" + vtkCameraAdjustRedraws +
                "; working_set_mb=" + workingSetMb +
                "; peak_working_set_mb=" + peakWorkingSetMb +
                "; sha256=" + _asterMaxCadSourceSha256);
        }

'@
if(-not $c.Contains('public void AsterMaxCompleteCadOpenTelemetry')){
    if(-not $c.Contains($splitMethod)){ throw 'C10.43 SplitAssembly method anchor missing for telemetry methods.' }
    $c=$c.Replace($splitMethod,$telemetryMethods+$splitMethod)
}
Set-Content $controllerPath $c -Encoding UTF8

# ----------------------------------------------------------------------
# 2. vtkControl: count requests and expensive per-actor camera path.
# These are counters only; scene mutation remains on the owning UI thread.
# ----------------------------------------------------------------------
$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")
$vtkField='        private bool _asterMaxRenderScheduled;'
$vtkFields=@'
        private bool _asterMaxRenderScheduled;
        private long _asterMaxPerfRenderRequests;
        private long _asterMaxPerfAddCells;
        private long _asterMaxPerfCameraAdjustRedraws;
'@
if(-not $v.Contains('_asterMaxPerfRenderRequests')){
    if(-not $v.Contains($vtkField)){ throw 'C10.43 C10.42 VTK scheduled-render field missing.' }
    $v=$v.Replace($vtkField,$vtkFields.TrimEnd())
}

$userPickAnchor='        public bool UserPick { get { return _userPick; } set { _userPick = value; } }'
$vtkApi=@'
        public long AsterMaxPerfRenderRequests { get { return System.Threading.Interlocked.Read(ref _asterMaxPerfRenderRequests); } }
        public long AsterMaxPerfAddCells { get { return System.Threading.Interlocked.Read(ref _asterMaxPerfAddCells); } }
        public long AsterMaxPerfCameraAdjustRedraws { get { return System.Threading.Interlocked.Read(ref _asterMaxPerfCameraAdjustRedraws); } }
        public void AsterMaxResetPerfCounters()
        {
            System.Threading.Interlocked.Exchange(ref _asterMaxPerfRenderRequests, 0);
            System.Threading.Interlocked.Exchange(ref _asterMaxPerfAddCells, 0);
            System.Threading.Interlocked.Exchange(ref _asterMaxPerfCameraAdjustRedraws, 0);
        }

'@
if(-not $v.Contains('public void AsterMaxResetPerfCounters()')){
    if(-not $v.Contains($userPickAnchor)){ throw 'C10.43 vtkControl UserPick anchor missing.' }
    $v=$v.Replace($userPickAnchor,$vtkApi+$userPickAnchor)
}

$renderAnchor=@'
        private void RenderSceene()
        {
            if (!_renderingOn || IsDisposed || !IsHandleCreated) return;
'@
$renderNew=@'
        private void RenderSceene()
        {
            System.Threading.Interlocked.Increment(ref _asterMaxPerfRenderRequests);
            if (!_renderingOn || IsDisposed || !IsHandleCreated) return;
'@
if(-not $v.Contains('Interlocked.Increment(ref _asterMaxPerfRenderRequests)')){
    if(-not $v.Contains($renderAnchor.TrimEnd())){ throw 'C10.43 C10.42 RenderSceene anchor missing.' }
    $v=$v.Replace($renderAnchor.TrimEnd(),$renderNew.TrimEnd())
}

$addCellsAnchor=@'
        public void AddCells(vtkMaxActorData data)
        {
            // Create actor
'@
$addCellsNew=@'
        public void AddCells(vtkMaxActorData data)
        {
            System.Threading.Interlocked.Increment(ref _asterMaxPerfAddCells);
            // Create actor
'@
if(-not $v.Contains('Interlocked.Increment(ref _asterMaxPerfAddCells)')){
    if(-not $v.Contains($addCellsAnchor.TrimEnd())){ throw 'C10.43 AddCells anchor missing.' }
    $v=$v.Replace($addCellsAnchor.TrimEnd(),$addCellsNew.TrimEnd())
}

$cameraAnchor=@'
        public void AdjustCameraDistanceAndClippingRedraw()
        {
            _style.AdjustCameraDistanceAndClipping();
'@
$cameraNew=@'
        public void AdjustCameraDistanceAndClippingRedraw()
        {
            System.Threading.Interlocked.Increment(ref _asterMaxPerfCameraAdjustRedraws);
            _style.AdjustCameraDistanceAndClipping();
'@
if(-not $v.Contains('Interlocked.Increment(ref _asterMaxPerfCameraAdjustRedraws)')){
    if(-not $v.Contains($cameraAnchor.TrimEnd())){ throw 'C10.43 camera-adjust redraw anchor missing.' }
    $v=$v.Replace($cameraAnchor.TrimEnd(),$cameraNew.TrimEnd())
}
Set-Content $vtkPath $v -Encoding UTF8

# ----------------------------------------------------------------------
# 3. Native WinForms bridge: reset VTK counters at transaction start and mark
# completion only after the final camera fit + synchronous Refresh returns.
# ----------------------------------------------------------------------
$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")
$centerSignature='        private void AsterMaxCenterImportedGeometry()'
$resetMethod=@'
        public void AsterMaxResetCadViewportCounters()
        {
            if (InvokeRequired)
            {
                Invoke(new Action(AsterMaxResetCadViewportCounters));
                return;
            }
            if (_vtk != null && !_vtk.IsDisposed) _vtk.AsterMaxResetPerfCounters();
        }

'@
if(-not $u.Contains('public void AsterMaxResetCadViewportCounters()')){
    if(-not $u.Contains($centerSignature)){ throw 'C10.43 center method anchor missing for reset API.' }
    $u=$u.Replace($centerSignature,$resetMethod+$centerSignature)
}

$finalRefresh=@'
                _vtk.SetIsometricView(false, true);
                _vtk.SetZoomToFit(false);
                _vtk.Refresh();
'@
$finalRefreshNew=@'
                _vtk.SetIsometricView(false, true);
                _vtk.SetZoomToFit(false);
                _vtk.Refresh();
                if (_controller != null)
                    _controller.AsterMaxCompleteCadOpenTelemetry(_vtk.AsterMaxPerfRenderRequests,
                        _vtk.AsterMaxPerfAddCells, _vtk.AsterMaxPerfCameraAdjustRedraws);
'@
if(-not $u.Contains('AsterMaxCompleteCadOpenTelemetry(_vtk.AsterMaxPerfRenderRequests')){
    if(-not $u.Contains($finalRefresh.TrimEnd())){ throw 'C10.43 final viewport refresh anchor missing.' }
    $u=$u.Replace($finalRefresh.TrimEnd(),$finalRefreshNew.TrimEnd())
}
Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.43: end-to-end CAD open telemetry applied (no FEM/CAD fidelity changes).' -ForegroundColor Green
