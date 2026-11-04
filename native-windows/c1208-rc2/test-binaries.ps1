param([Parameter(Mandatory=$true)][string]$Dist,[Parameter(Mandatory=$true)][string]$OutDir)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ne 5 -or -not [Environment]::Is64BitProcess) { throw 'Requires Windows PowerShell 5.1 x64.' }
$Dist = [IO.Path]::GetFullPath($Dist)
$OutDir = [IO.Path]::GetFullPath($OutDir)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$vswhere="${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$csc = & $vswhere -latest -products * -requires Microsoft.Component.MSBuild -find 'MSBuild\**\Bin\Roslyn\csc.exe' | Select-Object -First 1
if (-not $csc) { throw 'Native Roslyn compiler not found.' }
$refs = @('/r:'+(Join-Path $Dist 'AsterMax Mechanical.exe'))
foreach ($name in @('CaeGlobals','CaeMesh','CaeModel','CaeResults','Newtonsoft.Json')) { $refs += '/r:'+(Join-Path $Dist "lib/$name.dll") }
$tests = Join-Path $PSScriptRoot 'tests'
$harness = Join-Path $OutDir 'test-bin'
Copy-Item -LiteralPath $Dist -Destination $harness -Recurse
$env:PATH = (Join-Path $harness 'lib') + ';' + $env:PATH
foreach ($name in @('BinaryGate','StrictFixtureTests','ResourceAudit')) {
    $sources = @((Join-Path $tests "$name.cs"))
    if ($name -eq 'BinaryGate') { foreach ($extra in @('ContactLawTests','ContactTopologyTests','BondedMpcTests')) { $sources += Join-Path $tests "$extra.cs" } }
    $exe = Join-Path $harness "$name.exe"
    & $csc /nologo /platform:x64 "/out:$exe" @refs @sources
    if ($LASTEXITCODE -ne 0) { throw "Test compile failed: $name" }
    [IO.File]::WriteAllText(($exe+'.config'),'<configuration><runtime><assemblyBinding xmlns="urn:schemas-microsoft-com:asm.v1"><probing privatePath="lib" /></assemblyBinding></runtime></configuration>')
    $target = Join-Path $OutDir $name
    if ($name -eq 'ResourceAudit') { $target = Join-Path $Dist 'AsterMax Mechanical.exe' } else { New-Item -ItemType Directory -Force -Path $target | Out-Null }
    & $exe $target 2>&1 | Tee-Object (Join-Path $OutDir "$name.log")
    if ($LASTEXITCODE -ne 0) { throw "Compiled binary test failed: $name" }
}
Write-Host 'Actual Windows binaries passed export/fixture/resource gates. Real Code_Aster and interactive GUI were not run.'
