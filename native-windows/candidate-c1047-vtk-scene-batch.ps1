param([string]$Root)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
$mainPath = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
foreach($p in @($vtkPath,$mainPath,$controllerPath)){ if(!(Test-Path $p)){ throw "C10.47 missing: $p" } }

function Normalize-Lf([string]$text){ return [regex]::Replace($text,"\r\n?","`n") }
function Replace-CSharpMethod([string]$text,[string]$signature,[scriptblock]$transform){
    $start=$text.IndexOf($signature)
    if($start -lt 0){ throw "C10.47 method missing: $signature" }
    $brace=$text.IndexOf('{',$start)
    if($brace -lt 0){ throw "C10.47 opening brace missing: $signature" }
    $depth=0; $end=-1
    for($n=$brace; $n -lt $text.Length; $n++){
        if($text[$n] -eq '{'){ $depth++ }
        elseif($text[$n] -eq '}'){
            $depth--
            if($depth -eq 0){ $end=$n+1; break }
        }
    }
    if($end -lt 0){ throw "C10.47 closing brace missing: $signature" }
    $existing=$text.Substring($start,$end-$start)
    $replacement=& $transform $existing
    return $text.Substring(0,$start)+$replacement.TrimEnd()+$text.Substring($end)
}

# ----------------------------------------------------------------------
# vtkControl: defer per-actor camera+render work while a CAD scene is built.
# Scene mutation stays on the owning WinForms/VTK thread. Outside a batch,
# AddCells keeps its historical behavior unchanged.
# ----------------------------------------------------------------------
$v=Normalize-Lf (Get-Content $vtkPath -Raw)
$fieldAnchor='        private bool _asterMaxRenderScheduled;'
if(-not $v.Contains('_asterMaxSceneBatchDepth')){
    if(-not $v.Contains($fieldAnchor)){ throw 'C10.47 render scheduled field missing after C10.42.' }
    $fields=@'
        private bool _asterMaxRenderScheduled;
        private int _asterMaxSceneBatchDepth;
        private bool _asterMaxSceneBatchCameraDirty;
        private long _asterMaxSceneBatchDeferredCameraAdjusts;
        private long _asterMaxSceneBatchCameraFlushes;
'@
    $v=$v.Replace($fieldAnchor,$fields.TrimEnd())
}

$userPick='        public bool UserPick { get { return _userPick; } set { _userPick = value; } }'
if(-not $v.Contains('public void AsterMaxBeginSceneBatch()')){
    if(-not $v.Contains($userPick)){ throw 'C10.47 UserPick insertion anchor missing.' }
    $api=@'
        public long AsterMaxSceneBatchDeferredCameraAdjusts { get { return _asterMaxSceneBatchDeferredCameraAdjusts; } }
        public long AsterMaxSceneBatchCameraFlushes { get { return _asterMaxSceneBatchCameraFlushes; } }
        public int AsterMaxSceneBatchDepth { get { return _asterMaxSceneBatchDepth; } }

        public void AsterMaxBeginSceneBatch()
        {
            if (InvokeRequired)
            {
                Invoke(new Action(AsterMaxBeginSceneBatch));
                return;
            }
            if (_asterMaxSceneBatchDepth == 0)
            {
                _asterMaxSceneBatchCameraDirty = false;
                _asterMaxSceneBatchDeferredCameraAdjusts = 0;
                _asterMaxSceneBatchCameraFlushes = 0;
            }
            _asterMaxSceneBatchDepth++;
        }

        public void AsterMaxEndSceneBatch()
        {
            if (InvokeRequired)
            {
                Invoke(new Action(AsterMaxEndSceneBatch));
                return;
            }
            if (_asterMaxSceneBatchDepth <= 0)
                throw new InvalidOperationException("AsterMax scene batch underflow.");

            _asterMaxSceneBatchDepth--;
            if (_asterMaxSceneBatchDepth == 0 && _asterMaxSceneBatchCameraDirty)
            {
                _asterMaxSceneBatchCameraDirty = false;
                _asterMaxSceneBatchCameraFlushes++;
                AdjustCameraDistanceAndClippingRedraw();
            }
        }

'@
    $v=$v.Replace($userPick,$api+$userPick)
}

