param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference='Stop'
$harness=Join-Path $PSScriptRoot 'c1207-contact/load-production-exporter.ps1'
$tests=Join-Path $PSScriptRoot 'c1207-contact/ContactTopologyTests.cs'
. $harness -Root $Root -AdditionalSources @($tests)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$audit=[AsterMaxC1207ContactTests]::Run([IO.Path]::GetFullPath($OutDir))
$bridge=Get-Content -LiteralPath (Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs') -Raw
if(-not $bridge.Contains('if (cp == null || !cp.Active) continue;') -or -not $bridge.Contains('if (!cp.Valid)')) {
    throw 'C12.07 live-model bridge must omit inactive pairs and reject active invalid pairs.'
}
$audit['live_model_bridge_guard_source_check']=[Newtonsoft.Json.Linq.JValue]::new('PASS')
[IO.File]::WriteAllText((Join-Path $OutDir 'contact-topology.json'),$audit.ToString(),(New-Object Text.UTF8Encoding($false)))
Write-Host ('C12.07 contact topology PASS: '+$audit['checks'].Count+' production C# checks and 160 exhaustive comparisons; no native solver/GUI execution claimed.')
