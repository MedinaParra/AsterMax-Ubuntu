param([string]$Root)
$ErrorActionPreference='Stop'
function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){throw "C10.20 anchor missing: $Old"}
    return $Text.Replace($Old,$New)
}

$source=Join-Path $PSScriptRoot 'AsterMaxWorkflowConformanceAudit.cs'
$destination=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
Copy-Item $source $destination -Force

$project=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$p=Get-Content $project -Raw
$anchor='<Compile Include="Forms\AsterMaxNativeUi.cs" />'
$p=Replace-Required $p $anchor ('<Compile Include="Forms\AsterMaxWorkflowConformanceAudit.cs" />'+[Environment]::NewLine+'    '+$anchor)
Set-Content $project $p -Encoding UTF8

$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $ui -Raw
$anchor='                StartAsterMaxIntegratedAudit();'
$u=Replace-Required $u $anchor ($anchor+[Environment]::NewLine+'                StartAsterMaxC1020WorkflowConformanceAudit();')
Set-Content $ui $u -Encoding UTF8

Write-Host 'C10.20 native Windows workflow-conformance audit hook applied.'
