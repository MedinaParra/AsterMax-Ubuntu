param([string]$Root)
$ErrorActionPreference='Stop'

$bridgePath=Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
$exporterPath=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxC1035Audit.cs'
$globalsPath=Join-Path $Root 'PrePoMax/Globals.cs'
foreach($p in @($bridgePath,$exporterPath,$auditPath,$globalsPath)){ if(!(Test-Path $p)){ throw "C10.38 missing: $p" } }

# ----------------------------------------------------------------------
# 1) Translate real PrePoMax DisplacementRotation translational DOFs into
#    the native solver contract. Solid rotational DOFs remain blocked.
# ----------------------------------------------------------------------
$b=[regex]::Replace((Get-Content $bridgePath -Raw),"\r\n?","`n")
$b=[regex]::Replace($b,
    'public const string NativeBridgeVersion = "[^"]+";',
    'public const string NativeBridgeVersion = "C10.38-native-directional-bc-v1";',1)

$legacyElse='                    else supports.Add(new JObject { ["name"] = bcEntry.Value.Name, ["type"] = bcEntry.Value.GetType().Name, ["unsupported_for_code_aster_adapter_v0"] = true });'
$directional=@'
                    else
                    {
                        DisplacementRotation displacementBc = bcEntry.Value as DisplacementRotation;
                        if(displacementBc != null)
                        {
                            if(!double.IsNaN(displacementBc.UR1) || !double.IsNaN(displacementBc.UR2) || !double.IsNaN(displacementBc.UR3))
                                throw new NotSupportedException("C10.38 solid Code_Aster bridge supports translational displacement DOFs only. Rotational DOFs are not valid for 3D continuum nodes: " + displacementBc.Name);
                            if(double.IsNaN(displacementBc.U1) && double.IsNaN(displacementBc.U2) && double.IsNaN(displacementBc.U3))
                                throw new InvalidOperationException("C10.38 directional displacement has no constrained translation: " + displacementBc.Name);
                            string group = RegionToNodeGroup(model, displacementBc.RegionName, displacementBc.RegionType, nodeGroups);
                            supports.Add(new JObject
                            {
                                ["name"] = displacementBc.Name,
                                ["type"] = "displacement",
                                ["group"] = group,
                                ["dx"] = TranslationToken(displacementBc.U1, "U1", displacementBc.Name),
                                ["dy"] = TranslationToken(displacementBc.U2, "U2", displacementBc.Name),
                                ["dz"] = TranslationToken(displacementBc.U3, "U3", displacementBc.Name)
                            });
                        }
                        else supports.Add(new JObject { ["name"] = bcEntry.Value.Name, ["type"] = bcEntry.Value.GetType().Name, ["unsupported_for_code_aster_adapter_v0"] = true });
                    }
'@
if($b.Contains($legacyElse)){ $b=$b.Replace($legacyElse,$directional.TrimEnd()) }
elseif(-not $b.Contains('C10.38 directional displacement has no constrained translation')){ throw 'C10.38 bridge BC anchor missing.' }

$helperAnchor='        private static string GetElementType(FeElement e)'
$helper=@'
        private static JToken TranslationToken(double value, string component, string bcName)
        {
            if(double.IsNaN(value)) return JValue.CreateNull();
            if(double.IsPositiveInfinity(value)) return new JValue(0.0);
            if(double.IsInfinity(value))
                throw new InvalidOperationException("C10.38 invalid displacement value " + component + " in " + bcName);
            return new JValue(value);
        }

'@
if(-not $b.Contains('private static JToken TranslationToken(')){
    if(-not $b.Contains($helperAnchor)){ throw 'C10.38 bridge helper anchor missing.' }
    $b=$b.Replace($helperAnchor,$helper+$helperAnchor)
}
Set-Content $bridgePath $b -Encoding UTF8

# ----------------------------------------------------------------------
# 2) Harden exporter semantics. A primary FixedBC must remain first; all
#    later support records are emitted component-by-component as DDL_IMPO.
# ----------------------------------------------------------------------
$e=[regex]::Replace((Get-Content $exporterPath -Raw),"\r\n?","`n")
$e=[regex]::Replace($e,'public const string Version = "[^"]+";',
    'public const string Version = "C10.38-native-directional-bc-v1";',1)

