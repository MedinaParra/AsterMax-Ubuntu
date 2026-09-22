using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UserControls;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private void C1020AttachCrossCuttingToSession(string directory)
        {
            JObject cross = C1020RunCrossCuttingChecks(directory);
            string path = Path.Combine(directory, "workflow-conformance-session.json");
            JObject session = File.Exists(path) ? JObject.Parse(File.ReadAllText(path)) : new JObject();
            session["cross_cutting"] = cross;
            session["historical_pending_closed"] = false;
            session["closure_note"] = "The application does not close the historical audit finding itself. Closure requires the uploaded CI artifact to be reviewed after this process exits.";
            File.WriteAllText(path, session.ToString(Formatting.Indented));
        }

        private JObject C1020RunCrossCuttingChecks(string directory)
        {
            var checks = new JArray();
            Action<string,string,string,JToken> add = (id,status,reason,evidence) => checks.Add(new JObject {
                ["id"] = id, ["status"] = status, ["reason"] = reason, ["evidence"] = evidence
            });

            string pmxPath = Path.Combine(directory, "pmx-save-reopen.json");
            if (File.Exists(pmxPath))
            {
                JObject pmx = JObject.Parse(File.ReadAllText(pmxPath));
                bool pass = (bool?)pmx["pass"] == true;
                int cycles = pmx["cycles"] is JArray ? ((JArray)pmx["cycles"]).Count : 0;
                add("pmx_save_reopen_survives", pass ? "PASS" : "FAIL",
                    pass ? "A real PMX save/reopen preserved the configured model." : (string)pmx["reason"],
                    new JObject { ["file"] = Path.GetFileName(pmxPath), ["cycles"] = cycles });
                add("repeated_pmx_save_reopen", pass && cycles >= 3 ? "PASS" : "FAIL",
                    pass && cycles >= 3 ? "Three consecutive save/reopen cycles survived." : "Fewer than three successful PMX cycles were recorded.",
                    new JObject { ["file"] = Path.GetFileName(pmxPath), ["cycles"] = cycles });
            }
            else
            {
                add("pmx_save_reopen_survives", "NOT_EXERCISED", "PMX evidence file is absent.", null);
                add("repeated_pmx_save_reopen", "NOT_EXERCISED", "PMX evidence file is absent.", null);
            }

            try
            {
                string solveWorkspace = _asterMaxSolveTransaction == null ? null : _asterMaxSolveTransaction.Workspace;
                string txPath = String.IsNullOrWhiteSpace(solveWorkspace) ? null :
                    Path.Combine(solveWorkspace, "ASTERMAX_SOLVE_TRANSACTION.json");
                if (String.IsNullOrWhiteSpace(txPath) || !File.Exists(txPath))
                {
                    add("cload_semantics", "NOT_EXERCISED",
                        "Solve transaction manifest is unavailable; nodal-load semantics could not be verified.", null);
                }
                else
                {
                    JObject tx = JObject.Parse(File.ReadAllText(txPath));
                    JObject manifest = tx["native_exporter_manifest"] as JObject;
                    string semantics = manifest == null ? null : (string)manifest["load_semantics"];
                    int loadNodes = manifest == null ? 0 : ((int?)manifest["load_nodes"] ?? 0);
                    double fxPerNode = manifest == null ? Double.NaN : ((double?)manifest["fx_per_node_n"] ?? Double.NaN);
                    double fxTotal = manifest == null ? Double.NaN : ((double?)manifest["fx_total_n"] ?? Double.NaN);
                    bool pass = String.Equals(semantics, "PER_NODE_CLOAD", StringComparison.Ordinal) &&
                                loadNodes == 4 && Math.Abs(fxPerNode - 2500.0) < 1e-9 &&
                                Math.Abs(fxTotal - 10000.0) < 1e-9;
                    add("cload_semantics", pass ? "PASS" : "FAIL",
                        pass ? "Native CLoad semantics preserved: 2500 N per node across 4 LOAD nodes = 10000 N total." :
                        "Unexpected Code_Aster load semantics or B01 force provenance.",
                        new JObject {
                            ["transaction_manifest"] = Path.GetFileName(txPath),
                            ["load_semantics"] = semantics,
                            ["load_nodes"] = loadNodes,
                            ["fx_per_node_n"] = fxPerNode,
                            ["fx_total_n"] = fxTotal
                        });
                }
            }
            catch (Exception ex)
            {
                add("cload_semantics", "FAIL", ex.Message, null);
            }

            try
            {
                string prefix = Path.Combine(directory, "cross-ribbon");
                AuditAsterMaxButtons(prefix);
                var ribbon = Controls["asterMaxRibbon"] as TabControl;
                var visited = new JArray();
                if (ribbon == null) throw new InvalidOperationException("AsterMax ribbon missing.");
                foreach (TabPage page in ribbon.TabPages)
                {
                    ribbon.SelectedTab = page;
                    Application.DoEvents();
                    foreach (Button button in AxButtons(page))
                    {
                        button.Select();
                        Application.DoEvents();
                        visited.Add(new JObject { ["tab"] = page.Text, ["command"] = button.Text,
                            ["enabled"] = button.Enabled, ["action_bound"] = button.Tag is Action });
                    }
                }
                File.WriteAllText(Path.Combine(directory, "ribbon-command-walk.json"), visited.ToString(Formatting.Indented));
                add("ribbon_command_walk", visited.Count > 0 ? "PASS" : "FAIL",
                    "Every ribbon command control was visited and its binding recorded. Editing commands were not invoked; this is traversal evidence, not a functional-success claim.",
                    new JObject { ["commands_visited"] = visited.Count, ["functional_execution_claim"] = false,
                        ["walk"] = "ribbon-command-walk.json", ["wiring_audit"] = "cross-ribbon.buttons.json" });
            }
            catch (Exception ex)
            {
                add("ribbon_command_walk", "FAIL", ex.Message, null);
            }

            try
            {
                var visited = new JArray();
                if (MainMenuStrip == null) throw new InvalidOperationException("MainMenuStrip is missing.");
                foreach (ToolStripItem item in MainMenuStrip.Items) C1020VisitMenuItem(item, visited, "");
                File.WriteAllText(Path.Combine(directory, "menu-command-walk.json"), visited.ToString(Formatting.Indented));
                add("menu_command_walk", visited.Count > 0 ? "PASS" : "FAIL",
                    "Every reachable menu item was selected/opened and recorded without invoking destructive commands. This proves command-surface traversal only.",
                    new JObject { ["commands_visited"] = visited.Count, ["functional_execution_claim"] = false,
                        ["walk"] = "menu-command-walk.json" });
            }
            catch (Exception ex)
            {
                add("menu_command_walk", "FAIL", ex.Message, null);
            }

            try
            {
                JObject multi = C1020ExerciseNativeTreeMultiselection();
                File.WriteAllText(Path.Combine(directory, "tree-multiselection.json"), multi.ToString(Formatting.Indented));
                add("tree_multiselection", (bool)multi["pass"] ? "PASS" : "FAIL",
                    (string)multi["reason"], new JObject { ["file"] = "tree-multiselection.json", ["selected_count"] = multi["selected_count"] });
            }
            catch (Exception ex)
            {
                add("tree_multiselection", "FAIL", ex.Message, null);
            }

            try
            {
                int deviceDpiBefore = DeviceDpi;
                int deviceDpiAfter = deviceDpiBefore;
                string before = Path.Combine(directory, "dpi-before.png");
                C1020CaptureWindow(before);
                Rectangle originalBounds = Bounds;
                bool transitionObserved = false;
                int screensVisited = 0;
                try
                {
                    foreach (Screen screen in Screen.AllScreens)
                    {
                        screensVisited++;
                        Rectangle target = screen.WorkingArea;
                        StartPosition = FormStartPosition.Manual;
                        Location = new Point(target.Left + Math.Max(0, Math.Min(32, target.Width - Width)),
                                             target.Top + Math.Max(0, Math.Min(32, target.Height - Height)));
                        Application.DoEvents();
                        deviceDpiAfter = DeviceDpi;
                        if (deviceDpiAfter != deviceDpiBefore)
                        {
                            transitionObserved = true;
                            C1020CaptureWindow(Path.Combine(directory, "dpi-real-transition.png"));
                            break;
                        }
                    }
                }
                finally
                {
                    Bounds = originalBounds;
                    Application.DoEvents();
                }
                var dpi = new JObject {
                    ["device_dpi_before"] = deviceDpiBefore,
                    ["device_dpi_after"] = deviceDpiAfter,
                    ["screens_visited"] = screensVisited,
                    ["live_form_scale_mutation_used"] = false,
                    ["system_dpi_transition_observed"] = transitionObserved,
                    ["screenshots"] = new JArray(Path.GetFileName(before))
                };
                File.WriteAllText(Path.Combine(directory, "dpi-change.json"), dpi.ToString(Formatting.Indented));
                string status = transitionObserved ? "PASS" : "NOT_EXERCISED";
                add("dpi_change", status,
                    status == "PASS" ? "A real DeviceDpi transition was observed while moving the native window between physical/virtual displays." :
                    "No different-DPI display was available. The audit deliberately does not scale the live VTK/WinForms window synthetically.",
                    new JObject { ["file"] = "dpi-change.json", ["system_dpi_transition_observed"] = transitionObserved,
                                  ["screens_visited"] = screensVisited, ["synthetic_dpi_claim"] = false });
            }
            catch (Exception ex)
            {
                add("dpi_change", "FAIL", ex.Message, null);
            }

            bool anyFail = checks.Any(x => String.Equals((string)x["status"], "FAIL", StringComparison.Ordinal));
            bool anyNotExercised = checks.Any(x => String.Equals((string)x["status"], "NOT_EXERCISED", StringComparison.Ordinal));
            return new JObject {
                ["checks"] = checks,
                ["no_failures"] = !anyFail,
                ["fully_exercised"] = !anyFail && !anyNotExercised,
                ["rule"] = "NOT_EXERCISED is explicit and is never converted to PASS. Traversal evidence does not claim command execution success."
            };
        }

        private void C1020VisitMenuItem(ToolStripItem item, JArray visited, string parent)
        {
            if (item == null || !item.Available) return;
            string path = String.IsNullOrEmpty(parent) ? item.Text : parent + " > " + item.Text;
            item.Select();
            Application.DoEvents();
            var menu = item as ToolStripMenuItem;
            visited.Add(new JObject { ["path"] = path, ["enabled"] = item.Enabled,
                ["has_children"] = menu != null && menu.DropDownItems.Count > 0 });
            if (menu == null || menu.DropDownItems.Count == 0) return;
            menu.ShowDropDown();
            Application.DoEvents();
            foreach (ToolStripItem child in menu.DropDownItems) C1020VisitMenuItem(child, visited, path);
            menu.HideDropDown();
        }

        private JObject C1020ExerciseNativeTreeMultiselection()
        {
            FieldInfo field = typeof(ModelTree).GetField("cltvModel", BindingFlags.Instance | BindingFlags.NonPublic);
            if (field == null) return new JObject { ["pass"] = false, ["reason"] = "cltvModel field not found.", ["selected_count"] = 0 };
            object tree = field.GetValue(_modelTree);
            if (tree == null) return new JObject { ["pass"] = false, ["reason"] = "cltvModel is null.", ["selected_count"] = 0 };
            PropertyInfo nodesProperty = tree.GetType().GetProperty("Nodes");
            PropertyInfo selectedProperty = tree.GetType().GetProperty("SelectedNodes");
            if (nodesProperty == null || selectedProperty == null)
                return new JObject { ["pass"] = false, ["reason"] = "Native tree selection properties are unavailable.", ["selected_count"] = 0 };
            var roots = nodesProperty.GetValue(tree, null) as TreeNodeCollection;
            object selected = selectedProperty.GetValue(tree, null);
            if (roots == null || selected == null)
                return new JObject { ["pass"] = false, ["reason"] = "Native tree selection collections are unavailable.", ["selected_count"] = 0 };
            var candidates = new List<TreeNode>();
            C1020CollectTreeNodes(roots, candidates);
            candidates = candidates.Where(n => n.Tag != null).Take(2).ToList();
            if (candidates.Count < 2)
                return new JObject { ["pass"] = false, ["reason"] = "Fewer than two selectable native model nodes exist.", ["selected_count"] = candidates.Count };
            MethodInfo clear = selected.GetType().GetMethod("Clear", Type.EmptyTypes);
            MethodInfo add = selected.GetType().GetMethods().FirstOrDefault(m => m.Name == "Add" && m.GetParameters().Length == 1);
            PropertyInfo count = selected.GetType().GetProperty("Count");
            if (clear == null || add == null || count == null)
                return new JObject { ["pass"] = false, ["reason"] = "SelectedNodes mutation API is unavailable.", ["selected_count"] = 0 };
            clear.Invoke(selected, null);
            add.Invoke(selected, new object[] { candidates[0] });
            add.Invoke(selected, new object[] { candidates[1] });
            int selectedCount = Convert.ToInt32(count.GetValue(selected, null));
            return new JObject { ["pass"] = selectedCount >= 2,
                ["reason"] = selectedCount >= 2 ? "Two native model-tree nodes were selected concurrently." : "Native multiselection did not retain two nodes.",
                ["selected_count"] = selectedCount,
                ["nodes"] = new JArray(candidates.Select(n => n.Text)) };
        }

        private static void C1020CollectTreeNodes(TreeNodeCollection nodes, List<TreeNode> output)
        {
            foreach (TreeNode node in nodes)
            {
                output.Add(node);
                C1020CollectTreeNodes(node.Nodes, output);
            }
        }

        private void C1020CaptureWindow(string path)
        {
            using (var bitmap = new Bitmap(Math.Max(1, Width), Math.Max(1, Height)))
            {
                DrawToBitmap(bitmap, new Rectangle(0, 0, bitmap.Width, bitmap.Height));
                bitmap.Save(path, ImageFormat.Png);
            }
        }
    }
}
