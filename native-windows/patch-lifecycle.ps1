param([string]$Root)
$ErrorActionPreference = 'Stop'

# Native x64 consistency is part of the lifecycle/runtime contract.
$x64Patch = Join-Path $PSScriptRoot 'patch-x64-runtime.ps1'
if(Test-Path $x64Patch){ & $x64Patch -Root $Root }
else { throw 'patch-x64-runtime.ps1 not found' }

$main = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$t = Get-Content $main -Raw

# Current polished UI already registers a post-Shown BeginInvoke hook in the constructor.
if($t.Contains('BeginInvoke(new Action(ApplyAsterMaxNativeUi))')){
    Write-Host 'AsterMax UI lifecycle already deferred after native FrmMain_Shown.' -ForegroundColor Green
    exit 0
}

# Backward-compatible migration for older patch revisions.
$old = '                ApplyAsterMaxNativeUi();'
$new = '                this.Shown += (asterSender, asterArgs) => this.BeginInvoke(new Action(ApplyAsterMaxNativeUi));'
if($t.Contains($old)){
    $t = $t.Replace($old,$new)
    Set-Content $main $t -Encoding UTF8
    Write-Host 'AsterMax UI delayed until after native FrmMain_Shown initialization.' -ForegroundColor Green
    exit 0
}

throw 'AsterMax UI lifecycle hook not found'
