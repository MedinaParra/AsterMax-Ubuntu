param([string]$Root)
$ErrorActionPreference = 'Stop'

$bridgePath = Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
$bridge = @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using CaeGlobals;
using CaeMesh;
using CaeModel;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    /// <summary>
    /// Native translation boundary from the live AsterMax/PrePoMax FeModel to the
    /// solver-neutral astermax-model-contract/v0 consumed by the Code_Aster adapter.
    /// This class exports model definition only. It never creates or fabricates FEA results.
    /// </summary>
    public static class AsterMaxModelContractBridge
    {
        public const string Schema = "astermax-model-contract/v0";
        public const string NativeBridgeVersion = "C9.60-native-bridge-v0";

        public static JObject Build(FeModel model)
        {
            if (model == null) throw new ArgumentNullException(nameof(model));
            if (model.Mesh == null) throw new InvalidOperationException("Model has no FE mesh.");
            if (model.Mesh.Nodes == null || model.Mesh.Nodes.Count == 0)
                throw new InvalidOperationException("Model mesh contains no nodes.");
            if (model.Mesh.Elements == null || model.Mesh.Elements.Count == 0)
                throw new InvalidOperationException("Model mesh contains no elements.");
            if (model.UnitSystem == null || model.UnitSystem.UnitSystemType != UnitSystemType.MM_TON_S_C)
                throw new NotSupportedException("C9.60 native Code_Aster bridge currently requires mm-ton-s-C, equivalent to mm-N-MPa mechanical units.");

            JObject root = new JObject();
            root["schema"] = Schema;
            root["bridge"] = NativeBridgeVersion;
            root["name"] = String.IsNullOrWhiteSpace(model.Name) ? "AsterMax Model" : model.Name;
            root["unit_system"] = "MM_N_S_MPA";
            root["source"] = new JObject
            {
                ["kind"] = "live_astermax_femodel",
                ["fea_results_included"] = false,
                ["solver_execution_claimed"] = false
            };

            JObject mesh = new JObject();
            JArray nodes = new JArray();
            foreach (var entry in model.Mesh.Nodes.OrderBy(e => e.Key))
            {
                FeNode n = entry.Value;
                nodes.Add(new JObject
                {
                    ["id"] = "N" + n.Id,
                    ["x"] = n.X,
                    ["y"] = n.Y,
                    ["z"] = n.Z
                });
            }
            mesh["nodes"] = nodes;

            JArray elements = new JArray();
            HashSet<string> elementTypes = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var entry in model.Mesh.Elements.OrderBy(e => e.Key))
            {
                FeElement e = entry.Value;
                string type = GetElementType(e);
                elementTypes.Add(type);
                JArray connectivity = new JArray();
                foreach (int nodeId in e.NodeIds) connectivity.Add("N" + nodeId);
                elements.Add(new JObject
                {
                    ["id"] = "E" + e.Id,
                    ["type"] = type,
                    ["nodes"] = connectivity
                });
            }
            mesh["element_type"] = elementTypes.Count == 1 ? elementTypes.First() : "MIXED";
            mesh["elements"] = elements;

            JObject nodeGroups = new JObject();
            foreach (var entry in model.Mesh.NodeSets)
            {
                JArray ids = new JArray();
                if (entry.Value.Labels != null)
                    foreach (int id in entry.Value.Labels.OrderBy(i => i)) ids.Add("N" + id);
                nodeGroups[entry.Key] = ids;
            }
            mesh["node_groups"] = nodeGroups;
            root["mesh"] = mesh;

            JArray materials = new JArray();
            foreach (var entry in model.Materials)
            {
                Material m = entry.Value;
                Elastic elastic = m.GetProperty<Elastic>() as Elastic;
                ElasticWithDensity elasticDensity = m.GetProperty<ElasticWithDensity>() as ElasticWithDensity;
                JObject item = new JObject { ["name"] = m.Name };
                if (elastic != null && elastic.YoungsPoissonsTemp != null && elastic.YoungsPoissonsTemp.Length > 0)
                {
                    item["young_modulus_mpa"] = elastic.YoungsPoissonsTemp[0][0];
                    item["poisson"] = elastic.YoungsPoissonsTemp[0][1];
                    item["constitutive_model"] = "isotropic_linear_elastic";
                }
                else if (elasticDensity != null)
                {
                    item["young_modulus_mpa"] = elasticDensity.YoungsModulus;
                    item["poisson"] = elasticDensity.PoissonsRatio;
                    item["constitutive_model"] = "isotropic_linear_elastic";
                }
                else
                {
                    item["unsupported_for_code_aster_adapter_v0"] = true;
                }
                materials.Add(item);
            }
            root["materials"] = materials;

            Step selectedStep = null;
            if (model.StepCollection != null && model.StepCollection.StepsList != null)
                selectedStep = model.StepCollection.StepsList.FirstOrDefault(s => s is StaticStep && s.RunAnalysis);
            if (selectedStep == null)
                throw new NotSupportedException("C9.60 bridge requires an enabled StaticStep.");

            JArray supports = new JArray();
            foreach (var entry in selectedStep.BoundaryConditions)
            {
                BoundaryCondition bc = entry.Value;
                if (bc is FixedBC)
                {
                    supports.Add(new JObject
                    {
                        ["name"] = bc.Name,
                        ["group"] = bc.RegionName,
                        ["type"] = "fixed_support",
                        ["dx"] = 0.0,
                        ["dy"] = 0.0,
                        ["dz"] = 0.0,
                        ["source_type"] = "FixedBC"
                    });
                }
                else
                {
                    supports.Add(new JObject
                    {
                        ["name"] = bc.Name,
                        ["source_type"] = bc.GetType().Name,
                        ["unsupported_for_code_aster_adapter_v0"] = true
                    });
                }
            }
            root["supports"] = supports;

            JArray loads = new JArray();
            string firstLoadGroup = null;
            foreach (var entry in selectedStep.Loads)
            {
                Load load = entry.Value;
                CLoad cload = load as CLoad;
                if (cload == null)
                {
                    loads.Add(new JObject
                    {
                        ["name"] = load.Name,
                        ["source_type"] = load.GetType().Name,
                        ["unsupported_for_code_aster_adapter_v0"] = true
                    });
                    continue;
                }

                string group;
                int multiplicity;
                if (cload.RegionType == RegionTypeEnum.NodeId)
                {
                    group = "ASTERMAX_NODE_" + cload.NodeId;
                    multiplicity = 1;
                    if (nodeGroups[group] == null) nodeGroups[group] = new JArray("N" + cload.NodeId);
                }
                else
                {
                    group = cload.RegionName;
                    FeNodeSet nodeSet;
                    if (String.IsNullOrWhiteSpace(group) || !model.Mesh.NodeSets.TryGetValue(group, out nodeSet) || nodeSet.Labels == null)
                        throw new NotSupportedException("CLoad region must resolve to an FE node set for Code_Aster adapter v0.");
                    multiplicity = nodeSet.Labels.Length;
                }
                if (firstLoadGroup == null) firstLoadGroup = group;
                loads.Add(new JObject
                {
                    ["name"] = cload.Name,
                    ["group"] = group,
                    ["type"] = "total_nodal_force",
                    ["source_semantics"] = "PrePoMax_CLoad_per_node",
                    ["node_count"] = multiplicity,
                    ["fx_per_node_n"] = cload.F1,
                    ["fy_per_node_n"] = cload.F2,
                    ["fz_per_node_n"] = cload.F3,
                    ["fx_total_n"] = cload.F1 * multiplicity,
                    ["fy_total_n"] = cload.F2 * multiplicity,
                    ["fz_total_n"] = cload.F3 * multiplicity
                });
            }
            root["loads"] = loads;
            root["analysis"] = new JObject
            {
                ["type"] = "static_structural",
                ["source_step"] = selectedStep.Name,
                ["nlgeom"] = selectedStep.Nlgeom
            };
            root["postprocess"] = new JObject
            {
                ["displacement_probe_group"] = firstLoadGroup,
                ["stress_fields"] = new JArray("SIGM_ELNO", "SIEQ_ELNO"),
                ["export_med"] = true,
                ["policy"] = "requested_outputs_only_not_fea_results"
            };
            root["validation"] = new JObject
            {
                ["node_count"] = model.Mesh.Nodes.Count,
                ["element_count"] = model.Mesh.Elements.Count,
                ["material_count"] = model.Materials.Count,
                ["support_count"] = supports.Count,
                ["load_count"] = loads.Count,
                ["no_fea_results_claimed"] = true
            };
            return root;
        }

        public static string Export(FeModel model, string fileName)
        {
            JObject contract = Build(model);
            string json = contract.ToString(Formatting.Indented);
            File.WriteAllText(fileName, json);
            return json;
        }

        private static string GetElementType(FeElement e)
        {
            if (e is LinearHexaElement) return "HEXA8";
            if (e is ParabolicHexaElement) return "HEXA20";
            if (e is LinearTetraElement) return "TETRA4";
            if (e is ParabolicTetraElement) return "TETRA10";
            if (e is LinearWedgeElement) return "PENTA6";
            if (e is ParabolicWedgeElement) return "PENTA15";
            throw new NotSupportedException("Unsupported solid element for C9.60 bridge: " + e.GetType().Name);
        }
    }
}
'@
Set-Content $bridgePath $bridge -Encoding UTF8

