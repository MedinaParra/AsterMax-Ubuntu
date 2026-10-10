param([string]$Root)
$ErrorActionPreference='Stop'

$impl = Join-Path $PSScriptRoot 'candidate-c1043-cad-open-telemetry-v2.ps1'
if(!(Test-Path $impl)){ throw "C10.43 v2 implementation missing: $impl" }

# The effective C10.42 Controller.cs writes "AsterMax visualización CAD: "
# with content continuing after the colon. Replace the one scene-pattern line
# structurally instead of attempting an escape-sensitive substring hotfix.
$lines = @(Get-Content $impl)
$hits = @()
for($i = 0; $i -lt $lines.Count; $i++)
{
    if($lines[$i].Contains('$pattern=') -and $lines[$i].Contains('AsterMax visualización CAD:'))
    {
        $hits += $i
    }
}
if($hits.Count -ne 1){ throw "C10.43 scene-pattern line expected exactly 1 match, got $($hits.Count)." }
$lines[$hits[0]] = '    $pattern=''(?<log>\s*if \(_asterMaxCadImportDepth == 0\)\s*\n\s*_form\.WriteDataToOutput\(\"AsterMax visualización CAD:.*?\);\s*\n)\s*DrawGeometry\(false\);'''

$temp = Join-Path $PSScriptRoot 'candidate-c1043-cad-open-telemetry-v2-runtime.ps1'
Set-Content $temp $lines -Encoding UTF8
try
{
    & $temp -Root $Root
}
finally
{
    Remove-Item $temp -Force -ErrorAction SilentlyContinue
}
