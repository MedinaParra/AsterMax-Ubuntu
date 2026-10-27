param([Parameter(Mandatory=$true)][string]$Root,[Parameter(Mandatory=$true)][string]$OutDir)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'c1207-contact/load-production-exporter.ps1') -Root $Root -AdditionalSources @((Join-Path $PSScriptRoot 'c1208-bonded/ForceDistributionTests.cs'))
$audit=[ForceDistributionTests]::Run([IO.Path]::GetFullPath($OutDir))
[IO.File]::WriteAllText((Join-Path $OutDir 'force-distribution.json'),$audit.ToString())
Write-Host ('C12.08 force distribution PASS: '+$audit['checks'].Count+' checks; solver NOT_RUN.')
