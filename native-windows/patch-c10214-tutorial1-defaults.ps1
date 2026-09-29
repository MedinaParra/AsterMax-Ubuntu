param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New,[string]$Label) {
    if(-not $Text.Contains($Old)){ throw "C10.23 anchor missing ($Label): $Old" }
    return $Text.Replace($Old,$New)
}

# C10.23 — product defaults distilled from WS01.1.
# No tutorial-specific faces, material, pressure, or reference values are embedded.

# 1) New meshing parameter objects default to quadratic structural solids.
$meshParams=Join-Path $Root 'CaeMesh/Parts/MeshingParameters.cs'
if(!(Test-Path $meshParams)){ throw 'C10.23 MeshingParameters.cs missing.' }
$m=Get-Content $meshParams -Raw
if(-not $m.Contains('ASTERMAX_TUTORIAL1_DEFAULTS'))
{
    $marker=@'
            // Defaults
            // ASTERMAX_TUTORIAL1_DEFAULTS:
            // Structural solids start quadratic. Midside nodes stay off the CAD
            // geometry by default to reduce high-order inversion risk on dirty CAD.
            // Explicit user edits after creation remain authoritative.
'@
    $m=Replace-Required $m '            // Defaults' $marker.TrimEnd() 'meshing-default-marker'
}
$m=[regex]::Replace($m,'(?m)^\s*_secondOrder\s*=\s*(true|false)\s*;\s*$','            _secondOrder = true;',1)
$m=[regex]::Replace($m,'(?m)^\s*_midsideNodesOnGeometry\s*=\s*(true|false)\s*;\s*$','            _midsideNodesOnGeometry = false;',1)
$m=[regex]::Replace($m,'(?m)^\s*_optimizeSteps3D\s*=\s*\d+\s*;\s*$','            _optimizeSteps3D = 3;',1)
if(-not $m.Contains('_secondOrder = true;')){ throw 'C10.23 quadratic default not applied.' }
if(-not $m.Contains('_midsideNodesOnGeometry = false;')){ throw 'C10.23 midside default not applied.' }
Set-Content $meshParams $m -Encoding UTF8

# 2) Pre-solve readiness records the actual emitted element order.
$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
if(!(Test-Path $workspace)){ throw 'C10.23 results workspace missing.' }
$w=Get-Content $workspace -Raw
if(-not $w.Contains('public int LinearStructuralSolidElementCount'))
{
    $anchor='        public int UnsupportedElementCount { get; private set; }'
    $insert=@'
        public int UnsupportedElementCount { get; private set; }
        public int LinearStructuralSolidElementCount { get; private set; }
        public int QuadraticStructuralSolidElementCount { get; private set; }
'@
    $w=Replace-Required $w $anchor $insert.TrimEnd() 'readiness-properties'
}
if(-not $w.Contains('WARN:linear_structural_solid_elements='))
{
    $pattern='int expectedNodeCount = 0;\s*if \(e is CaeMesh\.LinearHexaElement\) expectedNodeCount = 8;\s*else if \(e is CaeMesh\.LinearTetraElement\) expectedNodeCount = 4;\s*else if \(e is CaeMesh\.ParabolicTetraElement\) expectedNodeCount = 10;'
    $replacement=@'
int expectedNodeCount = 0;
                    if (e is CaeMesh.LinearHexaElement)
                    {
                        expectedNodeCount = 8;
                        r.LinearStructuralSolidElementCount++;
                    }
                    else if (e is CaeMesh.LinearTetraElement)
                    {
                        expectedNodeCount = 4;
                        r.LinearStructuralSolidElementCount++;
                    }
                    else if (e is CaeMesh.ParabolicTetraElement)
                    {
                        expectedNodeCount = 10;
                        r.QuadraticStructuralSolidElementCount++;
                    }
'@
    $newW=[regex]::Replace($w,$pattern,$replacement.Trim(),1)
    if($newW -eq $w){ throw 'C10.23 readiness element-family anchor missing.' }
    $w=$newW

    $warnAnchor='            r.MaterialCount = model.Materials == null ? 0 : model.Materials.Count;'
    $warnInsert=@'
            if (r.LinearStructuralSolidElementCount > 0)
                r.Issues.Add("WARN:linear_structural_solid_elements=" +
                    r.LinearStructuralSolidElementCount.ToString(CultureInfo.InvariantCulture) +
                    "; quadratic solids are the AsterMax default for stress/bending fidelity");
            if (r.QuadraticStructuralSolidElementCount == 0 && r.ElementCount > 0)
                r.Issues.Add("WARN:no_quadratic_structural_solid_elements");

            r.MaterialCount = model.Materials == null ? 0 : model.Materials.Count;
'@
    $w=Replace-Required $w $warnAnchor $warnInsert.TrimEnd() 'readiness-warning'
}
Set-Content $workspace $w -Encoding UTF8

