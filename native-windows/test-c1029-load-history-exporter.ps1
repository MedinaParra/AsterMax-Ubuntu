param([Parameter(Mandatory=$true)][string]$Dist,[string]$OutDir)
$ErrorActionPreference='Stop'
if([string]::IsNullOrWhiteSpace($OutDir)){ $OutDir=Join-Path $Dist 'Validation\C10.29-Load-History' }
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
[System.Reflection.Assembly]::LoadFrom($jsonFile.FullName) | Out-Null
$assembly=[System.Reflection.Assembly]::LoadFrom($exe)
$jt=[Type]::GetType('Newtonsoft.Json.Linq.JObject, Newtonsoft.Json',$true)
$contract=$jt.GetMethod('Parse',[Type[]]@([string])).Invoke($null,@([IO.File]::ReadAllText($fixture)))
$type=$assembly.GetType('PrePoMax.AsterMaxCodeAsterNativeExporter',$true)
$flags=[System.Reflection.BindingFlags]::Public -bor [System.Reflection.BindingFlags]::Static
$method=$type.GetMethod('ExportContract',$flags)
if($null -eq $method){ throw 'Compiled exporter does not expose ExportContract.' }
$null=$method.Invoke($null,@($contract,$OutDir,'load-history'))

$comm=Join-Path $OutDir 'load-history.comm'
$manifest=Join-Path $OutDir 'load-history.native-export.json'
foreach($p in @($comm,$manifest)){ if(-not(Test-Path $p)){ throw "Missing C10.29 evidence: $p" } }
$txt=Get-Content $comm -Raw
foreach($token in @('DEFI_FONCTION','DEFI_LIST_REEL','FONC_MULT=amp0','LIST_INST=linst','MECA_STATIQUE')){
 if(-not $txt.Contains($token)){ throw "C10.29 compiled exporter missing $token" }
}
if(-not $txt.Contains("VALE=(0,0,0.5,0.5,1,1,)")){ throw 'Amplitude points changed or missing.' }
$m=Get-Content $manifest -Raw | ConvertFrom-Json
if($m.load_history_enabled -ne $true){ throw 'load_history_enabled is false.' }
if($m.load_history_amplitude -ne 'Ramp'){ throw 'Wrong load history amplitude.' }
if([Math]::Abs([double]$m.load_history_final_multiplier-1.0) -gt 1e-12){ throw 'Wrong final multiplier.' }
$times=@($m.analysis_times)
if($times.Count -ne 3 -or [double]$times[0] -ne 0 -or [double]$times[1] -ne 0.5 -or [double]$times[2] -ne 1){ throw 'Analysis time list mismatch.' }
$bridge=Join-Path $Dist 'AsterMaxTools\bridge-c964-med-results.py'
if(-not(Test-Path $bridge)){ throw 'Packaged MED bridge missing.' }
$bridgeText=Get-Content $bridge -Raw
if(-not $bridgeText.Contains('ASTERMAX_MED_STEP_SELECTION')){ throw 'Packaged MED bridge lacks multi-instant selection.' }
if(-not $bridgeText.Contains('select_field_step')){ throw 'Packaged MED bridge lacks last-instant selector.' }

$r=@($m.expected_external_resultant_n)
if([Math]::Abs([double]$r[0]-200) -gt 1e-8 -or [Math]::Abs([double]$r[1]-50) -gt 1e-8 -or [Math]::Abs([double]$r[2]+100) -gt 1e-8){ throw 'Final resultant mismatch.' }
[ordered]@{status='PASS';compiled_exporter=$true;amplitude='Ramp';analysis_times=$times;final_resultant_n=$r;solver_execution='NOT_RUN_IN_THIS_GATE';fea_values_invented=$false} |
 ConvertTo-Json -Depth 6 | Set-Content (Join-Path $OutDir 'C10.29_LOAD_HISTORY_TEST.json') -Encoding UTF8
Write-Host 'C10.29 compiled load-history exporter regression PASS.' -ForegroundColor Green
