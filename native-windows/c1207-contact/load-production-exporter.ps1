param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string[]]$AdditionalSources=@()
)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -lt 7) { throw 'C12.07 source harness requires PowerShell 7 (the CI shell); native application validation uses the built EXE separately.' }
if(('PrePoMax.AsterMaxCodeAsterNativeExporter' -as [type])) { throw 'Run the production-exporter source harness in a fresh PowerShell process.' }
$exporter=Get-Content -LiteralPath (Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs') -Raw
$helper=Join-Path $Root 'PrePoMax/AsterMaxContactTopology.cs'
if(-not (Test-Path -LiteralPath $helper)) { throw 'Apply C12.07 contact-topology patch before loading the production exporter.' }

# Only the FeModel entry overload depends on the desktop assemblies. Compile the
# complete production JSON ExportContract and every helper unchanged; no solver
# stand-in, substituted exporter, or generated result is involved in these tests.
$start=$exporter.IndexOf('        public static JObject Export(FeModel model, string outDir, string baseName)')
$end=$exporter.IndexOf('        public static JObject ExportContract(JObject contract,string outDir,string baseName)')
if($start -lt 0 -or $end -le $start) { throw 'Production exporter entry-method boundaries changed; source harness must be reviewed.' }
$exporter=$exporter.Remove($start,$end-$start)
$exporter=$exporter.Replace('using CaeModel;','')
$scratch=Join-Path ([IO.Path]::GetTempPath()) ('AsterMax-C1207-production-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch | Out-Null
try {
    $sourcePath=Join-Path $scratch 'AsterMaxCodeAsterNativeExporter.cs'
    [IO.File]::WriteAllText($sourcePath,$exporter,(New-Object Text.UTF8Encoding($false)))
    $jsonAssembly=[Newtonsoft.Json.Linq.JObject].Assembly.Location
    $references=@($jsonAssembly,'System.Runtime','System.Collections','System.Linq','System.Linq.Expressions','System.IO.FileSystem','System.ComponentModel.TypeConverter','System.ObjectModel','System.Text.Encoding.Extensions')
    $sources=@($sourcePath,$helper)
    # C12.08 adds a production helper without changing the C12.07 contact path.
    # Compile it when present so historical gates still exercise the current
    # exporter instead of a stale copy; older source trees remain supported.
    $bondedHelper=Join-Path $Root 'PrePoMax/AsterMaxBondedMpc.cs'
    if(Test-Path -LiteralPath $bondedHelper) { $sources += $bondedHelper }
    $forceHelper=Join-Path $Root 'PrePoMax/AsterMaxForceDistribution.cs'
    if(Test-Path -LiteralPath $forceHelper) { $sources += $forceHelper }
    $sources += $AdditionalSources
    # The desktop project targets .NET Framework (default language C# 7.3).
    # PowerShell's newer compiler defaults otherwise hide desktop scope errors.
    Add-Type -Path $sources -ReferencedAssemblies $references -CompilerOptions @('/nowarn:1701,1702','/langversion:7.3')
}
finally {
    Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
}
