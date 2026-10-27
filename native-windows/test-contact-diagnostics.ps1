param([Parameter(Mandatory=$true)][string]$Root, [Parameter(Mandatory=$true)][string]$OutDir)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'c1207-contact/load-production-exporter.ps1') -Root $Root -AdditionalSources @((Join-Path $PSScriptRoot 'c1207-contact/ContactDiagnosticTests.cs'))
$audit=[ContactDiagnosticTests]::Run([IO.Path]::GetFullPath($OutDir))
[IO.File]::WriteAllText((Join-Path $OutDir 'contact-diagnostics.json'),$audit.ToString())
Write-Host $audit.ToString()
