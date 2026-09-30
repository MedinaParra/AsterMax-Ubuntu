param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New,[string]$Label) {
    if(-not $Text.Contains($Old)){ throw "C10.26 anchor missing: $Label" }
    return $Text.Replace($Old,$New)
}

$src=Join-Path $PSScriptRoot 'c1026'
$contract=Join-Path $Root 'PrePoMax/AsterMaxSurfaceMechanicsContract.cs'
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $contract) -or !(Test-Path $exporter)){ throw 'C10.26 requires C10.25 body-load backend first.' }

Copy-Item (Join-Path $src 'AsterMaxSurfaceMechanicsContract.cs') $contract -Force
$e=Get-Content (Join-Path $src 'AsterMaxCodeAsterSurfaceTractionExporter.cs') -Raw
$e=$e.Replace('AsterMaxCodeAsterSurfaceTractionExporter','AsterMaxCodeAsterNativeExporter')
Set-Content $exporter $e -Encoding UTF8

$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $ui -Raw
if(-not $u.Contains('CommandTile("Surface Traction"')) {
    $anchor='                CommandTile("Pressure", "LOAD", () => CreateAsterMaxPressure()),'
    $insert=$anchor+[Environment]::NewLine+'                CommandTile("Surface Traction", "LOAD", () => tsmiCreateLoad_Click(null, new CaeGlobals.EventArgs<int>(3))),'
    $u=Replace-Required $u $anchor $insert 'Surface Traction tile'
    Set-Content $ui $u -Encoding UTF8
}

Write-Host 'C10.26 Surface Traction -> FORCE_FACE backend applied.' -ForegroundColor Green
