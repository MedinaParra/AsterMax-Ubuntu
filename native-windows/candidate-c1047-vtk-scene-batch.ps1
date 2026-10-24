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
function Insert-AfterCSharpMethod([string]$text,[string]$signature,[string]$insertion){
    $start=$text.IndexOf($signature)
    if($start -lt 0){ throw "C10.47 insertion method missing: $signature" }
    $brace=$text.IndexOf('{',$start)
    if($brace -lt 0){ throw "C10.47 insertion opening brace missing: $signature" }
    $depth=0; $end=-1
    for($n=$brace; $n -lt $text.Length; $n++){
        if($text[$n] -eq '{'){ $depth++ }
        elseif($text[$n] -eq '}'){
            $depth--
            if($depth -eq 0){ $end=$n+1; break }
        }
    }
    if($end -lt 0){ throw "C10.47 insertion closing brace missing: $signature" }
    return $text.Substring(0,$end)+"`n"+$insertion.TrimEnd()+$text.Substring($end)
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
# Locate Add3DCells structurally because prior native patches may change its
# whitespace/body while preserving its signature and semantics.
# ----------------------------------------------------------------------
$m=Normalize-Lf (Get-Content $mainPath -Raw)
if(-not $m.Contains('public void AsterMaxBeginVtkSceneBatch()')){
    $wrappers=@'
        public void AsterMaxBeginVtkSceneBatch()
        {
            InvokeIfRequired(() => _vtk.AsterMaxBeginSceneBatch());
        }
        public void AsterMaxEndVtkSceneBatch()
        {
            InvokeIfRequired(() => _vtk.AsterMaxEndSceneBatch());
        }
'@
    $m=Insert-AfterCSharpMethod $m '        public void Add3DCells(vtkControl.vtkMaxActorData cellData)' $wrappers
}
Set-Content $mainPath $m -Encoding UTF8

# ----------------------------------------------------------------------
# Controller: batch only the final CAD geometry draw introduced by the C10.42
# large-assembly policy. Later candidates add diagnostics/preview code around
# it, so locate the draw structurally from the ASTERMAX_LARGE_ASSEMBLY_PARTS
# policy instead of requiring the old exact multiline block.
# ----------------------------------------------------------------------
$c=Normalize-Lf (Get-Content $controllerPath -Raw)
if(-not $c.Contains('AsterMaxBeginVtkSceneBatch();')){
    $policyToken='Environment.GetEnvironmentVariable("ASTERMAX_LARGE_ASSEMBLY_PARTS")'
    $policyPos=$c.IndexOf($policyToken)
    if($policyPos -lt 0){ throw 'C10.47 large-assembly policy anchor missing after C10.42.' }

    $drawToken='DrawGeometry(false);'
    $drawPos=$c.IndexOf($drawToken,$policyPos)
    if($drawPos -lt 0){ throw 'C10.47 final CAD DrawGeometry call missing after large-assembly policy.' }
    if(($drawPos-$policyPos) -gt 6000){ throw 'C10.47 final CAD DrawGeometry call is unexpectedly far from large-assembly policy.' }

    $between=$c.Substring($policyPos,$drawPos-$policyPos)
    if(-not $between.Contains('AsterMax visualización CAD:')){
        throw 'C10.47 refused to batch an unverified DrawGeometry call.'
    }

    $lineStart=$c.LastIndexOf("`n",$drawPos)
    if($lineStart -lt 0){$lineStart=0}else{$lineStart++}
    $indent=$c.Substring($lineStart,$drawPos-$lineStart)
    if($indent.Trim().Length -ne 0){ throw 'C10.47 DrawGeometry line has unexpected prefix.' }

    $drawLine=$indent+$drawToken
    $replacement=$indent+'_form.AsterMaxBeginVtkSceneBatch();'+"`n"+
                 $indent+'try'+"`n"+
                 $indent+'{'+"`n"+
                 $indent+'    DrawGeometry(false);'+"`n"+
                 $indent+'}'+"`n"+
                 $indent+'finally'+"`n"+
                 $indent+'{'+"`n"+
                 $indent+'    _form.AsterMaxEndVtkSceneBatch();'+"`n"+
                 $indent+'}'
    $c=$c.Substring(0,$lineStart)+$replacement+$c.Substring($lineStart+$drawLine.Length)
}
Set-Content $controllerPath $c -Encoding UTF8

Write-Host 'C10.47: CAD scene batch defers per-actor camera/redraw work and flushes once in finally.' -ForegroundColor Green
