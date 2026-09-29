param(
  [Parameter(Mandatory=$true)][string]$Label,
  [Parameter(Mandatory=$true)][double]$Size
)
$ErrorActionPreference='Stop'

$repo=(Resolve-Path '.').Path
$step=(Resolve-Path '.\tutorial-input\Cap_fillets.stp').Path
$out=Join-Path $repo "tutorial-evidence\WS01.1\mesh-$Label"
New-Item -ItemType Directory -Force $out | Out-Null

Write-Host "=== BUILD WS01.1 $Label TETRA10 ==="
python .\native-windows\ansys-tutorials\generate-ws01.py --step $step --out $out --size $Size
if($LASTEXITCODE -ne 0){ throw "WS01.1 mesh generation failed for $Label." }

Write-Host "=== SOLVE WS01.1 $Label TETRA10 ==="
$runner=(Resolve-Path '.\native-windows\runtime\CodeAster\astermax-codeaster-runner.ps1').Path
& $runner (Join-Path $out 'ws01.export') $out | Tee-Object (Join-Path $out 'ASTERMAX_CODE_ASTER_STDOUT.log')
if($LASTEXITCODE -ne 0){ throw "WS01.1 genuine Code_Aster solve failed for $Label." }

$mess=Join-Path $out 'ws01.mess'
if(-not (Test-Path $mess)){ throw "Missing Code_Aster message file for $Label." }
$bad=Select-String -Path $mess -Pattern 'trop distordue','jacobien.*signe' -CaseSensitive:$false
if($bad){
  $bad | ForEach-Object { Write-Host $_.Line }
  throw "WS01.1 $Label contains invalid/distorted quadratic elements."
}
Write-Host "MESH_QUALITY_$Label=PASS_NO_DISTORTED_TETRA10_ALARM"

Write-Host "=== BRIDGE + COMPARE WS01.1 $Label ==="
$env:ASTERMAX_MED_BRIDGE_MODE='production'
python .\native-windows\bridge-c964-med-results.py (Join-Path $out 'ws01.rmed') (Join-Path $out 'ws01.astermax-results.json') (Join-Path $out 'ws01.astermax-results.vtu') | Tee-Object (Join-Path $out 'ASTERMAX_MED_BRIDGE.log')
if($LASTEXITCODE -ne 0){ throw "WS01.1 MED result admission failed for $Label." }

$reference=(Resolve-Path '.\native-windows\ansys-tutorials\ws01-ansys-reference.json').Path
python .\native-windows\ansys-tutorials\compare-ws01.py --bundle (Join-Path $out 'ws01.astermax-results.json') --input (Join-Path $out 'ws01-input.json') --reference $reference --out (Join-Path $out 'ws01-comparison.json')
if($LASTEXITCODE -ne 0){ throw "WS01.1 comparison failed for $Label." }

Write-Host "=== RENDER WS01.1 $Label ==="
python .\native-windows\ansys-tutorials\render-ws01.py --vtu (Join-Path $out 'ws01.astermax-results.vtu') --out (Join-Path $out 'screenshots')
if($LASTEXITCODE -ne 0){ throw "WS01.1 screenshot render failed for $Label." }

Write-Host "WS01_CASE_$Label=PASS"
