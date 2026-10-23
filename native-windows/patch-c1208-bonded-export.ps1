param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'

function Replace-C1208Required([string]$Text,[string]$Old,[string]$New) {
    $Old=[regex]::Replace($Old,"\r\n?","`n")
    $New=[regex]::Replace($New,"\r\n?","`n")
    if(-not $Text.Contains($Old)) { throw "C12.08 bonded export anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$exporterPath=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
$bridgePath=Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
$projectPath=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$exporter=[regex]::Replace((Get-Content -LiteralPath $exporterPath -Raw),"\r\n?","`n")
$bridge=[regex]::Replace((Get-Content -LiteralPath $bridgePath -Raw),"\r\n?","`n")
$project=Get-Content -LiteralPath $projectPath -Raw

if(-not $exporter.Contains('// ASTERMAX_C1208_BONDED_PLAN')) {
    $old='            JArray loads=(JArray)contract["loads"];'
    $new=@'
            JArray loads=(JArray)contract["loads"];
            // ASTERMAX_C1208_BONDED_PLAN
            // Validate geometry, support consistency and independent MPC rank
            // before creating any output. The caller's model remains unchanged.
            AsterMaxBondedMpc.Plan bondedPlan=AsterMaxBondedMpc.Build(contract);
'@
    $exporter=Replace-C1208Required $exporter $old $new
    $exporter=Replace-C1208Required $exporter '            mail.Add("FIN");' @'
            bondedPlan.AppendNodeGroups(mail,usedAsterGroupNames);
            mail.Add("FIN");
'@
    $exporter=Replace-C1208Required $exporter '            File.WriteAllText(commPath,comm,new System.Text.UTF8Encoding(false));' @'
            comm=bondedPlan.AddToCommand(comm);
            File.WriteAllText(commPath,comm,new System.Text.UTF8Encoding(false));
            string bondedBindingsPath=Path.Combine(outDir,baseName+".bonded-mpc.json");
            bondedPlan.WriteBindings(bondedBindingsPath);
'@
    $exporter=Replace-C1208Required $exporter '                ["contact_pair_count"]=contacts.Count,' @'
                ["contact_pair_count"]=contacts.Count,
                ["bonded_pair_count"]=bondedPlan.TieCount,
                ["bonded_mpc_report"]=bondedPlan.Report,
                ["generated_bonded_bindings"]=bondedPlan.TieCount>0?new JValue(Path.GetFileName(bondedBindingsPath)):JValue.CreateNull(),
'@
}

if(-not $bridge.Contains('// ASTERMAX_C1208_BONDED_CONSTRAINTS')) {
    $old=@'
            if (model.Constraints.Values.Any(x => x.Active) || model.InitialConditions.Values.Any(x => x.Active) ||
                model.StepCollection.StepsList.Any(s => s.DefinedFields.Values.Any(x => x.Active)))
                throw new NotSupportedException("Active constraints, initial conditions or defined fields are not supported by the C10.36 Code_Aster bridge.");
'@
    $new=@'
            // ASTERMAX_C1208_BONDED_CONSTRAINTS
            // Only the existing, explicit welded Tie is added. Other constraint
            // kinds and nonbonded contact laws retain their previous semantics.
            if (model.Constraints.Values.Any(x => x.Active && !(x is Tie)) || model.InitialConditions.Values.Any(x => x.Active) ||
                model.StepCollection.StepsList.Any(s => s.DefinedFields.Values.Any(x => x.Active)))
                throw new NotSupportedException("C12.08 admite uniones soldadas Tie; otras restricciones activas, condiciones iniciales y campos definidos no están soportados por este puente Code_Aster.");
'@
    $bridge=Replace-C1208Required $bridge $old $new
    $old='            root["contacts"] = contacts;'
    $new=@'
            JArray bondedTies = new JArray();
            int bondedIndex = contactIndex;
            foreach (var constraintEntry in model.Constraints)
            {
                Constraint constraint = constraintEntry.Value;
                if (constraint == null || !constraint.Active) continue;
                Tie tie = constraint as Tie;
                if (tie == null)
                    throw new NotSupportedException("Restricción activa no soportada: " + constraint.Name);
                if (!tie.Valid)
                    throw new InvalidOperationException("La unión soldada activa '" + tie.Name + "' no es válida. Revise sus superficies.");
                if (tie.MasterRegionType != RegionTypeEnum.SurfaceName || tie.SlaveRegionType != RegionTypeEnum.SurfaceName)
                    throw new NotSupportedException("La unión soldada '" + tie.Name + "' requiere superficies maestra y esclava con nombre.");
                if (Double.IsNaN(tie.PositionTolerance) || Double.IsInfinity(tie.PositionTolerance) || tie.PositionTolerance <= 0)
                    throw new InvalidOperationException("La unión soldada '" + tie.Name + "' requiere una tolerancia de posición explícita, finita y positiva en mm.");
                if (tie.Adjust)
                    throw new NotSupportedException("La unión soldada '" + tie.Name + "' requiere Adjust=false. C12.08 conserva las coordenadas y acopla el hueco mediante MPC afines.");
                bondedIndex++;
                string bondedSuffix = bondedIndex.ToString("000");
                bondedTies.Add(new JObject
                {
                    ["name"] = tie.Name,
                    ["position_tolerance_mm"] = tie.PositionTolerance,
                    ["adjust"] = false,
                    ["master"] = BuildCodeAsterContactSurface(model, tie.MasterRegionName, "AM_BM" + bondedSuffix, "M", bondedIndex),
                    ["slave"] = BuildCodeAsterContactSurface(model, tie.SlaveRegionName, "AM_BS" + bondedSuffix, "S", bondedIndex)
                });
            }
            root["bonded_ties"] = bondedTies;
            root["contacts"] = contacts;
'@
    $bridge=Replace-C1208Required $bridge $old $new
}

$exporter=[regex]::Replace($exporter,'public const string Version = "[^"]+";','public const string Version = "C12.08-bonded-mpc-v1";')
$bridge=[regex]::Replace($bridge,'public const string NativeBridgeVersion = "[^"]+";','public const string NativeBridgeVersion = "C12.08-bonded-mpc-v1";')
if(-not $project.Contains('<Compile Include="AsterMaxBondedMpc.cs" />')) {
    $project=Replace-C1208Required $project '<Compile Include="AsterMaxCodeAsterNativeExporter.cs" />' ('<Compile Include="AsterMaxCodeAsterNativeExporter.cs" />'+"`n"+'    <Compile Include="AsterMaxBondedMpc.cs" />')
}
$helper=Join-Path $PSScriptRoot 'AsterMaxBondedMpc.cs'
if(-not (Test-Path -LiteralPath $helper -PathType Leaf)) { throw "C12.08 production bonded MPC helper missing: $helper" }
Copy-Item -LiteralPath $helper -Destination (Join-Path $Root 'PrePoMax/AsterMaxBondedMpc.cs') -Force
Set-Content -LiteralPath $exporterPath -Value $exporter -Encoding UTF8 -NoNewline
Set-Content -LiteralPath $bridgePath -Value $bridge -Encoding UTF8 -NoNewline
Set-Content -LiteralPath $projectPath -Value $project -Encoding UTF8 -NoNewline
Write-Host 'C12.08 explicit welded Tie bridge, affine TETRA4 MPC export and support-seeded rank audit applied.'
