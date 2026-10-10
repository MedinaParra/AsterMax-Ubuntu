param([string]$Root)
$ErrorActionPreference='Stop'

$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
foreach($p in @($controllerPath,$vtkPath,$uiPath)){ if(!(Test-Path $p)){ throw "C10.43 missing: $p" } }

function To-Lf([string]$Text) { return [regex]::Replace($Text,"\r\n?","`n") }
function Replace-OnceRegex([string]$Text,[string]$Pattern,[string]$Replacement,[string]$Name) {
    $rx = [regex]::new($Pattern,[System.Text.RegularExpressions.RegexOptions]::Singleline)
    $matches = $rx.Matches($Text)
    if($matches.Count -ne 1){ throw "C10.43 $Name expected exactly 1 match, got $($matches.Count)." }
    return $rx.Replace($Text,$Replacement,1)
}

# Instrumentation only. No CAD tolerances, FEM meshing, contacts, loads, solver,
# body identity, hierarchy, units or exact BREP data are changed by this patch.

# ----------------------------------------------------------------------
# Controller: one top-level CAD-open measurement transaction.
# ----------------------------------------------------------------------
$c = To-Lf (Get-Content $controllerPath -Raw)
if(-not $c.Contains('_asterMaxCadOpenWatch')) {
    $anchor='        [NonSerialized] private int _asterMaxCadImportDepth;'
    if(-not $c.Contains($anchor)){ throw 'C10.43 import-depth state anchor missing.' }
    $extra=@(
        '        [NonSerialized] private System.Diagnostics.Stopwatch _asterMaxCadOpenWatch;',
        '        [NonSerialized] private string _asterMaxCadSourceSha256;',
        '        [NonSerialized] private long _asterMaxCadSplitMs;',
        '        [NonSerialized] private long _asterMaxCadBrepVisualizationMs;',
        '        [NonSerialized] private long _asterMaxCadModelIncorporationMs;',
        '        [NonSerialized] private long _asterMaxCadSceneBuildMs;',
        '        [NonSerialized] private int _asterMaxCadNetgenSubmitCount;',
        '        [NonSerialized] private int _asterMaxCadBrepVisualizationCount;',
        '        [NonSerialized] private int _asterMaxCadUpdateAfterImportCount;',
        '        [NonSerialized] private int _asterMaxCadRedrawCount;',
        '        [NonSerialized] private int _asterMaxCadImportedPartCount;'
    ) -join "`n"
    $c=$c.Replace($anchor,$anchor+"`n"+$extra)
}

if(-not $c.Contains('AsterMaxBeginCadOpenTelemetry(assemblyFileName);')) {
    $old = '            bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;'+"`n"+
           '            _asterMaxCadImportDepth++;'+"`n"+
           '            var asterMaxCadImportWatch = System.Diagnostics.Stopwatch.StartNew();'
    if(-not $c.Contains($old)){ throw 'C10.43 ImportCADAssemblyFile transaction start anchor missing.' }
    $new = '            bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;'+"`n"+
           '            if (asterMaxTopLevelCadImport)'+"`n"+
           '            {'+"`n"+
           '                AsterMaxBeginCadOpenTelemetry(assemblyFileName);'+"`n"+
           '                _form.AsterMaxResetCadViewportCounters();'+"`n"+
           '            }'+"`n"+
           '            _asterMaxCadImportDepth++;'+"`n"+
           '            var asterMaxCadImportWatch = System.Diagnostics.Stopwatch.StartNew();'
    $c=$c.Replace($old,$new)
}

if(-not $c.Contains('Este valor NO es el tiempo total de apertura')) {
    $logAnchor='                    _form.WriteDataToOutput("AsterMax CAD import: " + allAddedPartNames.Count +'
    if(-not $c.Contains($logAnchor)){ throw 'C10.43 C10.42 prepared-import log anchor missing.' }
    $c=$c.Replace($logAnchor,'                    _asterMaxCadImportedPartCount = allAddedPartNames.Count;'+"`n"+$logAnchor)
    $c=$c.Replace('                        " ms. Visualización final diferida hasta completar el conjunto.");',
                  '                        " ms. Este valor NO es el tiempo total de apertura; la medición continúa hasta el refresh final del viewport.");')
}

