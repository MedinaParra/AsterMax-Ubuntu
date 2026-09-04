using System;
using System.Collections;
using System.Drawing;
using System.Reflection;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    public sealed class AsterMaxEngineeringTree : UserControl
    {
        private readonly Controller _controller;
        private readonly TreeView _tree;
        private readonly Label _caption;
        private readonly Label _legend;
        private readonly Timer _timer;

        public AsterMaxEngineeringTree(Controller controller)
        {
            _controller = controller;
            Name = "ucAsterMaxEngineeringTree";
            Dock = DockStyle.Right;
            Width = 285;
            MinimumSize = new Size(235, 0);
            BackColor = Color.White;
            Padding = new Padding(0);

            Panel header = new Panel();
            header.Dock = DockStyle.Top;
            header.Height = 54;
            header.BackColor = AsterMaxUiTheme.SurfaceAlt;
            header.Padding = new Padding(12, 8, 8, 6);

            _caption = new Label();
            _caption.Dock = DockStyle.Top;
            _caption.Height = 23;
            _caption.Text = "Engineering Model";
            _caption.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 10.5f, FontStyle.Bold);
            _caption.ForeColor = AsterMaxUiTheme.TextPrimary;
            header.Controls.Add(_caption);

            Label subtitle = new Label();
            subtitle.Dock = DockStyle.Bottom;
            subtitle.Height = 18;
            subtitle.Text = "Observed state · evidence aware";
            subtitle.ForeColor = AsterMaxUiTheme.TextSecondary;
            subtitle.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.2f, FontStyle.Regular);
            header.Controls.Add(subtitle);

            _tree = new TreeView();
            _tree.Name = "tvAsterMaxEngineeringModel";
            _tree.Dock = DockStyle.Fill;
            _tree.BorderStyle = BorderStyle.None;
            _tree.BackColor = Color.White;
            _tree.ForeColor = AsterMaxUiTheme.TextPrimary;
            _tree.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9f, FontStyle.Regular);
            _tree.HideSelection = false;
            _tree.ShowLines = true;
            _tree.ShowPlusMinus = true;
            _tree.ShowRootLines = true;
            _tree.ItemHeight = 24;

            Panel footer = new Panel();
            footer.Dock = DockStyle.Bottom;
            footer.Height = 42;
            footer.BackColor = AsterMaxUiTheme.Surface;
            footer.Padding = new Padding(10, 5, 8, 5);
            _legend = new Label();
            _legend.Dock = DockStyle.Fill;
            _legend.Text = "● Present    ○ Missing    ? Unknown\r\n✓ Verified only from admitted solver evidence";
            _legend.ForeColor = AsterMaxUiTheme.TextSecondary;
            _legend.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 7.8f, FontStyle.Regular);
            footer.Controls.Add(_legend);

            Panel divider = new Panel();
            divider.Dock = DockStyle.Left;
            divider.Width = 1;
            divider.BackColor = AsterMaxUiTheme.Border;

            Controls.Add(_tree);
            Controls.Add(header);
            Controls.Add(footer);
            Controls.Add(divider);

            _timer = new Timer();
            _timer.Interval = 1500;
            _timer.Tick += (s, e) => RefreshTree();
            _timer.Start();
            Disposed += (s, e) => _timer.Dispose();

            RefreshTree();
        }

        public void RefreshTree()
        {
            object model = null;
            object result = null;
            try { if (_controller != null) model = _controller.Model; } catch { }
            try { if (_controller != null) result = _controller.CurrentResult; } catch { }

            _tree.BeginUpdate();
            try
            {
                _tree.Nodes.Clear();
                AddStage("Geometry", model == null ? State.Missing : State.Present,
                    model == null ? "No model loaded" : "Model object loaded",
                    new[] { "STEP / CAD provenance: separate evidence gate" });

                AddModelCollectionStage(model, "Mesh", new[] { "Mesh", "Meshes", "FeMesh" },
                    "Nodes / elements observed when exposed by model API");
                AddModelCollectionStage(model, "Materials", new[] { "Materials", "MaterialAssignments", "Sections" },
                    "Presence does not validate constitutive data");
                AddModelCollectionStage(model, "Boundary Conditions", new[] { "BoundaryConditions", "Constraints", "Bcs" },
                    "Presence does not prove constraint completeness");
                AddModelCollectionStage(model, "Loads", new[] { "Loads", "Forces", "Pressures" },
                    "Equilibrium remains a solver evidence gate");
                AddModelCollectionStage(model, "Analysis", new[] { "Steps", "AnalysisSteps", "Jobs" },
                    "Code_Aster solve state must be admitted independently");

                State resultState = result == null ? State.Missing : State.Present;
                string resultInfo = result == null ? "No result object loaded" : "Result object loaded";
                TreeNode resultsNode = AddStage("Results", resultState, resultInfo,
                    new[] { "Loaded ≠ solver verified" });
                if (result != null) TryAddCurrentField(resultsNode);

                foreach (TreeNode node in _tree.Nodes) node.Expand();
            }
            finally { _tree.EndUpdate(); }
        }

        private void AddModelCollectionStage(object model, string label, string[] probes, string note)
        {
            ProbeResult probe = ProbeAny(model, probes);
            AddStage(label, probe.State, probe.Detail, new[] { note });
        }

        private TreeNode AddStage(string label, State state, string detail, string[] notes)
        {
            string badge = state == State.Present ? "●" : state == State.Missing ? "○" : "?";
            TreeNode node = new TreeNode(badge + "  " + label);
            node.Name = "astermax:" + label;
            node.ForeColor = state == State.Present ? AsterMaxUiTheme.Success :
                             state == State.Missing ? Color.FromArgb(176, 70, 70) :
                             AsterMaxUiTheme.TextSecondary;
            TreeNode detailNode = new TreeNode(detail ?? "State unavailable");
            detailNode.ForeColor = AsterMaxUiTheme.TextSecondary;
            node.Nodes.Add(detailNode);
            if (notes != null)
                foreach (string note in notes)
                {
                    TreeNode n = new TreeNode(note);
                    n.ForeColor = AsterMaxUiTheme.TextSecondary;
                    node.Nodes.Add(n);
                }
            _tree.Nodes.Add(node);
            return node;
        }

        private void TryAddCurrentField(TreeNode resultsNode)
        {
            try
            {
                if (_controller == null || _controller.CurrentFieldData == null) return;
                string name = _controller.CurrentFieldData.Name;
                string component = _controller.CurrentFieldData.Component;
                TreeNode field = new TreeNode("Field: " + name + " / " + component);
                field.ForeColor = AsterMaxUiTheme.TextPrimary;
                resultsNode.Nodes.Add(field);
            }
            catch { }
        }

        private static ProbeResult ProbeAny(object root, string[] propertyNames)
        {
            if (root == null) return new ProbeResult(State.Missing, "No model loaded");
            Type type = root.GetType();
            foreach (string name in propertyNames)
            {
                try
                {
                    PropertyInfo pi = type.GetProperty(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                    if (pi == null) continue;
                    object value = pi.GetValue(root, null);
                    if (value == null) return new ProbeResult(State.Missing, name + ": empty");
                    ICollection collection = value as ICollection;
                    if (collection != null)
                        return new ProbeResult(collection.Count > 0 ? State.Present : State.Missing,
                            name + ": " + collection.Count + " item(s)");
                    PropertyInfo countPi = value.GetType().GetProperty("Count", BindingFlags.Public | BindingFlags.Instance);
                    if (countPi != null)
                    {
                        object countValue = countPi.GetValue(value, null);
                        int count;
                        if (countValue != null && Int32.TryParse(countValue.ToString(), out count))
                            return new ProbeResult(count > 0 ? State.Present : State.Missing,
                                name + ": " + count + " item(s)");
                    }
                    return new ProbeResult(State.Present, name + ": present");
                }
                catch (Exception ex)
                {
                    return new ProbeResult(State.Unknown, name + ": probe error " + ex.GetType().Name);
                }
            }
            return new ProbeResult(State.Unknown, "Model API does not expose a recognized collection");
        }

        private struct ProbeResult
        {
            public readonly State State;
            public readonly string Detail;
            public ProbeResult(State state, string detail) { State = state; Detail = detail; }
        }

        private enum State { Unknown, Missing, Present }
    }
}
