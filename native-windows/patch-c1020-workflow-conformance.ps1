param([string]$Root)
$ErrorActionPreference='Stop'
function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){throw "C10.20 anchor missing: $Old"}
    return $Text.Replace($Old,$New)
}

$source=Join-Path $PSScriptRoot 'AsterMaxWorkflowConformanceAudit.cs'
$destination=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
Copy-Item $source $destination -Force
$crossSource=Join-Path $PSScriptRoot 'AsterMaxWorkflowConformanceCrossChecks.cs'
$crossDestination=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceCrossChecks.cs'
Copy-Item $crossSource $crossDestination -Force

# Keep the nine mandatory stages and the cross-cutting checks separate in source and evidence.
$a=Get-Content $destination -Raw
$old='                    ExecuteAsterMaxC1020WorkflowConformanceAudit(directory);'+[Environment]::NewLine+'                    Environment.Exit(0);'
$new='                    ExecuteAsterMaxC1020WorkflowConformanceAudit(directory);'+[Environment]::NewLine+'                    C1020AttachCrossCuttingToSession(directory);'+[Environment]::NewLine+'                    Environment.Exit(0);'
$a=Replace-Required $a $old $new

# Header nodes in the projected Outline are audit/navigation surfaces. Selecting them invokes
# the production AfterSelect routing and can re-enter the hidden source tree. C10.20 only needs
# those headers observable for evidence; functional selection is retained for real result fields.
$signature='        private void C1020SelectOutlineNode(string name)'
$helper=@'
        private void C1020RevealOutlineNode(string name)
        {
            _modelTree.RefreshAsterMaxOutline();
            TreeView tree = C1020FindControl<TreeView>(this, x => x.Name == "asterMaxOutline");
            TreeNode node = C1020FindOutlineNode(name);
            if (tree == null || node == null)
                throw new InvalidOperationException("AsterMax Outline node missing: " + name);
            for (TreeNode parent = node.Parent; parent != null; parent = parent.Parent) parent.Expand();
            node.EnsureVisible();
            Application.DoEvents();
        }

'@
$a=Replace-Required $a $signature ($helper+$signature)
foreach($name in @('ax-model','ax-coordinates','ax-connections','ax-mesh','ax-selections','ax-analysis','ax-solution')) {
    $a=$a.Replace('            C1020SelectOutlineNode("'+$name+'");','            C1020RevealOutlineNode("'+$name+'");')
}

# Persist the rows already exercised after every stage. If a later unmanaged WinForms callback
# terminates the process, completed stages remain auditable instead of being reconstructed as
# NOT_EXERCISED solely because the final session write was never reached.
$stageThrow='            if (status == "FAIL") throw new InvalidOperationException("C10.20 stage failed: " + id + ". " + expected);'
$checkpoint=@'
            File.WriteAllText(Path.Combine(directory, "workflow-conformance-session.json"),
                new JObject {
                    ["release"] = "C10.20",
                    ["pass"] = false,
                    ["partial"] = true,
                    ["historical_pending_closed"] = false,
                    ["reference_fixture"] = "B01_PARAMETRIC_STEP_100x10x10_mm",
                    ["fea_values_invented"] = false,
                    ["rows"] = rows
                }.ToString(Formatting.Indented));
'@
$a=Replace-Required $a $stageThrow ($checkpoint+$stageThrow)
Set-Content $destination $a -Encoding UTF8

$project=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$p=Get-Content $project -Raw
$anchor='<Compile Include="Forms\AsterMaxNativeUi.cs" />'
$p=Replace-Required $p $anchor ('<Compile Include="Forms\AsterMaxWorkflowConformanceAudit.cs" />'+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxWorkflowConformanceCrossChecks.cs" />'+[Environment]::NewLine+'    '+$anchor)
Set-Content $project $p -Encoding UTF8

$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $ui -Raw
$anchor='                StartAsterMaxIntegratedAudit();'
$u=Replace-Required $u $anchor ($anchor+[Environment]::NewLine+'                StartAsterMaxC1020WorkflowConformanceAudit();')
Set-Content $ui $u -Encoding UTF8

Write-Host 'C10.20 native Windows workflow-conformance audit + cross-cutting checks applied.'
