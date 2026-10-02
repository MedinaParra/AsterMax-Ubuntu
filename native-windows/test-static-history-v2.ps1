param([Parameter(Mandatory=$true)][string]$Dist,[string]$OutDir)
$ErrorActionPreference='Stop'
trap { Write-Host $_.ScriptStackTrace; Write-Host $_.Exception.ToString(); throw }
if([string]::IsNullOrWhiteSpace($OutDir)){ $OutDir=Join-Path $Dist 'Validation\Static-History-v2' }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$fixture=(Resolve-Path (Join-Path $PSScriptRoot 'c1029\load-history-contract.json')).Path
$exe=(Resolve-Path (Join-Path $Dist 'AsterMax Mechanical.exe')).Path
$jsonFile=Get-ChildItem -Path $Dist -Recurse -File -Filter 'Newtonsoft.Json.dll' | Select-Object -First 1
if($null -eq $jsonFile){ throw 'Newtonsoft.Json.dll missing.' }
$script:assemblyRoots=@((Resolve-Path $Dist).Path)
$script:assemblyRoots += Get-ChildItem -Path $Dist -Recurse -Directory | Select-Object -ExpandProperty FullName
[System.AppDomain]::CurrentDomain.add_AssemblyResolve({
 param($sender,$args)
 $simple=(New-Object System.Reflection.AssemblyName($args.Name)).Name+'.dll'
 foreach($root in $script:assemblyRoots){ $candidate=Join-Path $root $simple; if(Test-Path $candidate){ return [System.Reflection.Assembly]::LoadFrom($candidate) } }
 return $null
})
$jsonAssembly=[System.Reflection.Assembly]::LoadFrom($jsonFile.FullName)
$assembly=[System.Reflection.Assembly]::LoadFrom($exe)
$jt=$jsonAssembly.GetType('Newtonsoft.Json.Linq.JObject',$true)
$contract=$jt.GetMethod('Parse',[Type[]]@([string])).Invoke($null,@([IO.File]::ReadAllText($fixture)))
$type=$assembly.GetType('PrePoMax.AsterMaxCodeAsterNativeExporter',$true)
$flags=[System.Reflection.BindingFlags]::Public -bor [System.Reflection.BindingFlags]::Static
$method=$type.GetMethod('ExportContract',$flags)
if($null -eq $method){ throw 'Compiled exporter does not expose ExportContract.' }

function Read-Fixture { return (Get-Content $fixture -Raw | ConvertFrom-Json) }
function Export-Case($data,[string]$name) {
    $json=[string]($data | ConvertTo-Json -Depth 50)
    $c=$jt.GetMethod('Parse',[Type[]]@([string])).Invoke($null,@($json))
    $null=$method.Invoke($null,@($c,$OutDir,$name))
    return (Get-Content (Join-Path $OutDir ($name+'.native-export.json')) -Raw | ConvertFrom-Json)
}
function Require-Rejected($data,[string]$name,[string]$reason) {
    try { $null=Export-Case $data $name }
    catch {
        if($_.Exception.ToString() -notmatch $reason){ throw "Unexpected rejection for ${name}: $_" }
        return
    }
    throw "Invalid case was accepted: $name"
}

# One ramp, another curve with a longer time range, and a constant nodal load.
$data=Read-Fixture
$data.amplitudes | Add-Member -NotePropertyName Other -NotePropertyValue ([pscustomobject]@{points=@(@(0,1),@(0.25,2),@(2,3))})
$data.loads+= [pscustomobject]@{name='Other traction';type='surface_traction';surface='TRACTION_X';fx_n_per_mm2=1;fy_n_per_mm2=0;fz_n_per_mm2=0;amplitude='Other'}
$data.loads+= [pscustomobject]@{name='Constant force';type='nodal_force_per_node';group='TRACTION_X_NODES';fx_per_node_n=10;fy_per_node_n=0;fz_per_node_n=0}
$m=Export-Case $data 'independent-loads'
$txt=Get-Content (Join-Path $OutDir 'independent-loads.comm') -Raw
foreach($token in @('_F(CHARGE=load0,FONC_MULT=amp0)','_F(CHARGE=load1,FONC_MULT=amp1)','_F(CHARGE=load2)')) {
    if(-not $txt.Contains($token)){ throw "Missing independent excitation: $token" }
}
$expectedTimes=@(0.0,0.25,0.5,1.0,2.0)
$actualTimes=@($m.analysis_times)
if($actualTimes.Count -ne $expectedTimes.Count){ throw "Merged instant list count is incorrect. Actual=$($actualTimes -join ';')" }
for($i=0;$i -lt $expectedTimes.Count;$i++){
    if([Math]::Abs([double]$actualTimes[$i]-[double]$expectedTimes[$i]) -gt 1e-12){
        throw "Merged instant list is incorrect at index $i. Actual=$($actualTimes -join ';')"
    }
}
$r=@($m.expected_external_resultant_n)
if([Math]::Abs($r[0]-540) -gt 1e-8 -or [Math]::Abs($r[1]-50) -gt 1e-8 -or [Math]::Abs($r[2]+100) -gt 1e-8){ throw 'Independent resultant is incorrect.' }
$moment=@($m.expected_external_moment_n_mm)
if($moment.Count -ne 3 -or [Math]::Abs([double]$moment[0]+750) -gt 1e-8 -or [Math]::Abs([double]$moment[1]-3700) -gt 1e-8 -or [Math]::Abs([double]$moment[2]+2200) -gt 1e-8){ throw "Independent moment is incorrect: $($moment -join ',')." }
if($m.load_history_groups.Count -ne 3){ throw 'Expected three load concepts.' }

