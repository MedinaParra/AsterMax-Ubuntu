param([string]$Root)
$ErrorActionPreference='Stop'

# C10.48 v3 repairs wrapper composition only. v2 defines four structural
# transformation blocks but tries to replace comment markers absent from the
# base candidate. Preserve the C# transformations and inject them immediately
# before the base candidate writes vtkMaxActor.cs.
$v2=Join-Path $PSScriptRoot 'candidate-c1048-lazy-element-edges-v2.ps1'
if(!(Test-Path $v2)){ throw "C10.48 v3 wrapper missing: $v2" }
$text=Get-Content $v2 -Raw
$text=[regex]::Replace($text,'(?m)^\$text=Replace-Block \$text .*\r?\n','')

$needle='$temp=Join-Path $PSScriptRoot ''candidate-c1048-lazy-element-edges-runtime.ps1'''
if(-not $text.Contains($needle)){ throw 'C10.48 v3 runtime-script anchor missing.' }
$inject=@'
$actorWrite='Set-Content $actorPath $a -Encoding UTF8'
if(-not $text.Contains($actorWrite)){ throw 'C10.48 v3 actor write anchor missing in base candidate.' }
$combined=$constructorBlock+$copyBlock+$animationBlock+$createPolyBlock
$text=$text.Replace($actorWrite,$combined+"`n"+$actorWrite)
'@
$text=$text.Replace($needle,$inject+"`n"+$needle)

# The historical EdgesVisibility setter is whitespace-sensitive in the base
# candidate. Replace that script fragment with a structural property transform
# so CRLF/indentation changes cannot block C10.48 before compilation.
$old=@'
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
'@
$new=@'
if(-not $v.Contains('if (_edgesVisibility == vtkEdgesVisibility.ElementEdges) AsterMaxEnsureDeferredElementEdges();')){
    $v=Replace-CSharpMethod $v '        public vtkEdgesVisibility EdgesVisibility' {
        param($existing)
        $pattern='(?m)^(\s*)_edgesVisibility\s*=\s*value;\s*$'
        $matches=[regex]::Matches($existing,$pattern)
        if($matches.Count -ne 1){ throw "C10.48 EdgesVisibility assignment expected 1 structural match, got $($matches.Count)." }
        $indent=$matches[0].Groups[1].Value
        $replacement=$matches[0].Value+"`n"+$indent+'if (_edgesVisibility == vtkEdgesVisibility.ElementEdges) AsterMaxEnsureDeferredElementEdges();'
        return [regex]::Replace($existing,$pattern,[System.Text.RegularExpressions.MatchEvaluator]{ param($m) $replacement },1)
    }
}
'@
if(-not $text.Contains($old)){ throw 'C10.48 v3 EdgesVisibility script fragment missing.' }
$text=$text.Replace($old,$new)

$temp=Join-Path $PSScriptRoot 'candidate-c1048-lazy-element-edges-v3-runtime.ps1'
Set-Content $temp $text -Encoding UTF8
try { & $temp -Root $Root }
finally { Remove-Item $temp -Force -ErrorAction SilentlyContinue }
