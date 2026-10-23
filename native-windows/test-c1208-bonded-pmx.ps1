param(
    [Parameter(Mandatory=$true)][string]$Dist,
    [Parameter(Mandatory=$true)][string]$OutDir,
    [switch]$NativeChild
)
$ErrorActionPreference='Stop'
if($env:OS -ne 'Windows_NT') { throw 'Synthetic PMX native compatibility requires Windows and the packaged .NET Framework application.' }
if(-not $NativeChild) {
    # The application targets .NET Framework. Use its native runtime and
    # BinaryFormatter implementation, not PowerShell 7's different .NET runtime.
    $windowsPowerShell=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
    if(-not (Test-Path -LiteralPath $windowsPowerShell -PathType Leaf)) { throw 'Windows PowerShell 5.1 is missing.' }
    $env:ASTERMAX_C1208_TEST_PYTHON=(Get-Command python -ErrorAction Stop).Source
    # A PowerShell 7 module path makes 5.1 discover incompatible modules. Give
    # only the child a clean default path, restoring the parent's environment.
    $previousModulePath=$env:PSModulePath
    try {
        Remove-Item Env:PSModulePath -ErrorAction SilentlyContinue
        & $windowsPowerShell -NoLogo -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -Dist $Dist -OutDir $OutDir -NativeChild
        $childExit=$LASTEXITCODE
    }
    finally { $env:PSModulePath=$previousModulePath }
    if($childExit -ne 0) { throw "Synthetic PMX native child failed with exit code $childExit." }
    return
}
if($PSVersionTable.PSVersion.Major -ne 5 -or -not [Environment]::Is64BitProcess) { throw 'Synthetic PMX native child requires Windows PowerShell 5.1 x64.' }
$script:PackageRoot=(Resolve-Path -LiteralPath $Dist).Path
if(Test-Path -LiteralPath $OutDir) {
    if(@(Get-ChildItem -LiteralPath $OutDir -Force).Count -gt 0) { throw 'Synthetic PMX validation requires a fresh output directory.' }
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir=(Resolve-Path -LiteralPath $OutDir).Path
$python=$env:ASTERMAX_C1208_TEST_PYTHON
if([string]::IsNullOrWhiteSpace($python) -or -not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Host test Python path is missing.' }
$writer=Join-Path $PSScriptRoot 'tools/repair_bonded_nrbf.py'
$append=Join-Path $PSScriptRoot 'tools/nrbf_append.py'
$source=Join-Path $PSScriptRoot 'c1208-bonded/BondedPmxRoundTrip.cs'
foreach($file in @($writer,$append,$source)) { if(-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Synthetic PMX gate file missing: $file" } }

function Find-PackagedAssembly([string]$FileName) {
    foreach($relative in @($FileName,"lib/$FileName","libs/$FileName")) {
        $candidate=Join-Path $script:PackageRoot $relative
        if(Test-Path -LiteralPath $candidate -PathType Leaf) { return [IO.Path]::GetFullPath($candidate) }
    }
    return $null
}
$resolver=[ResolveEventHandler] {
    param($sender,$eventArgs)
    $file=(New-Object Reflection.AssemblyName($eventArgs.Name)).Name+'.dll'
    $path=Find-PackagedAssembly $file
    if($path) { return [Reflection.Assembly]::LoadFrom($path) }
    return $null
}
[AppDomain]::CurrentDomain.add_AssemblyResolve($resolver)
try {
    $exe=Join-Path $script:PackageRoot 'AsterMax Mechanical.exe'
    if(-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Packaged AsterMax executable missing.' }
    $references=@('System.dll','System.Core.dll','System.Drawing.dll')
    foreach($name in @('CaeGlobals.dll','CaeMesh.dll','CaeModel.dll','CaeResults.dll','Newtonsoft.Json.dll')) {
        $path=Find-PackagedAssembly $name
        if(-not $path) { throw "Packaged assembly missing: $name" }
        [Reflection.Assembly]::LoadFrom($path) | Out-Null
        $references+=$path
    }
    $application=[Reflection.Assembly]::LoadFrom($exe)
    Add-Type -Path $source -ReferencedAssemblies $references
    [AsterMaxC1208PmxRoundTrip]::Create($OutDir)
    & $python $writer --input (Join-Path $OutDir 'seed.nrbf') --output (Join-Path $OutDir 'repaired.nrbf') --selection (Join-Path $OutDir 'selection.json') --coordinates (Join-Path $OutDir 'coordinates.json') --report (Join-Path $OutDir 'rewrite.json')
    if($LASTEXITCODE -ne 0) { throw "Data-only synthetic NRBF rewrite failed with exit code $LASTEXITCODE." }
    $report=[AsterMaxC1208PmxRoundTrip]::Complete($OutDir,$application)
    $report['executable_sha256']=[Newtonsoft.Json.Linq.JValue]::new((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant())
    $report['data_only_writer_sha256']=[Newtonsoft.Json.Linq.JValue]::new((Get-FileHash -LiteralPath $writer -Algorithm SHA256).Hash.ToLowerInvariant())
    $report['data_only_append_sha256']=[Newtonsoft.Json.Linq.JValue]::new((Get-FileHash -LiteralPath $append -Algorithm SHA256).Hash.ToLowerInvariant())
    [IO.File]::WriteAllText((Join-Path $OutDir 'C12.08_SYNTHETIC_PMX_VALIDATION.json'),$report.ToString(),(New-Object Text.UTF8Encoding($false)))
    Write-Host ('C12.08 synthetic PMX native roundtrip PASS: '+$report['checks'].Count+' checks including live Tie export and 7 fingerprint mutations. No user geometry or solver result included.')
}
finally { [AppDomain]::CurrentDomain.remove_AssemblyResolve($resolver) }
