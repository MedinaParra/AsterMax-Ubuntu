param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $p)){throw "Missing Controller.cs: $p"}
$c=Get-Content $p -Raw
$required=@(
 'RedirectStandardOutput = true',
 'RedirectStandardError = true',
 'ReadToEndAsync()',
 'failureKind = "TIMEOUT"',
 'failureKind = "NON_ZERO_EXIT"',
 'failureKind = "ZERO_EXIT_MISSING_OUTPUT"',
 'failureKind = "PROCESS_START_OR_RUNTIME_EXCEPTION"',
 'Audit", "NetGenFailures',
 'stdout.txt',
 'stderr.txt',
 'diagnostic.txt',
 'elapsedMilliseconds=',
 'brepBytes=',
 'visBytes='
)
foreach($needle in $required){if(!$c.Contains($needle)){throw "C10.56 static diagnostic contract missing: $needle"}}
if(($c.Split('private AsterMaxPreparedBrepVisualization AsterMaxPrepareBrepVisualization').Count-1) -ne 1){throw 'C10.56 expected exactly one preparation method.'}
Write-Host 'PASS C10.56 static NetGen diagnostic contract.' -ForegroundColor Green
