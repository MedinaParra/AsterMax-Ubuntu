param([string]$Root)
$ErrorActionPreference = 'Stop'

$slnPath = Join-Path $Root 'PrePoMax.sln'
if(!(Test-Path $slnPath)){ throw 'PrePoMax.sln not found.' }
$sln = Get-Content $slnPath -Raw
$guid = '{74EA83FB-2743-49EE-85A8-5B42CBCE19B3}'
$replacements = @{
  "$guid.Debug|x64.ActiveCfg = Debug|Any CPU" = "$guid.Debug|x64.ActiveCfg = Debug|x64"
  "$guid.Debug|x64.Build.0 = Debug|Any CPU" = "$guid.Debug|x64.Build.0 = Debug|x64"
  "$guid.Release|x64.ActiveCfg = Release|Any CPU" = "$guid.Release|x64.ActiveCfg = Release|x64"
  "$guid.Release|x64.Build.0 = Release|Any CPU" = "$guid.Release|x64.Build.0 = Release|x64"
}
foreach($old in $replacements.Keys){
  if(-not $sln.Contains($old)){ throw "UserControls x64 mapping anchor missing: $old" }
  $sln = $sln.Replace($old,$replacements[$old])
}
Set-Content $slnPath $sln -Encoding UTF8

$projectPath = Join-Path $Root 'UserControls/UserControls.csproj'
$p = Get-Content $projectPath -Raw
# Ensure runtime cannot prefer 32 bit even if project metadata is interpreted differently by a future VS/MSBuild.
$p = $p.Replace('<PlatformTarget>x64</PlatformTarget>', '<PlatformTarget>x64</PlatformTarget>' + [Environment]::NewLine + '    <Prefer32Bit>false</Prefer32Bit>')
Set-Content $projectPath $p -Encoding UTF8

Write-Host 'UserControls solution mapping forced to native x64.' -ForegroundColor Green
