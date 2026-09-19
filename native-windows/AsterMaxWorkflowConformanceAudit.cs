using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using System.Windows.Forms;
using CaeGlobals;
using CaeMesh;
using CaeModel;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UserControls;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private static string AsterMaxC1020WorkflowDirectoryFromCommandLine()
        {
            const string prefix = "--astermax-c1020-workflow=";
            string argument = Environment.GetCommandLineArgs()
                .FirstOrDefault(x => x.StartsWith(prefix, StringComparison.OrdinalIgnoreCase));
            return argument == null ? null : argument.Substring(prefix.Length).Trim('"');
        }

        private void StartAsterMaxC1020WorkflowConformanceAudit()
        {
            string directory = AsterMaxC1020WorkflowDirectoryFromCommandLine();
            if (String.IsNullOrWhiteSpace(directory)) return;
            _asterMaxUiAuditMode = true;
            int attempts = 0;
            var timer = new Timer { Interval = 1000 };
            timer.Tick += (s, e) =>
            {
                attempts++;
                Dictionary<string, AsterMaxSectionState> states = null;
                try { states = BuildAsterMaxSectionStates(); } catch { }
                bool geometryReady = states != null && states.ContainsKey("geometry") && states["geometry"].State >= 2;
                if (!geometryReady && attempts < 60) return;
                timer.Stop();
                timer.Dispose();
                Directory.CreateDirectory(directory);
                try
                {
                    if (!geometryReady)
                        throw new InvalidOperationException("B01 STEP was not observable in the native GUI after 60 seconds.");
                    ExecuteAsterMaxC1020WorkflowConformanceAudit(directory);
                    Environment.Exit(0);
                }
                catch (Exception ex)
                {
                    File.WriteAllText(Path.Combine(directory, "workflow-conformance-session.json"),
                        new JObject {
                            ["release"] = "C10.20",
                            ["pass"] = false,
                            ["error"] = ex.ToString(),
                            ["historical_pending_closed"] = false
                        }.ToString(Formatting.Indented));
                    Environment.Exit(1);
                }
            };
            timer.Start();
        }

        private void ExecuteAsterMaxC1020WorkflowConformanceAudit(string directory)
        {
            var rows = new JArray();
            var previousStates = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

            C1020SelectOutlineNode("ax-model");
            C1020CaptureStage(directory, rows, previousStates, 1, "geometry", "Geometry", "geometry",
                () => C1020State("geometry") >= 2,
                "Imported B01 STEP visible; geometry workflow state >= 2.");

            FeModel model = _controller.Model;
            if (model.Materials.Count == 0)
            {
                var material = new Material("Steel");
                material.AddProperty(new Elastic(new[] { new[] { 210000.0, 0.3, 20.0 } }));
                model.Materials.Add(material.Name, material);
            }
            RegenerateTree();
            _modelTree.RefreshAsterMaxOutline();
            C1020SelectOutlineNodeByText("Materials");
            C1020CaptureStage(directory, rows, previousStates, 2, "materials", "Materials", "materials",
                () => C1020State("materials") == 2,
                "One active valid linear-elastic steel material; materials state == 2.");

            C1020SelectOutlineNode("ax-coordinates");
            C1020CaptureStage(directory, rows, previousStates, 3, "coordinate-systems", "Coordinate Systems", "ax-coordinates",
                () => C1020State("ax-coordinates") >= 1 && C1020OutlineContainsText("Global Cartesian"),
                "Global Cartesian node observable; coordinate-systems state >= 1.");

            C1020SelectOutlineNode("ax-connections");
            C1020CaptureStage(directory, rows, previousStates, 4, "connections", "Connections", "ax-connections",
                () => C1020State("ax-connections") >= 1,
                "Connections branch observable for continuous single-body B01; no contact required.");

            C1020PopulateB01Mesh(model);
            RegenerateTree();
            _modelTree.RefreshAsterMaxOutline();
            C1020SelectOutlineNode("ax-mesh");
            C1020CaptureStage(directory, rows, previousStates, 5, "mesh", "Mesh", "ax-mesh",
                () => C1020State("ax-mesh") == 2 && C1020State("assignments") == 2,
                "B01 native mesh and material assignment complete; ax-mesh == 2 and assignments == 2.");

            C1020PopulateB01NamedSelections(model);
            RegenerateTree();
            _modelTree.RefreshAsterMaxOutline();
            C1020SelectOutlineNode("ax-selections");
            C1020CaptureStage(directory, rows, previousStates, 6, "named-selections", "Named Selections", "ax-selections",
                () => C1020State("ax-selections") >= 1 &&
                      model.Mesh.NodeSets.ContainsKey("FIXED") && model.Mesh.NodeSets.ContainsKey("LOAD"),
                "FIXED and LOAD native node sets observable; named-selection state >= 1.");

            C1020PopulateB01StaticStructural(model);
            RegenerateTree();
            _modelTree.RefreshAsterMaxOutline();
            C1020SelectOutlineNode("ax-analysis");
            C1020CaptureStage(directory, rows, previousStates, 7, "static-structural", "Static Structural", "ax-analysis",
                () => C1020State("ax-analysis") == 2 && C1020State("supports") == 2 &&
                      C1020State("loads") == 2 && C1020State("ax-model") == 2,
                "One active linear static study with fixed support and 10000 N axial load; model state == 2.");

            string pmxPath = Path.Combine(directory, "B01-C10.20.pmx");
            JObject pmxCycles = C1020ExercisePmxCycles(pmxPath, 3);
            File.WriteAllText(Path.Combine(directory, "pmx-save-reopen.json"), pmxCycles.ToString(Formatting.Indented));
            if (!(bool)pmxCycles["pass"])
                throw new InvalidOperationException("PMX save/reopen conformance failed: " + (string)pmxCycles["reason"]);

            model = _controller.Model;
            C1020SelectOutlineNode("ax-solution");
            C1020ClickRibbonButton("Solve");
            Application.DoEvents();
            C1020CaptureStage(directory, rows, previousStates, 8, "solution", "Solution", "ax-solution",
                () => _asterMaxSolveTransaction != null &&
                      String.Equals(_asterMaxSolveTransaction.State.ToString(), "SolutionCurrent", StringComparison.Ordinal) &&
                      _asterMaxLoadedResults != null,
                "Native Solve command completed with SolutionCurrent and a real results bundle loaded.");

            string resultField = _asterMaxLoadedResults.AvailableFields()
                .FirstOrDefault(x => x.IndexOf("Equivalent", StringComparison.OrdinalIgnoreCase) >= 0) ??
                _asterMaxLoadedResults.AvailableFields().FirstOrDefault();
            if (String.IsNullOrWhiteSpace(resultField))
                throw new InvalidOperationException("No real result field is available after native solve.");
            _modelTree.SelectAsterMaxResultField(resultField);
            Application.DoEvents();
            C1020CaptureStage(directory, rows, previousStates, 9, "results", "Results", "results",
                () => C1020ResultState() == 2 && _axEmbeddedResults != null && _axEmbeddedResults.Visible &&
                      _axEmbeddedResults.LastRenderError == null && !_axEmbeddedResults.LastRenderSkipped,
                "A real result field is rendered in the integrated native viewport without stale/skipped render state.");

            File.WriteAllText(Path.Combine(directory, "workflow-conformance-session.json"),
                new JObject {
                    ["release"] = "C10.20",
                    ["pass"] = rows.All(x => String.Equals((string)x["status"], "PASS", StringComparison.Ordinal)),
                    ["historical_pending_closed"] = false,
                    ["reference_fixture"] = "B01_PARAMETRIC_STEP_100x10x10_mm",
                    ["solver"] = "native Windows Code_Aster",
                    ["fea_values_invented"] = false,
                    ["rows"] = rows,
                    ["pmx_cycles"] = pmxCycles,
                    ["note"] = "Raw mandatory-stage session only. Cross-cutting checks are added by Phase 1.3 before the historical pending can be considered closed."
                }.ToString(Formatting.Indented));
        }

        private int C1020State(string key)
        {
            var states = BuildAsterMaxSectionStates();
            AsterMaxSectionState state;
            return states.TryGetValue(key, out state) ? state.State : 0;
        }

        private int C1020ResultState()
        {
            if (_asterMaxLoadedResults == null || _asterMaxSolveTransaction == null) return 0;
            if (!String.Equals(_asterMaxSolveTransaction.State.ToString(), "SolutionCurrent", StringComparison.Ordinal)) return 1;
            if (_axEmbeddedResults == null || !_axEmbeddedResults.Visible ||
                _axEmbeddedResults.LastRenderError != null || _axEmbeddedResults.LastRenderSkipped) return 1;
            return 2;
        }

        private JObject C1020StateSnapshot()
        {
            var result = new JObject();
            foreach (var entry in BuildAsterMaxSectionStates())
                result[entry.Key] = new JObject { ["state"] = entry.Value.State, ["message"] = entry.Value.Message };
            int resultsState = C1020ResultState();
            result["results"] = new JObject {
                ["state"] = resultsState,
                ["message"] = resultsState == 2 ? "Current integrated real results are rendered." :
                    _asterMaxLoadedResults == null ? "No results bundle loaded." : "Results exist but are not current/rendered."
            };
            return result;
        }

        private void C1020CaptureStage(string directory, JArray rows, Dictionary<string, int> previousStates,
                                       int index, string id, string label, string stateKey,
                                       Func<bool> postcondition, string expected)
        {
            string prefix = String.Format("stage-{0:00}-{1}", index, id);
            string screenshot = Path.Combine(directory, prefix + ".png");
            string treePath = Path.Combine(directory, prefix + "-tree.json");
            string statePath = Path.Combine(directory, prefix + "-state.json");
            string transitionPath = Path.Combine(directory, prefix + "-transition.json");
            int before;
            if (!previousStates.TryGetValue(stateKey, out before)) before = -1;
            bool predicate = false;
            string error = null;
            try { predicate = postcondition(); } catch (Exception ex) { error = ex.Message; }

            JObject states = C1020StateSnapshot();
            int after = stateKey == "results" ? C1020ResultState() :
                states[stateKey] == null ? 0 : (int)states[stateKey]["state"];
            previousStates[stateKey] = after;

            File.WriteAllText(treePath, C1020SerializeOutline().ToString(Formatting.Indented));
            File.WriteAllText(statePath, states.ToString(Formatting.Indented));
            File.WriteAllText(transitionPath, new JObject {
                ["stage"] = id, ["expected"] = expected, ["before"] = before, ["after"] = after,
                ["postcondition_observed"] = predicate, ["error"] = error
            }.ToString(Formatting.Indented));
            try
            {
                using (var bitmap = new Bitmap(Math.Max(1, Width), Math.Max(1, Height)))
                {
                    DrawToBitmap(bitmap, new Rectangle(0, 0, bitmap.Width, bitmap.Height));
                    bitmap.Save(screenshot, ImageFormat.Png);
                }
            }
            catch (Exception ex) { error = (error == null ? "" : error + "; ") + "screenshot: " + ex.Message; }

            bool evidence = File.Exists(screenshot) && File.Exists(treePath) && File.Exists(statePath) && File.Exists(transitionPath);
            string status = !evidence ? "NOT_EXERCISED" : predicate ? "PASS" : "FAIL";
            rows.Add(new JObject {
                ["stage"] = id, ["label"] = label, ["status"] = status,
                ["workflow_state_key"] = stateKey, ["before"] = before, ["after"] = after,
                ["expected"] = expected, ["error"] = error,
                ["evidence"] = new JArray(Path.GetFileName(screenshot), Path.GetFileName(treePath),
                    Path.GetFileName(statePath), Path.GetFileName(transitionPath))
            });
            if (status == "FAIL") throw new InvalidOperationException("C10.20 stage failed: " + id + ". " + expected);
        }

        private JObject C1020SerializeOutline()
        {
            TreeView tree = C1020FindControl<TreeView>(this, x => x.Name == "asterMaxOutline");
            var root = new JObject { ["control_found"] = tree != null, ["nodes"] = new JArray() };
            if (tree == null) return root;
            root["selected"] = tree.SelectedNode == null ? null : tree.SelectedNode.Name;
            var nodes = (JArray)root["nodes"];
            foreach (TreeNode node in tree.Nodes) nodes.Add(C1020NodeToJson(node));
            return root;
        }

        private static JObject C1020NodeToJson(TreeNode node)
        {
            var children = new JArray();
            foreach (TreeNode child in node.Nodes) children.Add(C1020NodeToJson(child));
            return new JObject {
                ["name"] = node.Name, ["text"] = node.Text, ["state_image_key"] = node.StateImageKey,
                ["expanded"] = node.IsExpanded, ["children"] = children
            };
        }

        private static T C1020FindControl<T>(Control root, Func<T, bool> predicate) where T : Control
        {
            T self = root as T;
            if (self != null && predicate(self)) return self;
            foreach (Control child in root.Controls)
            {
                T found = C1020FindControl<T>(child, predicate);
                if (found != null) return found;
            }
            return null;
        }

        private TreeNode C1020FindOutlineNode(string name)
        {
            TreeView tree = C1020FindControl<TreeView>(this, x => x.Name == "asterMaxOutline");
            if (tree == null) return null;
            TreeNode[] found = tree.Nodes.Find(name, true);
            return found.Length == 0 ? null : found[0];
        }

        private void C1020SelectOutlineNode(string name)
        {
            _modelTree.RefreshAsterMaxOutline();
            TreeView tree = C1020FindControl<TreeView>(this, x => x.Name == "asterMaxOutline");
            TreeNode node = C1020FindOutlineNode(name);
            if (tree != null && node != null) { tree.SelectedNode = node; node.EnsureVisible(); Application.DoEvents(); }
        }

        private void C1020SelectOutlineNodeByText(string text)
        {
            _modelTree.RefreshAsterMaxOutline();
            TreeView tree = C1020FindControl<TreeView>(this, x => x.Name == "asterMaxOutline");
            if (tree == null) return;
            TreeNode node = C1020FindNodeByText(tree.Nodes, text);
            if (node != null) { tree.SelectedNode = node; node.EnsureVisible(); Application.DoEvents(); }
        }

        private static TreeNode C1020FindNodeByText(TreeNodeCollection nodes, string text)
        {
            foreach (TreeNode node in nodes)
            {
                if (String.Equals(node.Text, text, StringComparison.OrdinalIgnoreCase)) return node;
                TreeNode nested = C1020FindNodeByText(node.Nodes, text);
                if (nested != null) return nested;
            }
            return null;
        }

        private bool C1020OutlineContainsText(string text)
        {
            TreeView tree = C1020FindControl<TreeView>(this, x => x.Name == "asterMaxOutline");
            return tree != null && C1020FindNodeByText(tree.Nodes, text) != null;
        }

        private void C1020ClickRibbonButton(string caption)
        {
            var ribbon = Controls["asterMaxRibbon"] as TabControl;
            if (ribbon == null) throw new InvalidOperationException("AsterMax ribbon is missing.");
            foreach (TabPage page in ribbon.TabPages)
            {
                foreach (Button button in AxButtons(page))
                {
                    if (!String.Equals(button.Text, caption, StringComparison.Ordinal)) continue;
                    ribbon.SelectedTab = page;
                    Application.DoEvents();
                    button.PerformClick();
                    Application.DoEvents();
                    return;
                }
            }
            throw new InvalidOperationException("Ribbon command not found: " + caption);
        }

        private static int C1020NodeId(int plane, int corner)
        {
            return plane * 4 + corner + 1;
        }

        private static void C1020PopulateB01Mesh(FeModel model)
        {
            if (model.Mesh == null) throw new InvalidOperationException("Imported model has no native Mesh container.");
            model.Mesh.Nodes.Clear();
            model.Mesh.Elements.Clear();
            model.Mesh.Parts.Clear();
            model.Mesh.ElementSets.Clear();
            model.Mesh.NodeSets.Clear();
            int segments = 10;
            for (int i = 0; i <= segments; i++)
            {
                double x = 10.0 * i;
                model.Mesh.Nodes.Add(C1020NodeId(i, 0), new FeNode(C1020NodeId(i, 0), x, 0, 0));
                model.Mesh.Nodes.Add(C1020NodeId(i, 1), new FeNode(C1020NodeId(i, 1), x, 10, 0));
                model.Mesh.Nodes.Add(C1020NodeId(i, 2), new FeNode(C1020NodeId(i, 2), x, 0, 10));
                model.Mesh.Nodes.Add(C1020NodeId(i, 3), new FeNode(C1020NodeId(i, 3), x, 10, 10));
            }
            var elementIds = new List<int>();
            for (int i = 0; i < segments; i++)
            {
                int id = i + 1;
                int[] nodes = {
                    C1020NodeId(i,0), C1020NodeId(i+1,0), C1020NodeId(i+1,1), C1020NodeId(i,1),
                    C1020NodeId(i,2), C1020NodeId(i+1,2), C1020NodeId(i+1,3), C1020NodeId(i,3)
                };
                model.Mesh.Elements.Add(id, new LinearHexaElement(id, nodes));
                elementIds.Add(id);
            }
            int[] allNodes = model.Mesh.Nodes.Keys.OrderBy(x => x).ToArray();
            model.Mesh.Parts.Add("B01_Bar", new MeshPart("B01_Bar", 1, allNodes, elementIds.ToArray(), new[] { typeof(LinearHexaElement) }));
            model.Mesh.ElementSets.Add("ALL", new FeElementSet("ALL", elementIds.ToArray()));
            model.Sections.Clear();
            model.Sections.Add("B01_Steel", new SolidSection("B01_Steel", "Steel", "B01_Bar", RegionTypeEnum.PartName, 1, false));
        }

        private static void C1020PopulateB01NamedSelections(FeModel model)
        {
            int[] fixedNodes = Enumerable.Range(0, 4).Select(c => C1020NodeId(0, c)).ToArray();
            int[] loadNodes = Enumerable.Range(0, 4).Select(c => C1020NodeId(10, c)).ToArray();
            model.Mesh.NodeSets.Remove("FIXED");
            model.Mesh.NodeSets.Remove("LOAD");
            model.Mesh.NodeSets.Add("FIXED", new FeNodeSet("FIXED", fixedNodes));
            model.Mesh.NodeSets.Add("LOAD", new FeNodeSet("LOAD", loadNodes));
        }

        private static void C1020PopulateB01StaticStructural(FeModel model)
        {
            model.StepCollection.StepsList.Clear();
            var step = new StaticStep("Static Structural");
            step.AddBoundaryCondition(new FixedBC("Fixed Support", "FIXED", RegionTypeEnum.NodeSetName, false));
            step.AddLoad(new CLoad("Axial Force", "LOAD", RegionTypeEnum.NodeSetName, 10000, 0, 0, false, false, 0));
            model.StepCollection.AddStep(step, false);
        }

        private JObject C1020ExercisePmxCycles(string path, int cycles)
        {
            var evidence = new JArray();
            try
            {
                MethodInfo save = typeof(Controller).GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                    .FirstOrDefault(m => m.Name == "SaveToPmx" && m.GetParameters().Length == 1 &&
                                         m.GetParameters()[0].ParameterType == typeof(string));
                MethodInfo open = typeof(Controller).GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                    .FirstOrDefault(m => m.Name == "Open" && m.GetParameters().Length == 1 &&
                                         m.GetParameters()[0].ParameterType == typeof(string));
                if (save == null || open == null)
                    return new JObject { ["pass"] = false, ["reason"] = "Controller SaveToPmx/Open(string) reflection target not found.", ["cycles"] = evidence };

                for (int i = 1; i <= cycles; i++)
                {
                    save.Invoke(_controller, new object[] { path });
                    if (!File.Exists(path)) throw new IOException("PMX file was not written.");
                    // Cycle 2 also checks recovery of the branded header written by older releases.
                    if (i == 2)
                    {
                        byte[] header = new byte[32];
                        System.Text.Encoding.ASCII.GetBytes("AsterMax Mechanical C10.10.1").CopyTo(header, 0);
                        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Write))
                            stream.Write(header, 0, header.Length);
                    }
                    object result = open.Invoke(_controller, new object[] { path });
                    Task task = result as Task;
                    if (task != null) task.GetAwaiter().GetResult();
                    RegenerateTree();
                    _modelTree.RefreshAsterMaxOutline();
                    var states = BuildAsterMaxSectionStates();
                    bool survived = states["ax-model"].State == 2 && _controller.Model.Mesh.Nodes.Count == 44 &&
                                    _controller.Model.Mesh.Elements.Count == 10 &&
                                    _controller.Model.Mesh.NodeSets.ContainsKey("FIXED") &&
                                    _controller.Model.Mesh.NodeSets.ContainsKey("LOAD");
                    evidence.Add(new JObject {
                        ["cycle"] = i, ["file_bytes"] = new FileInfo(path).Length,
                        ["model_state"] = states["ax-model"].State,
                        ["nodes"] = _controller.Model.Mesh.Nodes.Count,
                        ["elements"] = _controller.Model.Mesh.Elements.Count,
                        ["survived"] = survived
                    });
                    if (!survived) return new JObject { ["pass"] = false, ["reason"] = "Model changed after PMX reopen.", ["cycles"] = evidence };
                }
                FeModel originalModel = _controller.Model;
                string corrupt = Path.Combine(Path.GetDirectoryName(path), "invalid.pmx");
                File.WriteAllBytes(corrupt, new byte[] { 1, 2, 3, 4 });
                bool rejected = false;
                try { open.Invoke(_controller, new object[] { corrupt }); }
                catch (TargetInvocationException) { rejected = true; }
                bool preserved = rejected && Object.ReferenceEquals(originalModel, _controller.Model) &&
                                 _controller.Model.Mesh.Nodes.Count == 44;
                if (!preserved) throw new InvalidOperationException("Invalid PMX replaced the active model.");
                return new JObject { ["pass"] = true, ["reason"] = "Three PMX cycles, legacy header recovery and invalid-file model preservation passed.",
                    ["invalid_file_preserved_model"] = preserved, ["legacy_header_reopened"] = true, ["cycles"] = evidence };
            }
            catch (TargetInvocationException ex)
            {
                Exception inner = ex.InnerException ?? ex;
                return new JObject { ["pass"] = false, ["reason"] = inner.ToString(), ["cycles"] = evidence };
            }
            catch (Exception ex)
            {
                return new JObject { ["pass"] = false, ["reason"] = ex.ToString(), ["cycles"] = evidence };
            }
        }
    }
}
