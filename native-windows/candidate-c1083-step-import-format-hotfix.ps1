param([string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.83 missing: $controllerPath"}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$signature='        private Dictionary<string, AsterMaxPreparedBrepVisualization> AsterMaxPrepareLeafBrepVisualizations(string[] filesToImport)'
$start=$c.IndexOf($signature)
if($start -lt 0){throw 'C10.83 C10.45 prepared visualization method missing.'}
$guard='            if (!String.Equals(Environment.GetEnvironmentVariable("ASTERMAX_EXPERIMENTAL_PARALLEL_VIS_IMPORT"), "1", StringComparison.Ordinal)) return prepared;'
if(-not $c.Contains('ASTERMAX_EXPERIMENTAL_PARALLEL_VIS_IMPORT')){
    $anchor='            if (filesToImport == null || filesToImport.Length == 0) return prepared;'
    $pos=$c.IndexOf($anchor,$start)
    if($pos -lt 0){throw 'C10.83 prepared visualization guard anchor missing.'}
    $c=$c.Insert($pos+$anchor.Length,"`n"+$guard+"`n            // C10.83: prepared parallel VIS import is experimental. The real STEP test exposed`n            // format/parser failures in AsterMaxImportPreparedBrep; default to the proven serial`n            // ImportBrepPartFile path until the VIS producer/consumer contract is characterized.")
}
Set-Content $controllerPath $c -Encoding UTF8
Write-Host 'C10.83: safe STEP import fallback applied; experimental parallel VIS import disabled by default.' -ForegroundColor Green
