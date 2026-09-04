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
        private readonly ComboBox _analysisType;
        private readonly Label _analysisHint;
        private readonly Timer _timer;

        public AsterMaxEngineeringTree(Controller controller)
        {
            _controller = controller;
            Name = "ucAsterMaxEngineeringTree";
            Dock = DockStyle.Right;
            Width = 315;
            MinimumSize = new Size(270, 0);
            BackColor = AsterMaxUiTheme.Background;
            Padding = new Padding(0);

            Panel header = new Panel();
            header.Dock = DockStyle.Top;
            header.Height = 126;
            header.BackColor = AsterMaxUiTheme.SurfaceAlt;
            header.Padding = new Padding(12, 8, 10, 8);

            _caption = new Label();
            _caption.Dock = DockStyle.Top;
            _caption.Height = 24;
            _caption.Text = "ASTERMAX ENGINEERING";
            _caption.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 10.5f, FontStyle.Bold);
            _caption.ForeColor = AsterMaxUiTheme.TextPrimary;
            header.Controls.Add(_caption);

            Label subtitle = new Label();
            subtitle.Dock = DockStyle.Top;
            subtitle.Height = 18;
            subtitle.Text = "Model tree · evidence aware";
            subtitle.ForeColor = AsterMaxUiTheme.TextSecondary;
            subtitle.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.2f, FontStyle.Regular);
            header.Controls.Add(subtitle);

            Label analysisCaption = new Label();
            analysisCaption.Dock = DockStyle.Top;
            analysisCaption.Height = 20;
            analysisCaption.Text = "ANALYSIS SETUP";
            analysisCaption.ForeColor = AsterMaxUiTheme.Accent;
            analysisCaption.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.2f, FontStyle.Bold);
            header.Controls.Add(analysisCaption);

            _analysisType = new ComboBox();
            _analysisType.Name = "cmbAsterMaxAnalysisType";
            _analysisType.Dock = DockStyle.Top;
            _analysisType.Height = 26;
            _analysisType.DropDownStyle = ComboBoxStyle.DropDownList;
            _analysisType.BackColor = AsterMaxUiTheme.SurfaceRaised;
            _analysisType.ForeColor = AsterMaxUiTheme.TextPrimary;
            _analysisType.FlatStyle = FlatStyle.Flat;
            _analysisType.Items.Add("Static Structural · qualified path");
            _analysisType.Items.Add("Modal · not qualified");
            _analysisType.Items.Add("Linear Buckling · not qualified");
            _analysisType.Items.Add("Thermal · not qualified");
            _analysisType.SelectedIndex = 0;
            _analysisType.SelectedIndexChanged += (s, e) => RefreshAnalysisHint();
            header.Controls.Add(_analysisType);

            _analysisHint = new Label();
            _analysisHint.Dock = DockStyle.Fill;
            _analysisHint.Padding = new Padding(0, 5, 0, 0);
            _analysisHint.ForeColor = AsterMaxUiTheme.TextSecondary;
            _analysisHint.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 7.7f, FontStyle.Regular);
            header.Controls.Add(_analysisHint);

            _tree = new TreeView();
            _tree.Name = "tvAsterMaxEngineeringModel";
            _tree.Dock = DockStyle.Fill;
            _tree.BorderStyle = BorderStyle.None;
            _tree.BackColor = AsterMaxUiTheme.Background;
            _tree.ForeColor = AsterMaxUiTheme.TextPrimary;
            _tree.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9f, FontStyle.Regular);
            _tree.HideSelection = false;
            _tree.ShowLines = true;
            _tree.ShowPlusMinus = true;
            _tree.ShowRootLines = true;
            _tree.LineColor = AsterMaxUiTheme.Border;
            _tree.ItemHeight = 25;

            Panel footer = new Panel();
            footer.Dock = DockStyle.Bottom;
            footer.Height = 47;
            footer.BackColor = AsterMaxUiTheme.Surface;
            footer.Padding = new Padding(10, 5, 8, 5);
            _legend = new Label();
            _legend.Dock = DockStyle.Fill;
            _legend.Text = "● Present    ○ Missing    ? Unknown\r\nAI + GUI observation never upgrades evidence to verified";
            _legend.ForeColor = AsterMaxUiTheme.TextSecondary;
            _legend.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 7.7f, FontStyle.Regular);
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

            RefreshAnalysisHint();
            RefreshTree();
        }

        private void RefreshAnalysisHint()
        {
            if (_analysisType.SelectedIndex == 0)
            {
                _analysisHint.Text = "Code_Aster static structural path available · mm-N-MPa";
                _analysisHint.ForeColor = AsterMaxUiTheme.Success;
            }
            else
            {
                _analysisHint.Text = "UI selection only · solver binding and qualification pending";
                _analysisHint.ForeColor = AsterMaxUiTheme.Warning;
            }
        }

        public string SelectedAnalysisType
        {
            get { return _analysisType.SelectedItem == null ? "Unknown" : _analysisType.SelectedItem.ToString(); }
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
                AddStage("Geometry / STEP", model == null ? State.Missing : State.Present,
                    model == null ? "No CAD model loaded" : "CAD/model object loaded",
                    new[] { "STEP scale and provenance require independent evidence" });

                AddModelCollectionStage(model, "Mesh", new[] { "Mesh", "Meshes", "FeMesh" },
                    "Nodes / elements observed when exposed by model API");
                AddModelCollectionStage(model, "Materials", new[] { "Materials", "MaterialAssignments", "Sections" },
                    "Presence does not validate constitutive data");
                AddModelCollectionStage(model, "Boundary Conditions", new[] { "BoundaryConditions", "Constraints", "Bcs" },
                    "Presence does not prove constraint completeness");
                AddModelCollectionStage(model, "Loads", new[] { "Loads", "Forces", "Pressures" },
                    "Equilibrium remains a solver evidence gate");

                ProbeResult analysisProbe = ProbeAny(model, new[] { "Steps", "AnalysisSteps", "Jobs" });
                TreeNode analysis = AddStage("Analysis Setup", analysisProbe.State, analysisProbe.Detail,
                    new[] { "Selected UI mode: " + SelectedAnalysisType,
                            _analysisType.SelectedIndex == 0 ? "Static structural path available" : "Selected mode not yet solver-qualified" });
                analysis.ImageIndex = -1;

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
                             state == State.Missing ? AsterMaxUiTheme.Danger :
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
                field.ForeColor = AsterMaxUiTheme.Accent;
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
