param([string]$Root)
$ErrorActionPreference='Stop'
$path=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(!(Test-Path $path)){ throw 'AsterMaxNativeUi.cs missing.' }
$t=Get-Content $path -Raw
if($t.Contains('Export Solver Contract')){ Write-Host 'C9.60 Solution command already present.'; exit 0 }
$old=@'
            ribbon.TabPages.Add(BuildRibbonPage("Solution", new Control[] {
                StateCard("Solver", "Code_Aster integration path"),
                InfoCard("Solution requests stay in the analysis tree; no synthetic results")
            }));
'@
$new='            ribbon.TabPages.Add(BuildRibbonPage("Solution", new Control[] { InfoChip("Code_Aster adapter: next integration gate") }));'
if(-not $t.Contains($old)){ throw 'Current polished Solution ribbon block not found.' }
$t=$t.Replace($old,$new)
Set-Content $path $t -Encoding UTF8
Write-Host 'C9.60 Solution ribbon normalized for bridge injection.' -ForegroundColor Green