$countGuard='if(mats.Count!=1 || supports.Count<1 || loads.Count!=1) throw new NotSupportedException("C10.36 native exporter requires one material, at least one support and exactly one load.");'
$guardNew=@'
if(mats.Count!=1 || supports.Count<1 || loads.Count!=1) throw new NotSupportedException("C10.38 native exporter requires one material, at least one support and exactly one load.");
            if(!String.Equals((string)((JObject)supports[0])["type"],"fixed",StringComparison.OrdinalIgnoreCase))
                throw new NotSupportedException("C10.38 requires the primary support to be a FixedBC; directional supports may follow it.");
'@
if($e.Contains($countGuard)){ $e=$e.Replace($countGuard,$guardNew.TrimEnd()) }
elseif(-not $e.Contains('C10.38 requires the primary support to be a FixedBC')){ throw 'C10.38 exporter support guard anchor missing.' }

$manifestAnchor='                ["contact_coulomb_coefficients"]=new JArray(contacts.Cast<JObject>()'
if($e.Contains($manifestAnchor) -and -not $e.Contains('["directional_support_count"]')){
    $manifestInsert=@'
                ["support_count"]=supports.Count,
                ["directional_support_count"]=supports.Cast<JObject>().Count(x =>
                    String.Equals((string)x["type"],"displacement",StringComparison.OrdinalIgnoreCase)),
'@
    $e=$e.Replace($manifestAnchor,$manifestInsert+$manifestAnchor)
}
elseif(-not $e.Contains('["directional_support_count"]')){ throw 'C10.38 exporter manifest anchor missing.' }
Set-Content $exporterPath $e -Encoding UTF8

# ----------------------------------------------------------------------
# 3) Extend the real STEP runtime audit. Create actual FeModel node sets,
#    FixedBC, DisplacementRotation and CLoad before building the contract.
#    No synthetic support/load JSON is required after this point.
# ----------------------------------------------------------------------
$a=[regex]::Replace((Get-Content $auditPath -Raw),"\r\n?","`n")
$buildAnchor='                    JObject solverContract=AsterMaxModelContractBridge.Build(model);'
$realBc=@'
                    StaticStep liveStep=model.StepCollection.StepsList.OfType<StaticStep>().FirstOrDefault();
                    if(liveStep==null) throw new InvalidOperationException("C10.38 audit static step missing.");

                    double xmin=model.Mesh.Nodes.Values.Min(n=>n.X);
                    double xmax=model.Mesh.Nodes.Values.Max(n=>n.X);
                    double span=Math.Max(1.0,Math.Abs(xmax-xmin));
                    double faceTol=Math.Max(1e-8,span*1e-8);
                    int[] fixedIds=model.Mesh.Nodes.Values.Where(n=>Math.Abs(n.X-xmin)<=faceTol).Select(n=>n.Id).OrderBy(x=>x).ToArray();
                    int[] loadIds=model.Mesh.Nodes.Values.Where(n=>Math.Abs(n.X-xmax)<=faceTol).Select(n=>n.Id).OrderBy(x=>x).ToArray();
                    if(fixedIds.Length==0 || loadIds.Length==0) throw new InvalidOperationException("C10.38 could not form deterministic end-face node sets.");

                    if(!model.Mesh.NodeSets.ContainsKey("C1038_FIXED"))
                        model.Mesh.AddNodeSet(new FeNodeSet("C1038_FIXED",fixedIds));
                    if(!model.Mesh.NodeSets.ContainsKey("C1038_LOAD"))
                        model.Mesh.AddNodeSet(new FeNodeSet("C1038_LOAD",loadIds));

                    if(!liveStep.BoundaryConditions.ContainsKey("C1038_Fixed"))
                    {
                        if(!liveStep.AddBoundaryCondition(new FixedBC("C1038_Fixed","C1038_FIXED",RegionTypeEnum.NodeSetName,false)))
                            throw new InvalidOperationException("C10.38 FixedBC was rejected by StaticStep.");
                    }
                    if(!liveStep.BoundaryConditions.ContainsKey("C1038_Directional"))
                    {
                        DisplacementRotation directional=new DisplacementRotation("C1038_Directional","C1038_LOAD",RegionTypeEnum.NodeSetName,false,false,0);
                        directional.U2=0.0;
                        if(!liveStep.AddBoundaryCondition(directional))
                            throw new InvalidOperationException("C10.38 DisplacementRotation was rejected by StaticStep.");
                    }
                    if(!liveStep.Loads.ContainsKey("C1038_Force"))
                    {
                        double fxPerNode=-1000.0/loadIds.Length;
                        double fzPerNode=100.0/loadIds.Length;
                        CLoad liveLoad=new CLoad("C1038_Force","C1038_LOAD",RegionTypeEnum.NodeSetName,fxPerNode,0.0,fzPerNode,false,false,0);
                        if(!liveStep.AddLoad(liveLoad))
                            throw new InvalidOperationException("C10.38 CLoad was rejected by StaticStep.");
                    }

                    JObject solverContract=AsterMaxModelContractBridge.Build(model);
