param([Parameter(Mandatory=$true)][string]$Dist,[Parameter(Mandatory=$true)][string]$OutDir)
$ErrorActionPreference='Stop'
if($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSVersion.Major -ne 5 -or -not [Environment]::Is64BitProcess) {
    throw 'Run this gate in Windows PowerShell 5.1 x64 against the locally rebuilt package. No user PMX is accepted.'
}
$script:PackageRoot=(Resolve-Path -LiteralPath $Dist).Path
function Find-Assembly([string]$name) {
    foreach($rel in @($name,"lib/$name","libs/$name")) {
        $p=Join-Path $script:PackageRoot $rel
        if(Test-Path -LiteralPath $p -PathType Leaf) { return [IO.Path]::GetFullPath($p) }
    }
    return $null
}
$resolver=[ResolveEventHandler] {
    param($sender,$eventArgs)
    $p=Find-Assembly ((New-Object Reflection.AssemblyName($eventArgs.Name)).Name+'.dll')
    if($p) { return [Reflection.Assembly]::LoadFrom($p) };return $null
}
[AppDomain]::CurrentDomain.add_AssemblyResolve($resolver)
try {
    if(Test-Path -LiteralPath $OutDir) { throw 'Use a new evidence directory.' }
    New-Item -ItemType Directory -Path $OutDir | Out-Null
    $references=@('System.dll','System.Core.dll','System.Drawing.dll')
    foreach($name in @('CaeGlobals.dll','CaeMesh.dll','CaeModel.dll','CaeResults.dll','Newtonsoft.Json.dll')) {
        $p=Find-Assembly $name;if(-not $p) { throw "Missing assembly: $name" }
        [Reflection.Assembly]::LoadFrom($p)|Out-Null;$references+=$p
    }
    $app=[Reflection.Assembly]::LoadFrom((Join-Path $script:PackageRoot 'AsterMax Mechanical.exe'))
    Add-Type -Path (Join-Path $PSScriptRoot 'c1208-bonded/ForceNativeTests.cs') -ReferencedAssemblies $references
    $report=[ForceNativeTests]::Run($app,[IO.Path]::GetFullPath($OutDir))
    [IO.File]::WriteAllText((Join-Path $OutDir 'force-native.json'),$report.ToString())
    Write-Host $report.ToString()
}
catch {
    Write-Host $_.Exception.ToString()
    throw
}
finally { [AppDomain]::CurrentDomain.remove_AssemblyResolve($resolver) }