# 3) Preserve non-blocking readiness warnings in every solve transaction.
$solve=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $solve)){ throw 'C10.23 native solve transaction missing.' }
$s=Get-Content $solve -Raw
if(-not $s.Contains('using System.Linq;'))
{
    $s=Replace-Required $s 'using System.IO;' ('using System.IO;'+[Environment]::NewLine+'using System.Linq;') 'solve-linq'
}
if(-not $s.Contains('string[] readinessWarnings'))
{
    $pattern='var readiness=AsterMaxPreSolveReadiness\.Evaluate\(model\);\s*if\(readiness\.Status!="READY"\)\s*throw new InvalidOperationException\("Solve blocked by engineering readiness gate: "\+readiness\.AuditSummary\(\)\+"\s*\|\s*"\+String\.Join\(";\s*",readiness\.Issues\)\);'
    $replacement=@'
var readiness=AsterMaxPreSolveReadiness.Evaluate(model);
            if(readiness.Status!="READY")
                throw new InvalidOperationException("Solve blocked by engineering readiness gate: "+readiness.AuditSummary()+" | "+String.Join("; ",readiness.Issues));
            string[] readinessWarnings=readiness.Issues
                .Where(x=>x.StartsWith("WARN:",StringComparison.Ordinal))
                .ToArray();
'@
    $newS=[regex]::Replace($s,$pattern,$replacement.Trim(),1)
    if($newS -eq $s){ throw 'C10.23 solve readiness anchor missing.' }
    $s=$newS

    $manifestAnchor='                ["native_exporter_manifest"]=exportManifest'
    $manifestInsert=@'
                ["native_exporter_manifest"]=exportManifest,
                ["readiness_warnings"]=new JArray(readinessWarnings),
                ["tutorial1_default_policy"]="quadratic structural solids + topology-stable scopes + reaction/equilibrium + component-first von Mises"
'@
    $s=Replace-Required $s $manifestAnchor $manifestInsert.TrimEnd() 'solve-manifest'

    $messageAnchor='            tx.Message="Code_Aster transaction prepared and fingerprint frozen.";'
    $messageInsert=@'
            tx.Message=readinessWarnings.Length==0
                ?"Code_Aster transaction prepared and fingerprint frozen."
                :"Code_Aster transaction prepared with engineering warnings: "+String.Join("; ",readinessWarnings);
'@
    $s=Replace-Required $s $messageAnchor $messageInsert.TrimEnd() 'solve-message'
}
Set-Content $solve $s -Encoding UTF8

# 4) Every exported Code_Aster deck carries the engineering-default contract.
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $exporter)){ throw 'C10.23 native exporter missing.' }
$e=Get-Content $exporter -Raw
if(-not $e.Contains('tutorial1_default_policy'))
{
    $manifestAnchor='                ["element_type"]=elementType,'
    $manifestInsert=@'
                ["element_type"]=elementType,
                ["tutorial1_default_policy"]=new JObject
                {
                    ["preferred_structural_order"]=2,
                    ["preferred_volume_family"]="TETRA10",
                    ["midside_nodes_on_geometry_default"]=false,
                    ["component_first_von_mises"]=true,
                    ["reaction_resultant_required_for_qualification"]=true,
                    ["scope_membership_frozen_in_model_fingerprint"]=true
                },
'@
    $e=Replace-Required $e $manifestAnchor $manifestInsert.TrimEnd() 'exporter-policy'
}
if(-not $e.Contains("FORCE=('REAC_NODA',)")){ throw 'C10.23 requires REAC_NODA support.' }
if(-not $e.Contains('["expected_external_resultant_n"]')){ throw 'C10.23 requires independent load resultant support.' }
Set-Content $exporter $e -Encoding UTF8

# 5) Make the defaults visible in the Mechanical workspace.
$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(!(Test-Path $ui)){ throw 'C10.23 native UI missing.' }
$u=Get-Content $ui -Raw
if(-not $u.Contains('Quadratic solids by default'))
{
    $anchor='                CommandTile("Loads", "MODEL", () => AsterMaxC1004MaterialAction(() => tsmiCreateLoad_Click(null, EventArgs.Empty))),'
    $insert=@'
                CommandTile("Loads", "MODEL", () => AsterMaxC1004MaterialAction(() => tsmiCreateLoad_Click(null, EventArgs.Empty))),
                InfoCard("Quadratic solids by default • scope fingerprint • reaction equilibrium • component-first von Mises"),
'@
    $u=Replace-Required $u $anchor $insert.TrimEnd() 'ui-policy'
}
Set-Content $ui $u -Encoding UTF8

Write-Host 'C10.23 Tutorial-1 engineering defaults applied.' -ForegroundColor Green
