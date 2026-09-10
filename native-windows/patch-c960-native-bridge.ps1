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
    public static class AsterMaxModelContractBridge
    {
        public const string Schema = "astermax-model-contract/v0";
        public const string NativeBridgeVersion = "C9.60-native-bridge-v0";

        public static JObject Build(FeModel model)
        {
            if (model == null) throw new ArgumentNullException(nameof(model));
            if (model.Mesh == null) throw new InvalidOperationException("Model has no FE mesh.");
            if (model.Mesh.Nodes == null || model.Mesh.Nodes.Count == 0) throw new InvalidOperationException("Model mesh contains no nodes.");
            if (model.Mesh.Elements == null || model.Mesh.Elements.Count == 0) throw new InvalidOperationException("Model mesh contains no elements.");
            if (model.UnitSystem == null || model.UnitSystem.UnitSystemType != UnitSystemType.MM_TON_S_C)
                throw new NotSupportedException("C9.60 native Code_Aster bridge currently requires mm-ton-s-C, equivalent to mm-N-MPa mechanical units.");

            JObject root = new JObject();
            root["schema"] = Schema;
            root["bridge"] = NativeBridgeVersion;
            root["name"] = String.IsNullOrWhiteSpace(model.Name) ? "AsterMax Model" : model.Name;
            root["unit_system"] = "MM_N_S_MPA";
            root["source"] = new JObject { ["kind"] = "live_astermax_femodel", ["fea_results_included"] = false, ["solver_execution_claimed"] = false };

            JObject mesh = new JObject();
            JArray nodes = new JArray();
            foreach (var entry in model.Mesh.Nodes.OrderBy(e => e.Key))
            {
                FeNode n = entry.Value;
                nodes.Add(new JObject { ["id"] = "N" + n.Id, ["x"] = n.X, ["y"] = n.Y, ["z"] = n.Z });
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
                elements.Add(new JObject { ["id"] = "E" + e.Id, ["type"] = type, ["nodes"] = connectivity });
            }
            mesh["element_type"] = elementTypes.Count == 1 ? elementTypes.First() : "MIXED";
            mesh["elements"] = elements;

            JObject nodeGroups = new JObject();
            foreach (var entry in model.Mesh.NodeSets)
            {
                JArray ids = new JArray();
                if (entry.Value.Labels != null) foreach (int id in entry.Value.Labels.OrderBy(i => i)) ids.Add("N" + id);
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
                else item["unsupported_for_code_aster_adapter_v0"] = true;
                materials.Add(item);
            }
            root["materials"] = materials;

            JArray supports = new JArray();
            JArray loads = new JArray();
            int stepCount = 0;
            foreach (Step step in model.StepCollection.StepsList)
            {
                if (step is InitialStep) continue;
                stepCount++;
                foreach (var bcEntry in step.BoundaryConditions)
                {
                    FixedBC fixedBc = bcEntry.Value as FixedBC;
                    if (fixedBc != null)
                    {
                        string group = RegionToNodeGroup(model, fixedBc.RegionName, fixedBc.RegionType, nodeGroups);
                        supports.Add(new JObject { ["name"] = fixedBc.Name, ["type"] = "fixed", ["group"] = group, ["dx"] = 0.0, ["dy"] = 0.0, ["dz"] = 0.0 });
                    }
                    else supports.Add(new JObject { ["name"] = bcEntry.Value.Name, ["type"] = bcEntry.Value.GetType().Name, ["unsupported_for_code_aster_adapter_v0"] = true });
                }
                foreach (var loadEntry in step.Loads)
                {
                    CLoad cload = loadEntry.Value as CLoad;
                    if (cload != null)
                    {
                        string group = RegionToNodeGroup(model, cload.RegionName, cload.RegionType, nodeGroups);
                        loads.Add(new JObject
                        {
                            ["name"] = cload.Name,
                            ["type"] = "nodal_force_total",
                            ["group"] = group,
                            ["fx_total_n"] = cload.F1,
                            ["fy_total_n"] = cload.F2,
                            ["fz_total_n"] = cload.F3
                        });
                    }
                    else loads.Add(new JObject { ["name"] = loadEntry.Value.Name, ["type"] = loadEntry.Value.GetType().Name, ["unsupported_for_code_aster_adapter_v0"] = true });
                }
            }
            if (stepCount != 1) throw new NotSupportedException("C9.60 native bridge v0 requires exactly one non-initial analysis step.");
            root["analysis"] = new JObject { ["type"] = "static_structural", ["step_count"] = stepCount };
            root["supports"] = supports;
            root["loads"] = loads;
            root["postprocess"] = new JObject { ["displacement_probe_group"] = loads.Count > 0 ? (string)loads[0]["group"] : null };
            return root;
        }

        public static void Export(FeModel model, string fileName)
        {
            JObject contract = Build(model);
            File.WriteAllText(fileName, contract.ToString(Formatting.Indented), new System.Text.UTF8Encoding(false));
        }

        private static string GetElementType(FeElement e)
        {
            if (e is LinearHexaElement) return "HEXA8";
            if (e is LinearTetraElement) return "TETRA4";
            if (e is ParabolicTetraElement) return "TETRA10";
            return e.GetType().Name;
        }

        private static string RegionToNodeGroup(FeModel model, string regionName, RegionTypeEnum regionType, JObject nodeGroups)
        {
            if (regionType == RegionTypeEnum.NodeSetName)
            {
                if (nodeGroups[regionName] == null) throw new InvalidOperationException("Node group not found: " + regionName);
                return regionName;
            }
            throw new NotSupportedException("C9.60 native bridge v0 currently requires node-set scoping for fixed BCs and nodal loads. Region: " + regionName + " / " + regionType);
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
using CaeGlobals;
namespace PrePoMax
{
    public partial class FrmMain
    {
        private void ExportAsterMaxModelContract()
        {
            try
            {
                if (_controller == null || _controller.Model == null) { MessageBoxes.ShowError("No active AsterMax model is available."); return; }
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
            catch (Exception ex) { ExceptionTools.Show(this, ex); }
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
    $insert = '<Compile Include="AsterMaxModelContractBridge.cs" />' + [Environment]::NewLine + '    <Compile Include="AsterMaxModelContractUi.cs" />' + [Environment]::NewLine + '    ' + $anchor
    $proj = $proj.Replace($anchor, $insert)
    Set-Content $projPath $proj -Encoding UTF8
}

$nativeUi = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(Test-Path $nativeUi) {
    $text = Get-Content $nativeUi -Raw
    if(-not $text.Contains('Export Solver Contract')) {
        $legacy = 'ribbon.TabPages.Add(BuildRibbonPage("Solution", new Control[] { InfoChip("Code_Aster adapter: next integration gate") }));'
        if($text.Contains($legacy)) {
            $replacement = 'ribbon.TabPages.Add(BuildRibbonPage("Solution", new Control[] {' + [Environment]::NewLine + '                CommandButton("Export Solver Contract", () => ExportAsterMaxModelContract()),' + [Environment]::NewLine + '                InfoChip("Code_Aster | model contract v0 | no synthetic results")' + [Environment]::NewLine + '            }));'
            $text = $text.Replace($legacy, $replacement)
        } else {
            $modern = '                StateCard("Solver", "Code_Aster integration path"),'
            if(-not $text.Contains($modern)){ throw 'C9.60/C10.00 Solution ribbon anchor not found.' }
            $insert = '                CommandTile("Export Solver Contract", "SOLVER", () => ExportAsterMaxModelContract(), true),' + [Environment]::NewLine + $modern
            $text = $text.Replace($modern,$insert)
        }
        Set-Content $nativeUi $text -Encoding UTF8
    }
}
else { throw 'AsterMaxNativeUi.cs missing; apply native UI patch before C9.60 bridge.' }

Write-Host 'C9.60 native FeModel -> solver contract bridge injected (CLoad double API verified).' -ForegroundColor Green
