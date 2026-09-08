param([string]$Root)
$ErrorActionPreference = 'Stop'

$main = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$t = Get-Content $main -Raw
$old = '                ApplyAsterMaxNativeUi();'
$new = '                this.Shown += (asterSender, asterArgs) => this.BeginInvoke(new Action(ApplyAsterMaxNativeUi));'
if(-not $t.Contains($old)){ throw 'AsterMax UI lifecycle anchor not found' }
$t = $t.Replace($old,$new)
Set-Content $main $t -Encoding UTF8

Write-Host 'AsterMax UI delayed until after native FrmMain_Shown initialization.' -ForegroundColor Green