# Displacement-driven analysis needs no external force concept.
$data=Read-Fixture
$data.loads=@()
$data.supports+= [pscustomobject]@{name='Travel';type='displacement';group='TRACTION_X_NODES';dx=0.5;amplitude='Ramp'}
$m=Export-Case $data 'displacement-only'
$txt=Get-Content (Join-Path $OutDir 'displacement-only.comm') -Raw
if(-not $txt.Contains('_F(CHARGE=bct0,FONC_MULT=amp0)')){ throw 'Displacement multiplier missing.' }
if($txt.Contains('load0=AFFE_CHAR_MECA')){ throw 'Empty load concept emitted.' }
if($m.displacement_history_count -ne 1 -or $m.load_count -ne 0){ throw 'Wrong displacement-only manifest.' }

# Another displacement curve can coexist with a constant directional constraint.
$data.supports+= [pscustomobject]@{name='Guide';type='displacement';group='TRACTION_X_NODES';dy=0}
$null=Export-Case $data 'displacement-guide'
$data.supports+= [pscustomobject]@{name='Conflict';type='displacement';group='TRACTION_X_NODES';dx=0}
Require-Rejected $data 'overlap' 'Overlapping displacement'

foreach($kind in @('duplicate','decreasing','missing','nonnumeric','interpolation','infinite')) {
    $data=Read-Fixture
    switch($kind) {
        'duplicate' { $data.amplitudes.Ramp.points=@(@(0,0),@(0,1)) }
        'decreasing' { $data.amplitudes.Ramp.points=@(@(1,0),@(0,1)) }
        'missing' { $data.loads[0].amplitude='Absent' }
        'nonnumeric' { $data.amplitudes.Ramp.points=@(@(0,0),@(1,'bad')) }
        'interpolation' { $data.amplitudes.Ramp.interpolation='SPLINE' }
        'infinite' { $data.amplitudes.Ramp.points=@(@(0,0),@(1,[double]::PositiveInfinity)) }
    }
    Require-Rejected $data $kind 'amplitude|Amplitude'
}
# Exercise a live FeModel -> contract -> compiled exporter, not just JSON fixtures.
# The application itself probes dist\lib via AsterMax Mechanical.exe.config. This
# reflection host is PowerShell.exe, so it must explicitly load UI dependencies
# from the assembled distribution before resolving FrmMain.
$managedUiDependencies=@('CaeGlobals.dll','CaeJob.dll','CaeMesh.dll','CaeResults.dll','CaeModel.dll','vtkControl.dll','UserControls.dll')
foreach($dependency in $managedUiDependencies){
    $dependencyFile=Get-ChildItem -Path $Dist -Recurse -File -Filter $dependency | Select-Object -First 1
    if($null -eq $dependencyFile){ throw "Packaged managed dependency missing: $dependency" }
    [System.Reflection.Assembly]::LoadFrom($dependencyFile.FullName) | Out-Null
}
$mainType=$assembly.GetType('PrePoMax.FrmMain',$true)
$privateStatic=[Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Static
$model=$mainType.GetMethod('CreateAsterMaxStatusFixture',$privateStatic).Invoke($null,@())
$step=$model.StepCollection.StepsList[0]
$step.Loads.Clear()
$disp=New-Object CaeModel.DisplacementRotation -ArgumentList @('Travel','LOAD',[CaeGlobals.RegionTypeEnum]::NodeSetName,$false,$false,0.0)
$disp.U1=0.5
$disp.AmplitudeName='TravelRamp'
$points=[double[][]]@([double[]]@(0,0),[double[]]@(1,1))
$amp=New-Object CaeModel.AmplitudeTabular -ArgumentList @('TravelRamp',$points)
$model.Amplitudes.Add('TravelRamp',$amp)
$step.AddBoundaryCondition($disp)
$buildMethod=$assembly.GetType('PrePoMax.AsterMaxSurfaceMechanicsContract',$true).GetMethod('Build',$flags)
$live=$buildMethod.Invoke($null,@($model))
$liveText=$live.ToString() | ConvertFrom-Json
if($liveText.supports[1].amplitude -ne 'TravelRamp'){ throw 'Live displacement amplitude was lost.' }
$null=$method.Invoke($null,@($live,$OutDir,'live-displacement'))
$ready=$assembly.GetType('PrePoMax.AsterMaxPreSolveReadiness',$true).GetMethod('Evaluate',$flags).Invoke($null,@($model))
if($ready.Issues -contains 'BLOCK:no_loads'){ throw 'Displacement-only live model is still blocked by readiness.' }
$states=$mainType.GetMethod('EvaluateAsterMaxSectionStates',$privateStatic).Invoke($null,@($model))
if($states['loads'].State -ne 2 -or $states['supports'].State -ne 2){ throw 'Live displacement workflow indicators are incorrect.' }

[ordered]@{status='PASS';compiled_exporter=$true;cases=11;solver_execution='NOT_RUN';fea_results_included=$false} |
    ConvertTo-Json | Set-Content (Join-Path $OutDir 'STATIC_HISTORY_V2_TEST.json') -Encoding UTF8
Write-Host 'Static Structural independent load/displacement history tests PASS.'
