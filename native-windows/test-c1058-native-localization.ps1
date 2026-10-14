param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$pre=Join-Path $Root 'PrePoMax'
$proj=Join-Path $pre 'PrePoMax.csproj'
$svc=Join-Path $pre 'AsterMaxLocalization.cs'
$resx=Join-Path $pre 'Localization\Strings.es-CL.resx'
if(-not (Test-Path $svc)){ throw 'AsterMaxLocalization.cs missing after C10.58 patch.' }
if(-not (Test-Path $resx)){ throw 'Strings.es-CL.resx missing after C10.58 patch.' }
if(-not (Test-Path $proj)){ throw 'PrePoMax.csproj missing.' }
$p=Get-Content $proj -Raw
$s=Get-Content $svc -Raw
$r=Get-Content $resx -Raw
$required=@('ResourceManager','CultureInfo','es-CL')
foreach($x in $required){ if(-not $s.Contains($x)){ throw "Localization service contract missing: $x" } }
foreach($x in @('Localization\Strings.es-CL.resx','AsterMaxLocalization.cs')){ if(-not $p.Contains($x)){ throw "Project localization include missing: $x" } }
foreach($x in @('Home','Geometry','Model','Mesh','Solution','Results','StaticStructural','GenerateMesh','EquivalentStress')){ if(-not $r.Contains('name="'+$x+'"')){ throw "Resource key missing: $x" } }
# Regression guard: C10.57 removed periodic UI translation. C10.58 must not reintroduce it.
$legacy=Join-Path $pre 'AsterMaxSpanishChile.cs'
if(Test-Path $legacy){
  $l=Get-Content $legacy -Raw
  if($l -match 'System\.Windows\.Forms\.Timer|Interval\s*=\s*350|Tick\s*\+='){ throw 'Periodic translation polling regression detected.' }
}
Write-Host 'PASS C10.58 native localization static contract.'