if(-not $v.Contains('_asterMaxSceneBatchDeferredCameraAdjusts++;')){
    $v=Replace-CSharpMethod $v '        public void AddCells(vtkMaxActorData data)' {
        param($existing)
        $old='            AdjustCameraDistanceAndClippingRedraw();'
        if(-not $existing.Contains($old)){ throw 'C10.47 AddCells camera-adjust anchor missing.' }
        $new=@'
            if (_asterMaxSceneBatchDepth > 0)
            {
                _asterMaxSceneBatchCameraDirty = true;
                _asterMaxSceneBatchDeferredCameraAdjusts++;
            }
            else
                AdjustCameraDistanceAndClippingRedraw();
'@
        return $existing.Replace($old,$new.TrimEnd())
    }
}
Set-Content $vtkPath $v -Encoding UTF8

# ----------------------------------------------------------------------
# FrmMain: synchronous marshaling wrappers. Controller may be importing on a
# worker thread, while all scene-batch state and VTK calls remain on UI thread.
# ----------------------------------------------------------------------
$m=Normalize-Lf (Get-Content $mainPath -Raw)
if(-not $m.Contains('public void AsterMaxBeginVtkSceneBatch()')){
    $anchor=@'
        public void Add3DCells(vtkControl.vtkMaxActorData cellData)
        {
            InvokeIfRequired(_vtk.AddCells, cellData);
        }
'@
    if(-not $m.Contains($anchor.TrimEnd())){ throw 'C10.47 FrmMain Add3DCells anchor missing.' }
    $wrapper=@'
        public void Add3DCells(vtkControl.vtkMaxActorData cellData)
        {
            InvokeIfRequired(_vtk.AddCells, cellData);
        }
        public void AsterMaxBeginVtkSceneBatch()
        {
            InvokeIfRequired(() => _vtk.AsterMaxBeginSceneBatch());
        }
        public void AsterMaxEndVtkSceneBatch()
        {
            InvokeIfRequired(() => _vtk.AsterMaxEndSceneBatch());
        }
'@
    $m=$m.Replace($anchor.TrimEnd(),$wrapper.TrimEnd())
}
Set-Content $mainPath $m -Encoding UTF8

# ----------------------------------------------------------------------
# Controller: batch only the final geometry draw performed by UpdateAfterImport.
# The try/finally guarantees camera state is restored/flushed on errors.
# Exact BREP, model identity, selection IDs, hierarchy and FEM remain untouched.
# ----------------------------------------------------------------------
$c=Normalize-Lf (Get-Content $controllerPath -Raw)
if(-not $c.Contains('AsterMaxBeginVtkSceneBatch();')){
    $needle=@'
                if (_asterMaxCadImportDepth == 0)
                    _form.WriteDataToOutput("AsterMax visualización CAD: " + asterMaxGeometryPartCount +
                        " pieza(s); render inicial " +
                        (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold ? "sin aristas." : "normal."));
                DrawGeometry(false);
'@
    if(-not $c.Contains($needle.TrimEnd())){ throw 'C10.47 final CAD DrawGeometry anchor missing after C10.42.' }
    $replacement=@'
                if (_asterMaxCadImportDepth == 0)
                    _form.WriteDataToOutput("AsterMax visualización CAD: " + asterMaxGeometryPartCount +
                        " pieza(s); render inicial " +
                        (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold ? "sin aristas." : "normal."));

                _form.AsterMaxBeginVtkSceneBatch();
                try
                {
                    DrawGeometry(false);
                }
                finally
                {
                    _form.AsterMaxEndVtkSceneBatch();
                }
'@
    $c=$c.Replace($needle.TrimEnd(),$replacement.TrimEnd())
}
Set-Content $controllerPath $c -Encoding UTF8

Write-Host 'C10.47: CAD scene batch defers per-actor camera/redraw work and flushes once in finally.' -ForegroundColor Green
