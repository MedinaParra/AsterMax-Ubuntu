param([string]$Root)
$ErrorActionPreference='Stop'

# C10.48 v3 repairs the wrapper composition itself.  v2 defined four structural
# transformation blocks, but attempted to Replace-Block markers that never
# existed in the base candidate script.  Keep those transformations unchanged
# and inject them immediately before the base candidate writes vtkMaxActor.cs.
$v2=Join-Path $PSScriptRoot 'candidate-c1048-lazy-element-edges-v2.ps1'
if(!(Test-Path $v2)){ throw "C10.48 v3 wrapper missing: $v2" }
$text=Get-Content $v2 -Raw

# Remove only the four broken wrapper-composition calls.  The Replace-Block
# helper is harmless and can remain; this avoids changing the actual C# edits.
$text=[regex]::Replace($text,'(?m)^\$text=Replace-Block \$text .*\r?\n','')

$needle="$temp=Join-Path `$PSScriptRoot 'candidate-c1048-lazy-element-edges-runtime.ps1'"
if(-not $text.Contains($needle)){ throw 'C10.48 v3 runtime-script anchor missing.' }
$inject=@'
$actorWrite='Set-Content $actorPath $a -Encoding UTF8'
if(-not $text.Contains($actorWrite)){ throw 'C10.48 v3 actor write anchor missing in base candidate.' }
$combined=$constructorBlock+$copyBlock+$animationBlock+$createPolyBlock
$text=$text.Replace($actorWrite,$combined+"`n"+$actorWrite)
'@
$text=$text.Replace($needle,$inject+"`n"+$needle)

$temp=Join-Path $PSScriptRoot 'candidate-c1048-lazy-element-edges-v3-runtime.ps1'
Set-Content $temp $text -Encoding UTF8
try { & $temp -Root $Root }
finally { Remove-Item $temp -Force -ErrorAction SilentlyContinue }
