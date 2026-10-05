param([string]$Root)
$ErrorActionPreference='Stop'

$src=Join-Path $PSScriptRoot 'c1027'
$contract=Join-Path $Root 'PrePoMax/AsterMaxSurfaceMechanicsContract.cs'
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $contract) -or !(Test-Path $exporter)){ throw 'C10.27 requires C10.26 surface-traction backend first.' }

Copy-Item (Join-Path $src 'AsterMaxSurfaceMechanicsContract.cs') $contract -Force
$e=Get-Content (Join-Path $src 'AsterMaxCodeAsterMultiMaterialExporter.cs') -Raw
$e=$e.Replace('AsterMaxCodeAsterMultiMaterialExporter','AsterMaxCodeAsterNativeExporter')
Set-Content $exporter $e -Encoding UTF8

Write-Host 'C10.27 multi-material SolidSection -> DEFI_MATERIAU/AFFE_MATERIAU backend applied.' -ForegroundColor Green
