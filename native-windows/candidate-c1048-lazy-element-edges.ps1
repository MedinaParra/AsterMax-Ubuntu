param([string]$Root)
$ErrorActionPreference='Stop'

$actorPath=Join-Path $Root 'vtkControl/vtkMax/Actor/vtkMaxActor.cs'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
foreach($p in @($actorPath,$vtkPath)){ if(!(Test-Path $p)){ throw "C10.48 missing: $p" } }

function To-Lf([string]$Text){ return [regex]::Replace($Text,"\r\n?","`n") }
function Replace-CSharpMethod([string]$text,[string]$signature,[scriptblock]$transform){
    $start=$text.IndexOf($signature)
    if($start -lt 0){ throw "C10.48 method missing: $signature" }
    $brace=$text.IndexOf('{',$start)
    if($brace -lt 0){ throw "C10.48 opening brace missing: $signature" }
    $depth=0; $end=-1
    for($n=$brace; $n -lt $text.Length; $n++){
        if($text[$n] -eq '{'){ $depth++ }
        elseif($text[$n] -eq '}'){
            $depth--
            if($depth -eq 0){$end=$n+1;break}
        }
    }
    if($end -lt 0){ throw "C10.48 closing brace missing: $signature" }
    $existing=$text.Substring($start,$end-$start)
    $replacement=& $transform $existing
    return $text.Substring(0,$start)+$replacement.TrimEnd()+$text.Substring($end)
}

$a=To-Lf (Get-Content $actorPath -Raw)
if(-not $a.Contains('_asterMaxElementEdgesDeferred')){
    $anchor='        private vtkProperty _modelEdgesProperty;'
    if(-not $a.Contains($anchor)){ throw 'C10.48 vtkMaxActor edge-property field anchor missing.' }
    $a=$a.Replace($anchor,$anchor+"`n"+'        private bool _asterMaxElementEdgesDeferred;')
}
if(-not $a.Contains('public bool AsterMaxElementEdgesDeferred')){
    $anchor='        public vtkProperty ModelEdgesProperty { get { return _modelEdgesProperty; } set { _modelEdgesProperty = value; } }'
    if(-not $a.Contains($anchor)){ throw 'C10.48 vtkMaxActor property anchor missing.' }
    $api=@'
        public bool AsterMaxElementEdgesDeferred { get { return _asterMaxElementEdgesDeferred; } }
        public bool AsterMaxEnsureElementEdges()
        {
            if (!_asterMaxElementEdgesDeferred) return false;
            if (_geometryMapper == null || _geometryMapper.GetInputAsDataSet() == null)
                throw new InvalidOperationException("Deferred element edges require geometry mapper input.");
            vtkExtractEdges extractEdges = vtkExtractEdges.New();
            extractEdges.SetInput(_geometryMapper.GetInputAsDataSet());
            extractEdges.Update();
            vtkDataSetMapper mapper = vtkDataSetMapper.New();
            mapper.SetInput(extractEdges.GetOutput());
            if (_elementEdges == null) _elementEdges = vtkActor.New();
            _elementEdges.SetMapper(mapper);
            _elementEdges.PickableOff();
            _elementEdgesProperty = _elementEdges.GetProperty();
            _elementEdgesProperty.SetLighting(true);
            _asterMaxElementEdgesDeferred = false;
            return true;
        }
'@
    $a=$a.Replace($anchor,$anchor+"`n"+$api.TrimEnd())
}
$oldCall='                    CreatePolyFromData(data);'
if($a.Contains($oldCall)){$a=$a.Replace($oldCall,'                    CreatePolyFromData(data, deferElementEdges);')}
$a=Replace-CSharpMethod $a '        private static void AddNodeAndCellDataToPoly(PartExchangeData data, out vtkPolyData polyActor, out vtkPolyData polyEdges,' {
    param($existing)
    $x=$existing.Replace('            polyEdges = vtkPolyData.New();','            polyEdges = extractEdges ? vtkPolyData.New() : null;')
    $x=$x.Replace('            polyEdges.SetPoints(points);','            if (extractEdges) polyEdges.SetPoints(points);')
    $x=$x.Replace('            polyEdges.Update();','            if (extractEdges) polyEdges.Update();')
    return $x
}
Set-Content $actorPath $a -Encoding UTF8

