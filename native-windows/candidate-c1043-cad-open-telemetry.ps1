param([string]$Root)
$ErrorActionPreference='Stop'

$impl = Join-Path $PSScriptRoot 'candidate-c1043-cad-open-telemetry-v2.ps1'
if(!(Test-Path $impl)){ throw "C10.43 v2 implementation missing: $impl" }

# Hotfix validated against the effective C10.42 Controller.cs captured on Windows:
# the log literal is "AsterMax visualización CAD: " (space after colon), so the
# structural regex must not require the closing quote immediately after ':'.
$text = Get-Content $impl -Raw
$bad = 'AsterMax visualización CAD:\".*?'
$good = 'AsterMax visualización CAD:.*?'
if(-not $text.Contains($bad)){ throw 'C10.43 expected v2 scene-regex token missing.' }
$text = $text.Replace($bad,$good)
$temp = Join-Path $PSScriptRoot 'candidate-c1043-cad-open-telemetry-v2-runtime.ps1'
Set-Content $temp $text -Encoding UTF8
try { & $temp -Root $Root }
finally { Remove-Item $temp -Force -ErrorAction SilentlyContinue }
