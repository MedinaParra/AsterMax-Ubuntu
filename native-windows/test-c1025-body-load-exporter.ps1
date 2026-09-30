param(
    [Parameter(Mandatory=$true)][string]$Dist,
    [string]$OutDir
)
$ErrorActionPreference='Stop'

if([string]::IsNullOrWhiteSpace($OutDir)){ $OutDir=Join-Path $Dist 'Validation\C10.25-Body-Loads' }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$fixture=(Resolve-Path (Join-Path $PSScriptRoot 'c1025\gravity-rotation-contract.json')).Path
$exe=(Resolve-Path (Join-Path $Dist 'AsterMax Mechanical.exe')).Path

$jsonFile=Get-ChildItem -Path $Dist -Recurse -File -Filter 'Newtonsoft.Json.dll' | Select-Object -First 1
if($null -eq $jsonFile){ throw 'Newtonsoft.Json.dll was not found in the assembled distribution.' }
$script:assemblyRoots=@((Resolve-Path $Dist).Path)
$script:assemblyRoots += Get-ChildItem -Path $Dist -Recurse -Directory | Select-Object -ExpandProperty FullName
[System.AppDomain]::CurrentDomain.add_AssemblyResolve({
    param($sender,$args)
    $simple=(New-Object System.Reflection.AssemblyName($args.Name)).Name+'.dll'
    foreach($root in $script:assemblyRoots){
        $candidate=Join-Path $root $simple
        if(Test-Path $candidate){ return [System.Reflection.Assembly]::LoadFrom($candidate) }
    }
    return $null
})
[System.Reflection.Assembly]::LoadFrom($jsonFile.FullName) | Out-Null
$assembly=[System.Reflection.Assembly]::LoadFrom($exe)
$jobjectType=[Type]::GetType('Newtonsoft.Json.Linq.JObject, Newtonsoft.Json',$true)
$parse=$jobjectType.GetMethod('Parse',[Type[]]@([string]))
$contract=$parse.Invoke($null,@([IO.File]::ReadAllText($fixture)))
$type=$assembly.GetType('PrePoMax.AsterMaxCodeAsterNativeExporter',$true)
$flags=[System.Reflection.BindingFlags]::Public -bor [System.Reflection.BindingFlags]::Static
$method=$type.GetMethod('ExportContract',$flags)
if($null -eq $method){ throw 'Compiled exporter does not expose ExportContract.' }
$null=$method.Invoke($null,@($contract,$OutDir,'body-cube'))

$comm=Join-Path $OutDir 'body-cube.comm'
$manifest=Join-Path $OutDir 'body-cube.native-export.json'
foreach($f in @($comm,$manifest)){ if(-not(Test-Path $f)){ throw "Expected exporter evidence missing: $f" } }
$commText=Get-Content $comm -Raw
if(-not $commText.Contains('RHO=0.00000000785')){ throw 'Material RHO missing or unit value changed.' }
if(-not $commText.Contains('PESANTEUR=_F(')){ throw 'PESANTEUR missing.' }
if(-not $commText.Contains('GRAVITE=9810')){ throw 'Gravity magnitude missing.' }
if(-not $commText.Contains('DIRECTION=(0,0,-1)')){ throw 'Gravity direction missing.' }
if(-not $commText.Contains('ROTATION=_F(')){ throw 'ROTATION missing.' }
if(-not $commText.Contains('VITESSE=100')){ throw 'Rotational speed missing.' }
if(-not $commText.Contains('AXE=(0,0,1)')){ throw 'Rotation axis missing.' }
if(-not $commText.Contains('CENTRE=(0,0,0)')){ throw 'Rotation center missing.' }

$evidence=Get-Content $manifest -Raw | ConvertFrom-Json
if($evidence.gravity_uses_pesanteur -ne $true){ throw 'Gravity manifest flag is false.' }
if($evidence.rotation_uses_rotation -ne $true){ throw 'Rotation manifest flag is false.' }
if($evidence.external_resultant_complete -ne $false){ throw 'Body-load resultant must remain explicitly incomplete in C10.25.' }
if([Math]::Abs([double]$evidence.material_density_tonne_per_mm3-7.85e-9) -gt 1e-15){ throw 'Material density evidence mismatch.' }

[ordered]@{
    status='PASS'
    compiled_exporter=$true
    density_tonne_per_mm3=[double]$evidence.material_density_tonne_per_mm3
    gravity_semantics='PESANTEUR'
    rotation_semantics='ROTATION'
    external_resultant_complete=$false
    solver_execution='NOT_RUN_IN_THIS_GATE'
    fea_values_invented=$false
} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutDir 'C10.25_BODY_LOAD_TEST.json') -Encoding UTF8

Write-Host 'C10.25 compiled gravity/rotation exporter regression PASS.' -ForegroundColor Green