$v=To-Lf (Get-Content $vtkPath -Raw)
$fieldAnchor='        private long _asterMaxSceneBatchCameraFlushes;'
if(-not $v.Contains('_asterMaxDeferredElementEdgeActors')){
    if(-not $v.Contains($fieldAnchor)){ throw 'C10.48 C10.47 telemetry field anchor missing.' }
    $v=$v.Replace($fieldAnchor,$fieldAnchor+"`n"+'        private long _asterMaxDeferredElementEdgeActors;'+"`n"+'        private long _asterMaxMaterializedElementEdgeActors;')
}
$userPick='        public bool UserPick { get { return _userPick; } set { _userPick = value; } }'
if(-not $v.Contains('AsterMaxDeferredElementEdgeActors')){
    if(-not $v.Contains($userPick)){ throw 'C10.48 UserPick property anchor missing.' }
    $props=@'
        public long AsterMaxDeferredElementEdgeActors { get { return _asterMaxDeferredElementEdgeActors; } }
        public long AsterMaxMaterializedElementEdgeActors { get { return _asterMaxMaterializedElementEdgeActors; } }
        public int AsterMaxDeferredElementEdgesRemaining
        {
            get
            {
                int count = 0;
                foreach (var actor in _actors.Values)
                    if (actor.AsterMaxElementEdgesDeferred) count++;
                return count;
            }
        }
'@
    $v=$v.Replace($userPick,$props+$userPick)
}
# Reset C10.48 counters structurally inside the C10.47 begin-batch method.
if(-not $v.Contains('_asterMaxDeferredElementEdgeActors = 0;')){
    $v=Replace-CSharpMethod $v '        public void AsterMaxBeginSceneBatch()' {
        param($existing)
        $anchor='                _asterMaxSceneBatchCameraFlushes = 0;'
        if(-not $existing.Contains($anchor)){ throw 'C10.48 scene-batch camera-flush reset missing.' }
        return $existing.Replace($anchor,$anchor+"`n"+
            '                _asterMaxDeferredElementEdgeActors = 0;'+"`n"+
            '                _asterMaxMaterializedElementEdgeActors = 0;')
    }
}
if(-not $v.Contains('private void AsterMaxEnsureDeferredElementEdges()')){
    $applySig='        private void ApplyEdgesVisibilityAndBackfaceCulling()'
    if(-not $v.Contains($applySig)){ throw 'C10.48 edge-visibility method anchor missing.' }
    $helper=@'
        private void AsterMaxEnsureDeferredElementEdges()
        {
            foreach (var actor in _actors.Values)
            {
                if (actor.AsterMaxElementEdgesDeferred && actor.AsterMaxEnsureElementEdges())
                    _asterMaxMaterializedElementEdgeActors++;
            }
        }
        //
'@
    $v=$v.Replace($applySig,$helper+$applySig)
}
$setterOld=@'
                    _edgesVisibility = value;
                    ApplyEdgesVisibilityAndBackfaceCulling();
'@
if(-not $v.Contains('if (_edgesVisibility == vtkEdgesVisibility.ElementEdges) AsterMaxEnsureDeferredElementEdges();')){
    if(-not $v.Contains($setterOld.TrimEnd())){ throw 'C10.48 EdgesVisibility setter body anchor missing.' }
    $setterNew=@'
                    _edgesVisibility = value;
                    if (_edgesVisibility == vtkEdgesVisibility.ElementEdges) AsterMaxEnsureDeferredElementEdges();
                    ApplyEdgesVisibilityAndBackfaceCulling();
'@
    $v=$v.Replace($setterOld.TrimEnd(),$setterNew.TrimEnd())
}
$v=Replace-CSharpMethod $v '        public void AddCells(vtkMaxActorData data)' {
    param($existing)
    if($existing.Contains('bool asterMaxDeferElementEdges')){ return $existing }
    $old='            vtkMaxActor actor = new vtkMaxActor(data);'
    if(-not $existing.Contains($old)){ throw 'C10.48 AddCells actor-construction anchor missing.' }
    $new=@'
            bool asterMaxDeferElementEdges = _asterMaxSceneBatchDepth > 0 &&
                _edgesVisibility == vtkEdgesVisibility.NoEdges &&
                data.Layer == vtkRendererLayer.Base && data.CanHaveElementEdges;
            vtkMaxActor actor = asterMaxDeferElementEdges
                ? new vtkMaxActor(data, false, false, true)
                : new vtkMaxActor(data);
            if (asterMaxDeferElementEdges) _asterMaxDeferredElementEdgeActors++;
'@
    return $existing.Replace($old,$new.TrimEnd())
}
$highlightNeedle='                vtkMaxActor actorToHighLight = _actors[actorName];'
if(-not $v.Contains('actorToHighLight.AsterMaxEnsureElementEdges();')){
    if(-not $v.Contains($highlightNeedle)){ throw 'C10.48 highlight actor anchor missing.' }
    $v=$v.Replace($highlightNeedle,$highlightNeedle+"`n"+'                if (actorToHighLight.AsterMaxElementEdgesDeferred)'+"`n"+'                {'+"`n"+'                    if (actorToHighLight.AsterMaxEnsureElementEdges()) _asterMaxMaterializedElementEdgeActors++;'+"`n"+'                }')
}
Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.48: initial large-CAD NoEdges path defers element-edge topology and materializes on demand.' -ForegroundColor Green
