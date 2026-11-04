param([Parameter(Mandatory=$true)][string]$Source, [Parameter(Mandatory=$true)][string]$Audit)
$ErrorActionPreference = 'Stop'
$Source = [IO.Path]::GetFullPath($Source)
$Audit = [IO.Path]::GetFullPath($Audit)
New-Item -ItemType Directory -Force -Path $Audit | Out-Null
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$msbuild = & $vswhere -latest -products * -requires Microsoft.Component.MSBuild -find 'MSBuild\**\Bin\MSBuild.exe' | Select-Object -First 1
if (-not $msbuild) { throw 'Native Windows MSBuild not found.' }
$nuget = Join-Path $Audit 'nuget.exe'
Invoke-WebRequest 'https://dist.nuget.org/win-x86-commandline/v6.14.0/nuget.exe' -OutFile $nuget
& $nuget restore (Join-Path $Source 'PrePoMax.sln') -PackagesDirectory (Join-Path $Source 'packages') -NonInteractive 2>&1 | Tee-Object (Join-Path $Audit 'nuget-restore.log')
if ($LASTEXITCODE -ne 0) { throw "NuGet restore failed: $LASTEXITCODE" }
& $msbuild (Join-Path $Source 'PrePoMax.sln') /t:Rebuild /m /p:Configuration=Release /p:Platform=x64 /p:CodePage=65001 /p:LangVersion=7.3 /p:PostBuildEvent= "/bl:$Audit/build.binlog" /verbosity:normal 2>&1 | Tee-Object (Join-Path $Audit 'build.log')
if ($LASTEXITCODE -ne 0) { throw "MSBuild failed: $LASTEXITCODE" }
$bin = Join-Path $Source 'PrePoMax/bin/x64/Release'
$products = @('AsterMax Mechanical.exe','lib/CaeGlobals.dll','lib/CaeJob.dll','lib/CaeMesh.dll','lib/CaeModel.dll','lib/CaeResults.dll','lib/UserControls.dll','lib/vtkControl.dll','lib/QuantumConcepts.Formats.StereoLithography.dll')
$manifest = foreach ($name in $products) {
    $path = Join-Path $bin $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing rebuilt product: $name" }
    @{path=$name;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant();bytes=(Get-Item -LiteralPath $path).Length}
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $Audit 'product-manifest.json')
"ASTERMAX_BUILD_DIR=$bin" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
"ASTERMAX_MSBUILD=$msbuild" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
Write-Host 'All nine application projects rebuilt natively for Windows x64.'