$uiPath = Join-Path $Root 'PrePoMax/AsterMaxModelContractUi.cs'
$ui = @'
using System;
using System.IO;
using System.Windows.Forms;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private void ExportAsterMaxModelContract()
        {
            try
            {
                if (_controller == null || _controller.Model == null)
                {
                    MessageBoxes.ShowError("No active AsterMax model is available.");
                    return;
                }
                using (SaveFileDialog dlg = new SaveFileDialog())
                {
                    dlg.Title = "Export AsterMax Solver Contract";
                    dlg.Filter = "AsterMax model contract (*.astermax.json)|*.astermax.json|JSON (*.json)|*.json";
                    dlg.FileName = "astermax-model.astermax.json";
                    if (dlg.ShowDialog(this) != DialogResult.OK) return;
                    AsterMaxModelContractBridge.Export(_controller.Model, dlg.FileName);
                    tsslState.Text = "Solver contract exported: " + Path.GetFileName(dlg.FileName);
                }
            }
            catch (Exception ex)
            {
                ExceptionTools.Show(this, ex);
            }
        }
    }
}
'@
Set-Content $uiPath $ui -Encoding UTF8

$projPath = Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$proj = Get-Content $projPath -Raw
if(-not $proj.Contains('AsterMaxModelContractBridge.cs')) {
    $anchor = '<Compile Include="Forms\FrmMain.cs">'
    if(-not $proj.Contains($anchor)){ throw 'PrePoMax.csproj FrmMain anchor not found for C9.60 bridge.' }
    $insert = '<Compile Include="AsterMaxModelContractBridge.cs" />' + [Environment]::NewLine +
              '    <Compile Include="AsterMaxModelContractUi.cs" />' + [Environment]::NewLine + '    ' + $anchor
    $proj = $proj.Replace($anchor, $insert)
    Set-Content $projPath $proj -Encoding UTF8
}

$nativeUi = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(Test-Path $nativeUi) {
    $text = Get-Content $nativeUi -Raw
    $old = 'ribbon.TabPages.Add(BuildRibbonPage("Solution", new Control[] { InfoChip("Code_Aster adapter: next integration gate") }));'
    if($text.Contains($old)) {
        $new = 'ribbon.TabPages.Add(BuildRibbonPage("Solution", new Control[] {' + [Environment]::NewLine +
               '                CommandButton("Export Solver Contract", () => ExportAsterMaxModelContract()),' + [Environment]::NewLine +
               '                InfoChip("Code_Aster | model contract v0 | no synthetic results")' + [Environment]::NewLine +
               '            }));'
        $text = $text.Replace($old, $new)
        Set-Content $nativeUi $text -Encoding UTF8
    }
    elseif(-not $text.Contains('Export Solver Contract')) {
        throw 'C9.60 Solution ribbon anchor not found.'
    }
}
else { throw 'AsterMaxNativeUi.cs missing; apply native UI patch before C9.60 bridge.' }

Write-Host 'C9.60 native FeModel -> solver contract bridge injected.' -ForegroundColor Green