# SplitAssembly: Netgen STEP decomposition job duration.
if(-not $c.Contains('asterMaxSplitWatch')) {
    $pattern='(?<prefix>\s*_netgenJob = new NetgenJob\("SplitStep", executable, argument, settings\.WorkDirectory\);\s*\n\s*_netgenJob\.AppendOutput \+= netgenJob_AppendOutput;\s*\n)(?<submit>\s*_netgenJob\.Submit\(\);)'
    $replacement='${prefix}            var asterMaxSplitWatch = System.Diagnostics.Stopwatch.StartNew();'+"`n"+
                 '            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning) _asterMaxCadNetgenSubmitCount++;'+"`n"+
                 '            _netgenJob.Submit();'+"`n"+
                 '            asterMaxSplitWatch.Stop();'+"`n"+
                 '            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning) _asterMaxCadSplitMs += asterMaxSplitWatch.ElapsedMilliseconds;'
    $c=Replace-OnceRegex $c $pattern $replacement 'SplitStep Netgen submit'
}

# ImportBrepPartFile: per-part BREP_VISUALIZATION job duration.
if(-not $c.Contains('asterMaxBrepWatch')) {
    $pattern='(?<prefix>\s*_netgenJob = new NetgenJob\("Brep", executable, argument, calculixSettings\.WorkDirectory\);\s*\n\s*_netgenJob\.AppendOutput \+= netgenJob_AppendOutput;\s*\n)(?<submit>\s*_netgenJob\.Submit\(\);)'
    $replacement='${prefix}            var asterMaxBrepWatch = System.Diagnostics.Stopwatch.StartNew();'+"`n"+
                 '            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning)'+"`n"+
                 '            {'+"`n"+
                 '                _asterMaxCadNetgenSubmitCount++;'+"`n"+
                 '                _asterMaxCadBrepVisualizationCount++;'+"`n"+
                 '            }'+"`n"+
                 '            _netgenJob.Submit();'+"`n"+
                 '            asterMaxBrepWatch.Stop();'+"`n"+
                 '            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning) _asterMaxCadBrepVisualizationMs += asterMaxBrepWatch.ElapsedMilliseconds;'
    $c=Replace-OnceRegex $c $pattern $replacement 'BREP_VISUALIZATION Netgen submit'
}

if(-not $c.Contains('asterMaxModelWatch')) {
    $old='                string[] addedPartNames = _model.ImportGeometryFromBrepFile(visFileName, brepFileName);'
    if(-not $c.Contains($old)){ throw 'C10.43 model incorporation anchor missing.' }
    $new='                var asterMaxModelWatch = System.Diagnostics.Stopwatch.StartNew();'+"`n"+
         $old+"`n"+
         '                asterMaxModelWatch.Stop();'+"`n"+
         '                if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning) _asterMaxCadModelIncorporationMs += asterMaxModelWatch.ElapsedMilliseconds;'
    $c=$c.Replace($old,$new)
}

if(-not $c.Contains('asterMaxSceneWatch')) {
    $pattern='(?<log>\s*if \(_asterMaxCadImportDepth == 0\)\s*\n\s*_form\.WriteDataToOutput\("AsterMax visualización CAD:".*?\);\s*\n)\s*DrawGeometry\(false\);'
    $replacement='${log}                var asterMaxSceneWatch = System.Diagnostics.Stopwatch.StartNew();'+"`n"+
                 '                DrawGeometry(false);'+"`n"+
                 '                asterMaxSceneWatch.Stop();'+"`n"+
                 '                if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning) _asterMaxCadSceneBuildMs += asterMaxSceneWatch.ElapsedMilliseconds;'
    $c=Replace-OnceRegex $c $pattern $replacement 'final geometry scene build'
}

