param(
    [Parameter(Mandatory=$true)][string]$Dist,
    [string]$OutDir
)
$ErrorActionPreference='Stop'

if([string]::IsNullOrWhiteSpace($OutDir)){ $OutDir=Join-Path $Dist 'Validation\C10.24-Surface-Exporter' }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$fixture=(Resolve-Path (Join-Path $PSScriptRoot 'c1024\pressure-frictionless-contract.json')).Path
$exe=(Resolve-Path (Join-Path $Dist 'AsterMax Mechanical.exe')).Path
$jsonDll=(Resolve-Path (Join-Path $Dist 'Newtonsoft.Json.dll')).Path

[System.Reflection.Assembly]::LoadFrom($jsonDll) | Out-Null
$assembly=[System.Reflection.Assembly]::LoadFrom($exe)
$jobjectType=[Type]::GetType('Newtonsoft.Json.Linq.JObject, Newtonsoft.Json', $true)
$parse=$jobjectType.GetMethod('Parse',[Type[]]@([string]))
$contract=$parse.Invoke($null,@([IO.File]::ReadAllText($fixture)))
$type=$assembly.GetType('PrePoMax.AsterMaxCodeAsterNativeExporter',$true)
$flags=[System.Reflection.BindingFlags]::Public -bor [System.Reflection.BindingFlags]::Static
$method=$type.GetMethod('ExportContract',$flags)
if($null -eq $method){ throw 'Compiled exporter does not expose ExportContract.' }
$null=$method.Invoke($null,@($contract,$OutDir,'surface-cube'))

$comm=Join-Path $OutDir 'surface-cube.comm'
$mail=Join-Path $OutDir 'surface-cube.mail'
$manifest=Join-Path $OutDir 'surface-cube.native-export.json'
foreach($f in @($comm,$mail,$manifest)){ if(-not(Test-Path $f)){ throw "Expected exporter evidence missing: $f" } }

$commText=Get-Content $comm -Raw
$mailText=Get-Content $mail -Raw
if(-not $commText.Contains('PRES_REP')){ throw 'PRES_REP missing from compiled exporter output.' }
if(-not $commText.Contains('FACE_IMPO')){ throw 'FACE_IMPO missing from compiled exporter output.' }
if(-not $commText.Contains('DNOR=0')){ throw 'DNOR=0 missing from compiled exporter output.' }
if(-not $commText.Contains('MECA_STATIQUE')){ throw 'MECA_STATIQUE missing from compiled exporter output.' }
if(-not $commText.Contains("FORCE=('REAC_NODA',)")){ throw 'REAC_NODA missing from compiled exporter output.' }
if(-not $mailText.Contains('QUAD4')){ throw 'Surface skin QUAD4 elements missing from .mail.' }
if(-not $mailText.Contains('GROUP_MA')){ throw 'Surface GROUP_MA missing from .mail.' }

$evidence=Get-Content $manifest -Raw | ConvertFrom-Json
if($evidence.pressure_uses_pres_rep -ne $true){ throw 'Pressure manifest flag is false.' }
if($evidence.frictionless_uses_face_impo_dnor -ne $true){ throw 'Frictionless manifest flag is false.' }
$r=@($evidence.expected_external_resultant_n)
if($r.Count -ne 3){ throw 'External resultant vector missing.' }
if([Math]::Abs([double]$r[0] + 100.0) -gt 1e-8 -or [Math]::Abs([double]$r[1]) -gt 1e-8 -or [Math]::Abs([double]$r[2]) -gt 1e-8){
    throw "Pressure resultant mismatch. Expected [-100,0,0] N; got [$($r -join ',')]."
}

[ordered]@{
    status='PASS'
    compiled_exporter=$true
    pressure_semantics='PRES_REP'
    frictionless_semantics='FACE_IMPO_DNOR_0'
    expected_external_resultant_n=$r
    solver_execution='NOT_RUN_IN_THIS_GATE'
    fea_values_invented=$false
} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutDir 'C10.24_SURFACE_EXPORTER_TEST.json') -Encoding UTF8

Write-Host 'C10.24 compiled surface exporter regression PASS.' -ForegroundColor Green
