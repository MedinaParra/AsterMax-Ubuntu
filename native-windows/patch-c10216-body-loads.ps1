param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New,[string]$Label) {
    if(-not $Text.Contains($Old)){ throw "C10.25 anchor missing: $Label" }
    return $Text.Replace($Old,$New)
}

$src=Join-Path $PSScriptRoot 'c1025'
$contract=Join-Path $Root 'PrePoMax/AsterMaxSurfaceMechanicsContract.cs'
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $contract) -or !(Test-Path $exporter)){ throw 'C10.25 requires C10.24 surface mechanics first.' }

Copy-Item (Join-Path $src 'AsterMaxSurfaceMechanicsContract.cs') $contract -Force
$e=Get-Content (Join-Path $src 'AsterMaxCodeAsterBodyLoadExporter.cs') -Raw
$e=$e.Replace('AsterMaxCodeAsterBodyLoadExporter','AsterMaxCodeAsterNativeExporter')
Set-Content $exporter $e -Encoding UTF8

# Expose Gravity directly; Centrifugal remains available in the full Loads dialog.
$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $ui -Raw
if(-not $u.Contains('CommandTile("Gravity"')) {
    $anchor='                CommandTile("Pressure", "LOAD", () => CreateAsterMaxPressure()),'
    $insert=$anchor+[Environment]::NewLine+'                CommandTile("Gravity", "BODY", () => tsmiCreateLoad_Click(null, new CaeGlobals.EventArgs<int>(4))),'
    $u=Replace-Required $u $anchor $insert 'Gravity tile'
    Set-Content $ui $u -Encoding UTF8
}

Write-Host 'C10.25 density + Gravity/PESANTEUR + Centrifugal/ROTATION backend applied.' -ForegroundColor Green
