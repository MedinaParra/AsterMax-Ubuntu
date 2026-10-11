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

$temp=Join-Path $PSScriptRoot 'candidate-c1048-lazy-element-edges-v3-runtime.ps1'
Set-Content $temp $text -Encoding UTF8
try { & $temp -Root $Root }
finally { Remove-Item $temp -Force -ErrorAction SilentlyContinue }