if(-not $c.Contains('_asterMaxCadUpdateAfterImportCount++;')) {
    $pattern='(?<sig>        private void UpdateAfterImport\(string extension\)\s*\n\s*\{)'
    $replacement='${sig}'+"`n"+'            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning) _asterMaxCadUpdateAfterImportCount++;'
    $c=Replace-OnceRegex $c $pattern $replacement 'UpdateAfterImport counter'
}
if(-not $c.Contains('_asterMaxCadRedrawCount++;')) {
    $pattern='(?<sig>        public void Redraw\(bool resetCamera = false\)\s*\n\s*\{)'
    $replacement='${sig}'+"`n"+'            if (_asterMaxCadOpenWatch != null && _asterMaxCadOpenWatch.IsRunning) _asterMaxCadRedrawCount++;'
    $c=Replace-OnceRegex $c $pattern $replacement 'Controller.Redraw counter'
}

if(-not $c.Contains('public void AsterMaxCompleteCadOpenTelemetry')) {
    $splitAnchor='        public string[] SplitAssembly(string assemblyFileName, string splitCommand)'
    if(-not $c.Contains($splitAnchor)){ throw 'C10.43 SplitAssembly insertion anchor missing.' }
    $methods=@'
        private void AsterMaxBeginCadOpenTelemetry(string fileName)
        {
            _asterMaxCadSourceSha256 = null;
            _asterMaxCadSplitMs = 0;
            _asterMaxCadBrepVisualizationMs = 0;
            _asterMaxCadModelIncorporationMs = 0;
            _asterMaxCadSceneBuildMs = 0;
            _asterMaxCadNetgenSubmitCount = 0;
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

        public void AsterMaxCompleteCadOpenTelemetry(long vtkRenderRequests, long vtkAddCells, long vtkCameraAdjustRedraws)
        {
            if (_asterMaxCadOpenWatch == null || !_asterMaxCadOpenWatch.IsRunning) return;
            _asterMaxCadOpenWatch.Stop();
            var process = System.Diagnostics.Process.GetCurrentProcess();
            long workingSetMb = process.WorkingSet64 / (1024L * 1024L);
            long processPeakWorkingSetMb = process.PeakWorkingSet64 / (1024L * 1024L);
            _form.WriteDataToOutput("AsterMax PERF CAD complete: total_to_visible_refresh_ms=" + _asterMaxCadOpenWatch.ElapsedMilliseconds +
                "; split_ms=" + _asterMaxCadSplitMs +
                "; brep_visualization_ms=" + _asterMaxCadBrepVisualizationMs +
                "; model_incorporation_ms=" + _asterMaxCadModelIncorporationMs +
                "; scene_build_ms=" + _asterMaxCadSceneBuildMs +
                "; parts=" + _asterMaxCadImportedPartCount +
                "; brep_jobs=" + _asterMaxCadBrepVisualizationCount +
                "; netgen_job_submits=" + _asterMaxCadNetgenSubmitCount +
                "; update_after_import=" + _asterMaxCadUpdateAfterImportCount +
                "; controller_redraw=" + _asterMaxCadRedrawCount +
                "; vtk_render_requests=" + vtkRenderRequests +
                "; vtk_add_cells=" + vtkAddCells +
                "; vtk_camera_adjust_redraw=" + vtkCameraAdjustRedraws +
                "; working_set_mb=" + workingSetMb +
                "; process_peak_working_set_mb=" + processPeakWorkingSetMb +
                "; sha256=" + _asterMaxCadSourceSha256);
        }

'@
    $methods=To-Lf $methods
    $c=$c.Replace($splitAnchor,$methods+$splitAnchor)
}
Set-Content $controllerPath $c -Encoding UTF8

# ----------------------------------------------------------------------
# vtkControl: counters only; no ownership/threading behavior changed.
# ----------------------------------------------------------------------
$v=To-Lf (Get-Content $vtkPath -Raw)
if(-not $v.Contains('_asterMaxPerfRenderRequests')) {
    $anchor='        private bool _asterMaxRenderScheduled;'
    if(-not $v.Contains($anchor)){ throw 'C10.43 C10.42 render-scheduled field missing.' }
    $v=$v.Replace($anchor,$anchor+"`n"+
        '        private long _asterMaxPerfRenderRequests;'+"`n"+
        '        private long _asterMaxPerfAddCells;'+"`n"+
        '        private long _asterMaxPerfCameraAdjustRedraws;')
}
if(-not $v.Contains('public void AsterMaxResetPerfCounters()')) {
    $anchor='        public bool UserPick { get { return _userPick; } set { _userPick = value; } }'
    if(-not $v.Contains($anchor)){ throw 'C10.43 UserPick property anchor missing.' }
    $api=@'
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
    $api=To-Lf $api
    $v=$v.Replace($anchor,$api+$anchor)
}
if(-not $v.Contains('Interlocked.Increment(ref _asterMaxPerfRenderRequests)')) {
    $pattern='(?<sig>        private void RenderSceene\(\)\s*\n\s*\{)'
    $v=Replace-OnceRegex $v $pattern ('${sig}'+"`n"+'            System.Threading.Interlocked.Increment(ref _asterMaxPerfRenderRequests);') 'RenderSceene counter'
}
if(-not $v.Contains('Interlocked.Increment(ref _asterMaxPerfAddCells)')) {
    $pattern='(?<sig>        public void AddCells\(vtkMaxActorData data\)\s*\n\s*\{)'
    $v=Replace-OnceRegex $v $pattern ('${sig}'+"`n"+'            System.Threading.Interlocked.Increment(ref _asterMaxPerfAddCells);') 'AddCells counter'
}
if(-not $v.Contains('Interlocked.Increment(ref _asterMaxPerfCameraAdjustRedraws)')) {
    $pattern='(?<sig>        public void AdjustCameraDistanceAndClippingRedraw\(\)\s*\n\s*\{)'
    $v=Replace-OnceRegex $v $pattern ('${sig}'+"`n"+'            System.Threading.Interlocked.Increment(ref _asterMaxPerfCameraAdjustRedraws);') 'camera-adjust redraw counter'
}
Set-Content $vtkPath $v -Encoding UTF8

# ----------------------------------------------------------------------
# Native WinForms bridge: reset counters before import; stop timing after the
# existing final Refresh in AsterMaxCenterImportedGeometry. This is a UI-refresh
# boundary, not a claim of GPU presentation or progressive-refinement completion.
# ----------------------------------------------------------------------
$u=To-Lf (Get-Content $uiPath -Raw)
$centerSignature='        private void AsterMaxCenterImportedGeometry()'
if(-not $u.Contains('public void AsterMaxResetCadViewportCounters()')) {
    if(-not $u.Contains($centerSignature)){ throw 'C10.43 center method anchor missing.' }
    $reset=@'
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
    $reset=To-Lf $reset
    $u=$u.Replace($centerSignature,$reset+$centerSignature)
}
if(-not $u.Contains('AsterMaxCompleteCadOpenTelemetry(_vtk.AsterMaxPerfRenderRequests')) {
    $methodStart=$u.IndexOf($centerSignature)
    if($methodStart -lt 0){ throw 'C10.43 center method missing after reset insertion.' }
    $braceStart=$u.IndexOf('{',$methodStart)
    $depth=0; $methodEnd=-1
    for($n=$braceStart; $n -lt $u.Length; $n++) {
        if($u[$n] -eq '{'){ $depth++ }
        elseif($u[$n] -eq '}') { $depth--; if($depth -eq 0){ $methodEnd=$n+1; break } }
    }
    if($methodEnd -lt 0){ throw 'C10.43 center method closing brace missing.' }
    $center=$u.Substring($methodStart,$methodEnd-$methodStart)
    $old='                _vtk.SetIsometricView(false, true);'+"`n"+
         '                _vtk.SetZoomToFit(false);'+"`n"+
         '                _vtk.Refresh();'
    if(-not $center.Contains($old)){ throw 'C10.43 center final Refresh block missing.' }
    $new=$old+"`n"+
         '                if (_controller != null)'+"`n"+
         '                    _controller.AsterMaxCompleteCadOpenTelemetry(_vtk.AsterMaxPerfRenderRequests,'+"`n"+
         '                        _vtk.AsterMaxPerfAddCells, _vtk.AsterMaxPerfCameraAdjustRedraws);'
    $center=$center.Replace($old,$new)
    $u=$u.Substring(0,$methodStart)+$center+$u.Substring($methodEnd)
}
Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.43 v2: newline-safe end-to-end CAD-open telemetry applied.' -ForegroundColor Green
