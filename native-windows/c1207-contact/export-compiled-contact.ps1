param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$Dist,
    [Parameter(Mandatory=$true)][string]$Contract,
    [Parameter(Mandatory=$true)][string]$OutDir,
    [string]$BaseName='astermax-contact'
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
if(-not [Environment]::Is64BitProcess){ throw 'The production exporter must be exercised in a 64-bit process.' }
$script:AsterMaxPackageRoot=(Resolve-Path -LiteralPath $Dist).Path
$exe=Join-Path $script:AsterMaxPackageRoot 'AsterMax Mechanical.exe'
if(-not (Test-Path -LiteralPath $exe -PathType Leaf)){ throw 'The packaged AsterMax Mechanical.exe is missing.' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir=(Resolve-Path -LiteralPath $OutDir).Path

function Find-AsterMaxAssembly([string]$FileName) {
    $packaged=Join-Path $script:AsterMaxPackageRoot $FileName
    if(Test-Path -LiteralPath $packaged -PathType Leaf){ return Get-Item -LiteralPath $packaged }
    # The gate must fail if a shipped dependency is missing. The build tree and
    # restored NuGet packages are deliberately not dependency search locations.
    return $null
}

$resolver=[System.ResolveEventHandler]{
    param($sender,$eventArgs)
    $simple=(New-Object System.Reflection.AssemblyName($eventArgs.Name)).Name + '.dll'
    $candidate=Find-AsterMaxAssembly $simple
    if($candidate){ return [System.Reflection.Assembly]::LoadFrom($candidate.FullName) }
    return $null
}
[AppDomain]::CurrentDomain.add_AssemblyResolve($resolver)
try {
    $newton=Find-AsterMaxAssembly 'Newtonsoft.Json.dll'
    if(-not $newton){ throw 'The production Newtonsoft.Json assembly was not found.' }
    [System.Reflection.Assembly]::LoadFrom($newton.FullName) | Out-Null
    $assembly=[System.Reflection.Assembly]::LoadFrom($exe)
    $json=[Newtonsoft.Json.Linq.JObject]::Parse((Get-Content -LiteralPath $Contract -Raw -Encoding UTF8))
    $originalContract=$json.ToString([Newtonsoft.Json.Formatting]::None)
    $type=$assembly.GetType('PrePoMax.AsterMaxCodeAsterNativeExporter',$true)
    $method=$type.GetMethod('ExportContract',[System.Reflection.BindingFlags]'Public,Static')
    if($null -eq $method){ throw 'The packaged application has no ExportContract method.' }
    try { $manifest=$method.Invoke($null,[object[]]@($json,[string]$OutDir,[string]$BaseName)) }
    catch { if($_.Exception.InnerException){ throw $_.Exception.InnerException } else { throw } }
    if($json.ToString([Newtonsoft.Json.Formatting]::None) -cne $originalContract){ throw 'Production export modified the original model contract.' }
    foreach($suffix in @('.mail','.comm','.native-export.json')){
        $path=Join-Path $OutDir ($BaseName+$suffix)
        if(-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0){ throw "Production exporter did not write $path" }
    }
    [ordered]@{
        export_source='COMPILED_ASTERMAX_EXECUTABLE'
        executable='AsterMax Mechanical.exe'
        executable_sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
        dependency_resolution='PACKAGE_DIRECTORY_ONLY'
        exporter_version=[string]$manifest['exporter']
        contract_sha256=(Get-FileHash -LiteralPath $Contract -Algorithm SHA256).Hash.ToLowerInvariant()
        source_contract_modified=$false
        solver_execution='NOT_RUN'
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutDir 'compiled-export-receipt.json') -Encoding UTF8
    Write-Host 'C12.07 production contact export PASS: compiled packaged executable.'
}
finally {
    [AppDomain]::CurrentDomain.remove_AssemblyResolve($resolver)
}
