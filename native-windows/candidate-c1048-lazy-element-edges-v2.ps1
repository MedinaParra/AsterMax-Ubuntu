param([string]$Root)
$ErrorActionPreference='Stop'

$impl=Join-Path $PSScriptRoot 'candidate-c1048-lazy-element-edges.ps1'
if(!(Test-Path $impl)){ throw "C10.48 implementation missing: $impl" }
$text=Get-Content $impl -Raw

function Replace-Block([string]$Source,[string]$StartMarker,[string]$EndMarker,[string]$Replacement,[string]$Name){
    $start=$Source.IndexOf($StartMarker)
    $end=$Source.IndexOf($EndMarker,$start)
    if($start -lt 0 -or $end -le $start){ throw "C10.48 v2 $Name block markers missing." }
    return $Source.Substring(0,$start)+$Replacement+$Source.Substring($end)
}

$constructorBlock=@'
# Keep historical constructors, add a fourth argument only for the optimized path.
if(-not $a.Contains('bool deferElementEdges')){
    $pattern='(?s)        public vtkMaxActor\(vtkMaxActorData data, bool extractVisualizationSurface, bool createNodalActor\)\s*:\s*this\(\)\s*\{'
    $rx=[regex]::new($pattern)
    $matches=$rx.Matches($a)
    if($matches.Count -ne 1){ throw "C10.48 vtkMaxActor three-argument constructor expected 1 structural match, got $($matches.Count)." }
    $replacement='        public vtkMaxActor(vtkMaxActorData data, bool extractVisualizationSurface, bool createNodalActor)' + "`n" +
                 '            : this(data, extractVisualizationSurface, createNodalActor, false)' + "`n" +
                 '        {' + "`n" +
                 '        }' + "`n" +
                 '        public vtkMaxActor(vtkMaxActorData data, bool extractVisualizationSurface, bool createNodalActor, bool deferElementEdges)' + "`n" +
                 '            : this()' + "`n" +
                 '        {'
    $a=$rx.Replace($a,$replacement,1)
}

'@
$text=Replace-Block $text '# Keep historical constructors, add a fourth argument only for the optimized path.' '# Only the polygon path used by the CAD visualization receives the defer flag.' $constructorBlock 'constructor'

$copyBlock=@'
# Ensure source edges exist before copy construction if an operation requires a full actor copy.
if(-not $a.Contains('sourceActor.AsterMaxEnsureElementEdges();')){
    $pattern='(?s)        public vtkMaxActor\(vtkMaxActor sourceActor\)\s*:\s*this\(\)\s*\{'
    $rx=[regex]::new($pattern)
    $matches=$rx.Matches($a)
    if($matches.Count -ne 1){ throw "C10.48 vtkMaxActor copy constructor expected 1 structural match, got $($matches.Count)." }
    $replacement=$matches[0].Value + "`n" +
        '            if (sourceActor.AsterMaxElementEdgesDeferred) sourceActor.AsterMaxEnsureElementEdges();'
    $a=$rx.Replace($a,$replacement,1)
}

'@
$text=Replace-Block $text '# Ensure source edges exist before copy construction if an operation requires a full actor copy.' '# Animation mutates edge-point data directly; materialize before that path.' $copyBlock 'copy constructor'

$animationBlock=@'
# Animation mutates edge-point data directly; materialize before that path.
if(-not $a.Contains('C10.48 animation edge materialization')){
    $pattern='(?s)        public void SetAnimationFrame\(vtkMaxActorData data, int frameNumber\)\s*\{'
    $rx=[regex]::new($pattern)
    $matches=$rx.Matches($a)
    if($matches.Count -ne 1){ throw "C10.48 SetAnimationFrame expected 1 structural match, got $($matches.Count)." }
    $replacement=$matches[0].Value + "`n" +
        '            // C10.48 animation edge materialization' + "`n" +
        '            if (_asterMaxElementEdgesDeferred) AsterMaxEnsureElementEdges();'
    $a=$rx.Replace($a,$replacement,1)
}

'@
$text=Replace-Block $text '# Animation mutates edge-point data directly; materialize before that path.' '# Replace CreatePolyFromData only once and create a lightweight placeholder when deferred.' $animationBlock 'animation'

$createPolyBlock=@"
# Replace CreatePolyFromData only once and create a lightweight placeholder when deferred.
`$a=Replace-CSharpMethod `$a '        private void CreatePolyFromData(vtkMaxActorData data)' {
    param(`$existing)
    `$x=`$existing.Replace('private void CreatePolyFromData(vtkMaxActorData data)','private void CreatePolyFromData(vtkMaxActorData data, bool deferElementEdges)')
    `$x=`$x.Replace('AddNodeAndCellDataToPoly(data.Geometry, out polyActor, out polyEdges, out numOfCellPolys, true);',
                  'AddNodeAndCellDataToPoly(data.Geometry, out polyActor, out polyEdges, out numOfCellPolys, !deferElementEdges);')

    `$ifToken='            if (data.CanHaveElementEdges)'
    `$ifStart=`$x.IndexOf(`$ifToken)
    if(`$ifStart -lt 0){ throw 'C10.48 CreatePolyFromData element-edge if missing.' }
    `$braceStart=`$x.IndexOf('{',`$ifStart)
    if(`$braceStart -lt 0){ throw 'C10.48 CreatePolyFromData element-edge opening brace missing.' }
    `$depth=0; `$ifEnd=-1
    for(`$n=`$braceStart; `$n -lt `$x.Length; `$n++){
        if(`$x[`$n] -eq '{'){ `$depth++ }
        elseif(`$x[`$n] -eq '}'){
            `$depth--
            if(`$depth -eq 0){ `$ifEnd=`$n+1; break }
        }
    }
    if(`$ifEnd -lt 0){ throw 'C10.48 CreatePolyFromData element-edge closing brace missing.' }

    `$new=@'
            if (data.CanHaveElementEdges)
            {
                if (deferElementEdges)
                {
                    // Keep a lightweight actor so historical transforms/visibility calls remain valid.
                    _elementEdges = vtkActor.New();
                    _elementEdges.PickableOff();
                    _elementEdgesProperty = _elementEdges.GetProperty();
                    _elementEdgesProperty.SetLighting(true);
                    _asterMaxElementEdgesDeferred = true;
                }
                else
                {
                    // Mapper
                    mapper = vtkDataSetMapper.New();
                    mapper.SetInput(polyEdges);
                    // Actor
                    _elementEdges = new vtkActor();
                    _elementEdges.SetMapper(mapper);
                    _elementEdges.PickableOff();
                    //
                    _elementEdgesProperty = _elementEdges.GetProperty();
                    _elementEdgesProperty.SetLighting(true);
                }
            }
'@
    return `$x.Substring(0,`$ifStart)+`$new.TrimEnd()+`$x.Substring(`$ifEnd)
}

"@
$text=Replace-Block $text '# Replace CreatePolyFromData only once and create a lightweight placeholder when deferred.' '# When extractEdges=false, do not populate/update a second vtkPolyData at all.' $createPolyBlock 'CreatePolyFromData'

$temp=Join-Path $PSScriptRoot 'candidate-c1048-lazy-element-edges-runtime.ps1'
Set-Content $temp $text -Encoding UTF8
try { & $temp -Root $Root }
finally { Remove-Item $temp -Force -ErrorAction SilentlyContinue }
