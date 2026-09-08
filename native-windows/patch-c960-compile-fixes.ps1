param([string]$Root)
$ErrorActionPreference='Stop'

$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(!(Test-Path $ui)){ throw 'AsterMaxNativeUi.cs missing.' }
$t=Get-Content $ui -Raw
$t=$t.Replace('CommandButton("Export Solver Contract", () => ExportAsterMaxModelContract())','CommandTile("Export Solver Contract", "SOLVER", () => ExportAsterMaxModelContract(), true)')
$t=$t.Replace('InfoChip("Code_Aster | model contract v0 | no synthetic results")','InfoCard("Code_Aster | model contract v0 | no synthetic results")')
Set-Content $ui $t -Encoding UTF8

$partial=Join-Path $Root 'PrePoMax/AsterMaxModelContractUi.cs'
if(!(Test-Path $partial)){ throw 'AsterMaxModelContractUi.cs missing.' }
$p=Get-Content $partial -Raw
if(-not $p.Contains('using CaeGlobals;')){
  $p=$p.Replace('using System.Windows.Forms;','using System.Windows.Forms;' + [Environment]::NewLine + 'using CaeGlobals;')
}
Set-Content $partial $p -Encoding UTF8

Write-Host 'C9.60 compile integration fixes applied.' -ForegroundColor Green
