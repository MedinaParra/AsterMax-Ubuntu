param([string]$Root)
$ErrorActionPreference='Stop'

$impl=Join-Path $PSScriptRoot 'candidate-c1048-lazy-element-edges.ps1'
if(!(Test-Path $impl)){ throw "C10.48 implementation missing: $impl" }

$text=Get-Content $impl -Raw
$start=$text.IndexOf('# Keep historical constructors, add a fourth argument only for the optimized path.')
$end=$text.IndexOf('# Only the polygon path used by the CAD visualization receives the defer flag.')
if($start -lt 0 -or $end -le $start){ throw 'C10.48 v2 constructor block markers missing.' }

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

$patched=$text.Substring(0,$start)+$constructorBlock+$text.Substring($end)
$temp=Join-Path $PSScriptRoot 'candidate-c1048-lazy-element-edges-runtime.ps1'
Set-Content $temp $patched -Encoding UTF8
try { & $temp -Root $Root }
finally { Remove-Item $temp -Force -ErrorAction SilentlyContinue }
