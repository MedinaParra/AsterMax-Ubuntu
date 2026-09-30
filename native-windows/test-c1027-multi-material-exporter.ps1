param(
    [Parameter(Mandatory=$true)][string]$Dist,
    [string]$OutDir
)
$ErrorActionPreference='Stop'

if([string]::IsNullOrWhiteSpace($OutDir)){ $OutDir=Join-Path $Dist 'Validation\C10.27-Multi-Material' }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$fixture=(Resolve-Path (Join-Path $PSScriptRoot 'c1027\multi-material-contract.json')).Path
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
$null=$method.Invoke($null,@($contract,$OutDir,'multi-material'))

$comm=Join-Path $OutDir 'multi-material.comm'
$manifest=Join-Path $OutDir 'multi-material.native-export.json'
foreach($f in @($comm,$manifest)){ if(-not(Test-Path $f)){ throw "Expected exporter evidence missing: $f" } }
$commText=Get-Content $comm -Raw
$materialDefinitions=([regex]::Matches($commText,'=DEFI_MATERIAU\(ELAS=_F\(')).Count
if($materialDefinitions -ne 2){ throw "Expected two DEFI_MATERIAU definitions; found $materialDefinitions." }
if(-not $commText.Contains('MATER=mat0')){ throw 'First material assignment missing.' }
if(-not $commText.Contains('MATER=mat1')){ throw 'Second material assignment missing.' }
if(-not $commText.Contains('RHO=0.00000000785')){ throw 'Steel density missing.' }
if(-not $commText.Contains('RHO=0.00000000277')){ throw 'Aluminum density missing.' }

$evidence=Get-Content $manifest -Raw | ConvertFrom-Json
if([int]$evidence.material_count -ne 2){ throw 'Material count evidence mismatch.' }
if([int]$evidence.material_assignment_count -ne 2){ throw 'Material assignment count evidence mismatch.' }
if($evidence.material_assignment_mode -ne 'SOLID_SECTION_GROUPS'){ throw 'Material assignment mode is not SOLID_SECTION_GROUPS.' }

[ordered]@{
    status='PASS'
    compiled_exporter=$true
    material_count=[int]$evidence.material_count
    material_assignment_count=[int]$evidence.material_assignment_count
    code_aster_semantics='DEFI_MATERIAU + AFFE_MATERIAU by GROUP_MA'
    solver_execution='NOT_RUN_IN_THIS_GATE'
    fea_values_invented=$false
} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutDir 'C10.27_MULTI_MATERIAL_TEST.json') -Encoding UTF8

Write-Host 'C10.27 compiled multi-material exporter regression PASS.' -ForegroundColor Green
