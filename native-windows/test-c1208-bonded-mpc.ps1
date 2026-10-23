param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference='Stop'
$harness=Join-Path $PSScriptRoot 'c1207-contact/load-production-exporter.ps1'
$tests=Join-Path $PSScriptRoot 'c1208-bonded/BondedMpcTests.cs'
. $harness -Root $Root -AdditionalSources @($tests)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$audit=[AsterMaxC1208BondedTests]::Run([IO.Path]::GetFullPath($OutDir))
$bridge=Get-Content -LiteralPath (Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs') -Raw
foreach($required in @('x.Active && !(x is Tie)','if (!tie.Valid)','tie.PositionTolerance','if (tie.Adjust)','root["bonded_ties"] = bondedTies;')) {
    if(-not $bridge.Contains($required)) { throw "C12.08 production Tie bridge guard missing: $required" }
}
$audit['live_model_bridge_guard_source_check']=[Newtonsoft.Json.Linq.JValue]::new('PASS')
[IO.File]::WriteAllText((Join-Path $OutDir 'bonded-mpc-tests.json'),$audit.ToString(),(New-Object Text.UTF8Encoding($false)))
Write-Host ('C12.08 bonded MPC PASS: '+$audit['checks'].Count+' production C# checks; native solver validation is a separate gate.')
