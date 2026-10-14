param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$f=Join-Path $Root 'PrePoMax\AsterMaxProgressDialog.cs'
$p=Join-Path $Root 'PrePoMax\PrePoMax.csproj'
if(-not(Test-Path $f)){throw 'AsterMaxProgressDialog.cs missing'}
$c=Get-Content $f -Raw
$proj=Get-Content $p -Raw
foreach($x in @('AsterMaxProgressSnapshot','ProgressBarStyle.Marquee','Percent.HasValue','Remaining.HasValue','Tiempo restante: calculando','CancelRequested','BeginInvoke','Stopwatch','Detalles','FALLÓ')){if(-not$c.Contains($x)){throw "C10.60 contract missing: $x"}}
if(-not$proj.Contains('AsterMaxProgressDialog.cs')){throw 'Progress dialog not compiled by project'}
# Guard against fabricated time-driven progress: timer may update elapsed label only, never progress value.
if($c -match '_uiTimer\.Tick[\s\S]{0,250}_bar\.Value'){throw 'Progress value must not be advanced by elapsed-time timer'}
Write-Host 'PASS C10.60 progress UI static contract.'