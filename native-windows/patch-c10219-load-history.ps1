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



# Static Structural history v2: expose existing native editors, preserving undo/redo.
$u=Get-Content $ui -Raw
if(-not $u.Contains('CommandTile("Tablas de carga"')) {
    $anchor='                CommandTile("Pressure", "LOAD", () => CreateAsterMaxPressure()),'
    if(-not $u.Contains($anchor)){ throw 'Static history UI anchor missing.' }
    $insert=@'
                CommandTile("Tablas de carga", "AMPLITUDE", () => tsmiCreateAmplitude_Click(null, EventArgs.Empty)),
                CommandTile("Desplazamiento", "SUPPORT", () => tsmiCreateBC_Click(null, new CaeGlobals.EventArgs<int>(1))),
'@
    $u=$u.Replace($anchor,$anchor+[Environment]::NewLine+$insert.TrimEnd())
    Set-Content $ui $u -Encoding UTF8
}

# A nonzero prescribed displacement is an excitation even without force objects.
$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
$w=Get-Content $workspace -Raw
$old='            if (r.LoadCount == 0) r.Issues.Add("BLOCK:no_loads");'
$new=@'
            bool imposedExcitation=model.StepCollection.StepsList
                .Where(step=>!(step is CaeModel.InitialStep) && step.Active && step.Valid)
                .SelectMany(step=>step.BoundaryConditions.Values).OfType<CaeModel.DisplacementRotation>()
                .Any(bc=>bc.Active && bc.Valid && new[]{bc.U1,bc.U2,bc.U3}.Any(value=>!Double.IsNaN(value) && !Double.IsInfinity(value) && value!=0));
            if (r.LoadCount == 0 && !imposedExcitation) r.Issues.Add("BLOCK:no_loads");
'@
if($w.Contains($old)){ $w=$w.Replace($old,$new.TrimEnd()); Set-Content $workspace $w -Encoding UTF8 }
elseif(-not $w.Contains('bool imposedExcitation=')){ throw 'Static history readiness anchor missing.' }

Write-Host 'Static Structural history v2: independent load/displacement histories and native editor shortcuts applied.' -ForegroundColor Green
