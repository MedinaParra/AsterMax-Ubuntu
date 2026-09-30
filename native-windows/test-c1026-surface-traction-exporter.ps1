param(
    [Parameter(Mandatory=$true)][string]$Dist,
    [string]$OutDir
)
$ErrorActionPreference='Stop'

if([string]::IsNullOrWhiteSpace($OutDir)){ $OutDir=Join-Path $Dist 'Validation\C10.26-Surface-Traction' }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$fixture=(Resolve-Path (Join-Path $PSScriptRoot 'c1026\surface-traction-contract.json')).Path
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
$null=$method.Invoke($null,@($contract,$OutDir,'traction-cube'))

$comm=Join-Path $OutDir 'traction-cube.comm'
$manifest=Join-Path $OutDir 'traction-cube.native-export.json'
foreach($f in @($comm,$manifest)){ if(-not(Test-Path $f)){ throw "Expected exporter evidence missing: $f" } }
$commText=Get-Content $comm -Raw
if(-not $commText.Contains('FORCE_FACE=(')){ throw 'FORCE_FACE missing from compiled exporter output.' }
if(-not $commText.Contains('FX=2')){ throw 'Surface traction FX missing.' }
if(-not $commText.Contains('FY=0.5')){ throw 'Surface traction FY missing.' }
if(-not $commText.Contains('FZ=-1')){ throw 'Surface traction FZ missing.' }

$evidence=Get-Content $manifest -Raw | ConvertFrom-Json
if($evidence.surface_traction_uses_force_face -ne $true){ throw 'Surface traction manifest flag is false.' }
if($evidence.external_resultant_complete -ne $true){ throw 'Surface traction should have a complete independent resultant.' }
$r=@($evidence.expected_external_resultant_n)
if($r.Count -ne 3){ throw 'External resultant vector missing.' }
if([Math]::Abs([double]$r[0]-200.0) -gt 1e-8 -or [Math]::Abs([double]$r[1]-50.0) -gt 1e-8 -or [Math]::Abs([double]$r[2]+100.0) -gt 1e-8){
    throw "Surface traction resultant mismatch. Expected [200,50,-100] N; got [$($r -join ',')]."
}

[ordered]@{
    status='PASS'
    compiled_exporter=$true
    surface_traction_semantics='FORCE_FACE'
    expected_external_resultant_n=$r
    external_resultant_complete=$true
    solver_execution='NOT_RUN_IN_THIS_GATE'
    fea_values_invented=$false
} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutDir 'C10.26_SURFACE_TRACTION_TEST.json') -Encoding UTF8

Write-Host 'C10.26 compiled surface-traction exporter regression PASS.' -ForegroundColor Green
