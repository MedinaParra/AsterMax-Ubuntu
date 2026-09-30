param([string]$Root)
$ErrorActionPreference='Stop'

$src=Join-Path $PSScriptRoot 'c1029'
$contract=Join-Path $Root 'PrePoMax/AsterMaxSurfaceMechanicsContract.cs'
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $contract) -or !(Test-Path $exporter)){ throw 'C10.29 requires C10.27 multi-material backend first.' }

Copy-Item (Join-Path $src 'AsterMaxSurfaceMechanicsContract.cs') $contract -Force
$e=Get-Content (Join-Path $src 'AsterMaxCodeAsterLoadHistoryExporter.cs') -Raw
$e=$e.Replace('AsterMaxCodeAsterLoadHistoryExporter','AsterMaxCodeAsterNativeExporter')
Set-Content $exporter $e -Encoding UTF8

$solve=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=Get-Content $solve -Raw
if(-not $s.Contains('ASTERMAX_MED_STEP_SELECTION')) {
    $anchor='            bridgePsi.EnvironmentVariables["ASTERMAX_MED_BRIDGE_MODE"]="production";'
    if(-not $s.Contains($anchor)){ throw 'C10.29 MED bridge environment anchor missing.' }
    $insert=$anchor+[Environment]::NewLine+'            bridgePsi.EnvironmentVariables["ASTERMAX_MED_STEP_SELECTION"]="last";'
    $s=$s.Replace($anchor,$insert)
    Set-Content $solve $s -Encoding UTF8
}

$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $ui -Raw
if(-not $u.Contains('Load History')) {
    $anchor='                InfoCard("Quadratic solids by default • scope fingerprint • reaction equilibrium • component-first von Mises"),'
    if($u.Contains($anchor)){
        $u=$u.Replace($anchor,$anchor+[Environment]::NewLine+'                InfoCard("Load History • AmplitudeTabular → DEFI_FONCTION / FONC_MULT"),')
        Set-Content $ui $u -Encoding UTF8
    }
}

Write-Host 'C10.29 tabular load histories + last-instant MED selection applied.' -ForegroundColor Green