'@
if($a.Contains($buildAnchor) -and -not $a.Contains('C1038_Directional')){
    $a=$a.Replace($buildAnchor,$realBc.TrimEnd())
}
elseif(-not $a.Contains('C1038_Directional')){ throw 'C10.38 audit solver-contract anchor missing.' }

$reportAnchor='                    report["codeaster_coulomb_mu"]=0.20;'
$reportNew=@'
                    report["codeaster_coulomb_mu"]=0.20;
                    JArray solverSupports=(JArray)solverContract["supports"];
                    JArray solverLoads=(JArray)solverContract["loads"];
                    JObject directionalContract=solverSupports==null ? null : solverSupports.Cast<JObject>()
                        .FirstOrDefault(x=>String.Equals((string)x["name"],"C1038_Directional",StringComparison.Ordinal));
                    bool directionalBcContract=solverSupports!=null && solverSupports.Count==2 &&
                        directionalContract!=null &&
                        String.Equals((string)directionalContract["type"],"displacement",StringComparison.OrdinalIgnoreCase) &&
                        directionalContract["dx"]!=null && directionalContract["dx"].Type==JTokenType.Null &&
                        Math.Abs(((double?)directionalContract["dy"] ?? Double.NaN)-0.0)<1e-12 &&
                        directionalContract["dz"]!=null && directionalContract["dz"].Type==JTokenType.Null;
                    JObject realLoad=solverLoads==null ? null : solverLoads.Cast<JObject>()
                        .FirstOrDefault(x=>String.Equals((string)x["name"],"C1038_Force",StringComparison.Ordinal));
                    double expectedFxPerNode=-1000.0/loadIds.Length;
                    double expectedFzPerNode=100.0/loadIds.Length;
                    bool realLoadContract=realLoad!=null &&
                        String.Equals((string)realLoad["type"],"nodal_force_per_node",StringComparison.OrdinalIgnoreCase) &&
                        Math.Abs(((double?)realLoad["fx_per_node_n"] ?? 0.0)-expectedFxPerNode)<1e-12 &&
                        Math.Abs(((double?)realLoad["fz_per_node_n"] ?? 0.0)-expectedFzPerNode)<1e-12;
                    contractOk &= directionalBcContract && realLoadContract;
                    report["codeaster_contact_contract_pass"]=contractOk;
                    report["codeaster_directional_bc_contract_pass"]=directionalBcContract;
                    report["codeaster_directional_bc_group"]="C1038_LOAD";
                    report["codeaster_directional_bc_components"]=new JArray("DY");
                    report["codeaster_live_load_contract_pass"]=realLoadContract;
                    report["codeaster_live_fixed_bc_group"]="C1038_FIXED";
                    report["codeaster_live_load_group"]="C1038_LOAD";
                    report["codeaster_live_load_node_count"]=loadIds.Length;
                    report["codeaster_live_load_fx_total_n"]=-1000.0;
                    report["codeaster_live_load_fz_total_n"]=100.0;
'@
if($a.Contains($reportAnchor) -and -not $a.Contains('codeaster_directional_bc_contract_pass')){
    $a=$a.Replace($reportAnchor,$reportNew.TrimEnd())
}
elseif(-not $a.Contains('codeaster_directional_bc_contract_pass')){ throw 'C10.38 audit report anchor missing.' }
Set-Content $auditPath $a -Encoding UTF8

# ----------------------------------------------------------------------
# 4) Release identity.
# ----------------------------------------------------------------------
$g=[regex]::Replace((Get-Content $globalsPath -Raw),"\r\n?","`n")
$g=$g.Replace('AsterMax Mechanical C10.37','AsterMax Mechanical C10.38')
if(-not $g.Contains('AsterMax Mechanical C10.38')){ throw 'C10.38 Globals version anchor missing.' }
Set-Content $globalsPath $g -Encoding UTF8

Write-Host 'C10.38: live FeModel directional displacement + fixed support + force translation applied.' -ForegroundColor Green
