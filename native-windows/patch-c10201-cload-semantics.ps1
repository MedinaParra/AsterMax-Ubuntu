param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){ throw "C10.20.1 anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

# Preserve native PrePoMax CLoad semantics: F1/F2/F3 are force components PER NODE.
# Earlier AsterMax code relabeled them as totals and divided by node count again.
$bridgePath=Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
$b=(Get-Content $bridgePath -Raw).Replace("`r`n","`n")
$b=Replace-Required $b 'public const string NativeBridgeVersion = "C9.60-native-bridge-v0";' 'public const string NativeBridgeVersion = "C10.20.1-native-bridge-cload-per-node";'
$b=Replace-Required $b '["type"] = "nodal_force_total",' '["type"] = "nodal_force_per_node",'
$b=Replace-Required $b '["fx_total_n"] = cload.F1,' '["fx_per_node_n"] = cload.F1,'
$b=Replace-Required $b '["fy_total_n"] = cload.F2,' '["fy_per_node_n"] = cload.F2,'
$b=Replace-Required $b '["fz_total_n"] = cload.F3' '["fz_per_node_n"] = cload.F3'
Set-Content $bridgePath $b -Encoding UTF8

$exporterPath=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
$e=(Get-Content $exporterPath -Raw).Replace("`r`n","`n")
$versionLine=[regex]::Match($e,'public const string Version = "[^"]+";').Value
if([string]::IsNullOrWhiteSpace($versionLine)){ throw 'C10.20.1 exporter version anchor missing.' }
$e=$e.Replace($versionLine,'public const string Version = "C10.20.1-native-codeaster-cload-semantics";')

$old=@'
            double fx=GetDouble(load,"fx_total_n")/loadNodes.Count;
            double fy=GetDouble(load,"fy_total_n")/loadNodes.Count;
            double fz=GetDouble(load,"fz_total_n")/loadNodes.Count;
'@
$new=@'
            bool perNodeLoad = load["fx_per_node_n"] != null || load["fy_per_node_n"] != null || load["fz_per_node_n"] != null;
            bool legacyTotalLoad = !perNodeLoad && (load["fx_total_n"] != null || load["fy_total_n"] != null || load["fz_total_n"] != null);
            if(!perNodeLoad && !legacyTotalLoad)
                throw new InvalidDataException("Nodal load has no recognized force semantics.");
            double fx=perNodeLoad ? GetDouble(load,"fx_per_node_n") : GetDouble(load,"fx_total_n")/loadNodes.Count;
            double fy=perNodeLoad ? GetDouble(load,"fy_per_node_n") : GetDouble(load,"fy_total_n")/loadNodes.Count;
            double fz=perNodeLoad ? GetDouble(load,"fz_per_node_n") : GetDouble(load,"fz_total_n")/loadNodes.Count;
            string loadSemantics=perNodeLoad ? "PER_NODE_CLOAD" : "LEGACY_TOTAL_DISTRIBUTED";
            double fxTotal=fx*loadNodes.Count;
            double fyTotal=fy*loadNodes.Count;
            double fzTotal=fz*loadNodes.Count;
'@
$old=$old.Replace("`r`n","`n"); $new=$new.Replace("`r`n","`n")
$e=Replace-Required $e $old $new

$oldManifest=@'
                ["load_nodes"]=loadNodes.Count,
                ["fx_per_node_n"]=fx,
                ["fy_per_node_n"]=fy,
                ["fz_per_node_n"]=fz,
'@
$newManifest=@'
                ["load_nodes"]=loadNodes.Count,
                ["load_semantics"]=loadSemantics,
                ["fx_per_node_n"]=fx,
                ["fy_per_node_n"]=fy,
                ["fz_per_node_n"]=fz,
                ["fx_total_n"]=fxTotal,
                ["fy_total_n"]=fyTotal,
                ["fz_total_n"]=fzTotal,
'@
$oldManifest=$oldManifest.Replace("`r`n","`n"); $newManifest=$newManifest.Replace("`r`n","`n")
$e=Replace-Required $e $oldManifest $newManifest
Set-Content $exporterPath $e -Encoding UTF8

# The conformance fixture declares 10 kN TOTAL across four nodes. Because CLoad is per-node,
# store 2.5 kN in each selected node after C10.20 has normalized the internal object names.
$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
$a=(Get-Content $auditPath -Raw).Replace("`r`n","`n")
$a=Replace-Required $a 'new CLoad("Axial_Force", "LOAD", RegionTypeEnum.NodeSetName, 10000, 0, 0, false, false, 0)' 'new CLoad("Axial_Force", "LOAD", RegionTypeEnum.NodeSetName, 2500, 0, 0, false, false, 0)'
$a=$a.Replace('["release"] = "C10.20"','["release"] = "C10.20.1"')
Set-Content $auditPath $a -Encoding UTF8

Write-Host 'C10.20.1 CLoad semantics hotfix applied: native per-node force preserved; legacy total contracts remain readable.' -ForegroundColor Green
