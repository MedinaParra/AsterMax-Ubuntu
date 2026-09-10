using System;
using System.Collections;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Reflection;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    public sealed class AsterMaxWorkflowStrip : ToolStrip
    {
        private readonly Controller _controller;
        private readonly ToolStripDropDownButton _statusButton;
        private readonly Timer _refreshTimer;

        public AsterMaxWorkflowStrip(Controller controller)
        {
            _controller = controller;
            Name = "tsAsterMaxWorkflow";
            GripStyle = ToolStripGripStyle.Hidden;
            Dock = DockStyle.Top;
            BackColor = AsterMaxUiTheme.Surface;
            ForeColor = AsterMaxUiTheme.TextPrimary;
            Padding = new Padding(8, 5, 8, 5);
            AutoSize = true;
            RenderMode = ToolStripRenderMode.System;

            Items.Add(MakeStage("CAD / STEP", StageIcon.Geometry));
            Items.Add(MakeStage("Mesh", StageIcon.Mesh));
            Items.Add(MakeStage("Material", StageIcon.Material));
            Items.Add(MakeStage("BC", StageIcon.Boundary));
            Items.Add(MakeStage("Load", StageIcon.Load));
            Items.Add(MakeStage("Analysis", StageIcon.Analysis));
            Items.Add(MakeStage("Solve", StageIcon.Solve));
            Items.Add(MakeStage("Results", StageIcon.Results));
            Items.Add(new ToolStripSeparator());

            ToolStripLabel units = new ToolStripLabel("mm · N · MPa");
            units.Name = "tslAsterMaxUnits";
            units.ForeColor = AsterMaxUiTheme.Accent;
            units.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.5f, FontStyle.Bold);
            units.ToolTipText = "AsterMax engineering unit contract";
            Items.Add(units);
            Items.Add(new ToolStripSeparator());

            _statusButton = new ToolStripDropDownButton("Model status");
            _statusButton.Name = "tsddbAsterMaxModelStatus";
            _statusButton.Image = CreateStatusIcon(AsterMaxUiTheme.TextSecondary, 18);
            _statusButton.ImageScaling = ToolStripItemImageScaling.None;
            _statusButton.DisplayStyle = ToolStripItemDisplayStyle.ImageAndText;
            _statusButton.ForeColor = AsterMaxUiTheme.TextPrimary;
            _statusButton.ToolTipText = "Observed engineering state. Presence is not solver verification.";
            _statusButton.DropDownOpening += (s, e) => RefreshEngineeringState();
            Items.Add(_statusButton);

            ToolStripLabel ai = new ToolStripLabel("AI · evidence aware");
            ai.ForeColor = AsterMaxUiTheme.AccentGlow;
            ai.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.3f, FontStyle.Bold);
            Items.Add(new ToolStripSeparator());
            Items.Add(ai);

            _refreshTimer = new Timer();
            _refreshTimer.Interval = 1500;
            _refreshTimer.Tick += (s, e) => RefreshEngineeringState();
            _refreshTimer.Start();
            Disposed += (s, e) => _refreshTimer.Dispose();

            RefreshEngineeringState();
        }

        private static ToolStripButton MakeStage(string text, StageIcon icon)
        {
            ToolStripButton button = new ToolStripButton();
            button.Name = "tsbAsterMax" + text.Replace(" ", "").Replace("/", "");
            button.Text = text;
            button.ForeColor = AsterMaxUiTheme.TextPrimary;
            button.BackColor = AsterMaxUiTheme.Surface;
            button.DisplayStyle = ToolStripItemDisplayStyle.ImageAndText;
            button.Image = CreateStageIcon(icon, 20);
            button.ImageScaling = ToolStripItemImageScaling.None;
            button.Margin = new Padding(2, 1, 2, 1);
            button.Padding = new Padding(5, 3, 5, 3);
            button.ToolTipText = "Engineering workflow: " + text;
            button.Tag = "astermax-workflow-stage";
            return button;
        }

        private void RefreshEngineeringState()
        {
            EngineeringState geometry = EngineeringState.Unknown;
            EngineeringState mesh = EngineeringState.Unknown;
            EngineeringState material = EngineeringState.Unknown;
            EngineeringState bc = EngineeringState.Unknown;
            EngineeringState load = EngineeringState.Unknown;
            EngineeringState solve = EngineeringState.Unknown;
            EngineeringState results = EngineeringState.Unknown;

            object model = null;
            try { model = _controller == null ? null : _controller.Model; } catch { }

            geometry = model == null ? EngineeringState.Missing : EngineeringState.Present;
            if (model != null)
            {
                mesh = ProbeAny(model, new[] { "Mesh", "Meshes", "FeMesh" });
                material = ProbeAny(model, new[] { "Materials", "MaterialAssignments", "Sections" });
                bc = ProbeAny(model, new[] { "BoundaryConditions", "Constraints", "Bcs" });
                load = ProbeAny(model, new[] { "Loads", "Forces", "Pressures" });
                solve = ProbeAny(model, new[] { "Steps", "AnalysisSteps", "Jobs" });
            }

            try
            {
                if (_controller != null && _controller.CurrentResult != null)
                {
                    solve = EngineeringState.Present;
                    results = EngineeringState.Present;
                }
                else results = EngineeringState.Missing;
            }
            catch { }

            _statusButton.DropDownItems.Clear();
            AddStateItem("Geometry / STEP", geometry, "Model presence only; STEP provenance must be qualified separately.");
            AddStateItem("Mesh", mesh, "Observed from model collections when exposed by the controller.");
            AddStateItem("Material", material, "Observed assignment presence; constitutive validity is not inferred.");
            AddStateItem("Boundary conditions", bc, "Observed presence only; completeness is not inferred.");
            AddStateItem("Loads", load, "Observed presence only; equilibrium is a separate evidence gate.");
            AddStateItem("Analysis / solve", solve, "Presence/result-loaded state; does not claim a verified solve.");
            AddStateItem("Results", results, "Result object loaded; solver verification requires evidence bundle admission.");
            _statusButton.DropDownItems.Add(new ToolStripSeparator());
            ToolStripMenuItem truth = new ToolStripMenuItem("Evidence policy: observed ≠ solver verified");
            truth.Enabled = false;
            truth.BackColor = AsterMaxUiTheme.SurfaceAlt;
            truth.ForeColor = AsterMaxUiTheme.TextSecondary;
            _statusButton.DropDownItems.Add(truth);

            bool hasModel = geometry == EngineeringState.Present;
            bool hasResults = results == EngineeringState.Present;
            Color stateColor = hasResults ? AsterMaxUiTheme.Success : hasModel ? AsterMaxUiTheme.Warning : AsterMaxUiTheme.TextSecondary;
            _statusButton.Image = CreateStatusIcon(stateColor, 18);
            _statusButton.Text = hasResults ? "Results loaded" : hasModel ? "Model loaded" : "No model";
        }

        private void AddStateItem(string name, EngineeringState state, string tooltip)
        {
            string label = state == EngineeringState.Present ? "Present" : state == EngineeringState.Missing ? "Missing" : "Unknown";
            Color color = state == EngineeringState.Present ? AsterMaxUiTheme.Success : state == EngineeringState.Missing ? AsterMaxUiTheme.Danger : AsterMaxUiTheme.TextSecondary;
            ToolStripMenuItem item = new ToolStripMenuItem(name + "   ·   " + label);
            item.Enabled = false;
            item.BackColor = AsterMaxUiTheme.SurfaceAlt;
            item.ForeColor = AsterMaxUiTheme.TextPrimary;
            item.Image = CreateStatusIcon(color, 14);
            item.ImageScaling = ToolStripItemImageScaling.None;
            item.ToolTipText = tooltip;
            _statusButton.DropDownItems.Add(item);
        }

        private static EngineeringState ProbeAny(object root, string[] propertyNames)
        {
            if (root == null) return EngineeringState.Missing;
            Type type = root.GetType();
            foreach (string name in propertyNames)
            {
                try
                {
                    PropertyInfo pi = type.GetProperty(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                    if (pi == null) continue;
                    object value = pi.GetValue(root, null);
                    if (value == null) return EngineeringState.Missing;
                    ICollection collection = value as ICollection;
                    if (collection != null) return collection.Count > 0 ? EngineeringState.Present : EngineeringState.Missing;
                    PropertyInfo countPi = value.GetType().GetProperty("Count", BindingFlags.Public | BindingFlags.Instance);
                    if (countPi != null)
                    {
                        object countValue = countPi.GetValue(value, null);
                        int count;
                        if (countValue != null && Int32.TryParse(countValue.ToString(), out count))
                            return count > 0 ? EngineeringState.Present : EngineeringState.Missing;
                    }
                    return EngineeringState.Present;
                }
                catch { return EngineeringState.Unknown; }
            }
            return EngineeringState.Unknown;
        }

        private enum EngineeringState { Unknown, Missing, Present }
        private enum StageIcon { Geometry, Mesh, Material, Boundary, Load, Analysis, Solve, Results }

        private static Bitmap CreateStatusIcon(Color color, int size)
        {
            Bitmap bmp = new Bitmap(size, size);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.Transparent);
                using (Brush b = new SolidBrush(color))
                {
                    Rectangle r = new Rectangle(2, 2, size - 5, size - 5);
                    g.FillEllipse(b, r);
                }
            }
            return bmp;
        }

        private static Bitmap CreateStageIcon(StageIcon stage, int size)
        {
            Bitmap bmp = new Bitmap(size, size);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.Transparent);
                using (Pen p = new Pen(AsterMaxUiTheme.Accent, 1.7f))
                using (Brush b = new SolidBrush(AsterMaxUiTheme.AccentGlow))
                using (Brush soft = new SolidBrush(Color.FromArgb(38, AsterMaxUiTheme.Accent)))
                {
                    switch (stage)
                    {
                        case StageIcon.Geometry:
                            g.FillRectangle(soft, 3, 5, 12, 10); g.DrawRectangle(p, 3, 5, 12, 10);
                            g.DrawLine(p, 3, 5, 7, 2); g.DrawLine(p, 15, 5, 11, 2); g.DrawLine(p, 7, 2, 11, 2); break;
                        case StageIcon.Mesh:
                            for (int x = 4; x <= 16; x += 6) g.DrawLine(p, x, 3, x, 17);
                            for (int y = 4; y <= 16; y += 6) g.DrawLine(p, 3, y, 17, y);
                            g.DrawLine(p, 3, 3, 17, 17); g.DrawLine(p, 17, 3, 3, 17); break;
                        case StageIcon.Material:
                            g.FillEllipse(soft, 3, 3, 14, 14); g.DrawEllipse(p, 3, 3, 14, 14);
                            g.DrawLine(p, 6, 10, 14, 10); g.DrawLine(p, 10, 6, 10, 14); break;
                        case StageIcon.Boundary:
                            g.DrawLine(p, 5, 3, 5, 17); g.DrawLine(p, 5, 4, 16, 4); g.DrawLine(p, 5, 16, 16, 16);
                            for (int y = 6; y <= 14; y += 4) g.DrawLine(p, 2, y, 5, y - 2); break;
                        case StageIcon.Load:
                            g.DrawLine(p, 10, 2, 10, 15); g.DrawLine(p, 10, 15, 6, 11); g.DrawLine(p, 10, 15, 14, 11); g.FillEllipse(b, 8, 1, 4, 4); break;
                        case StageIcon.Analysis:
                            g.DrawRectangle(p, 3, 3, 14, 14); g.DrawLine(p, 5, 13, 9, 8); g.DrawLine(p, 9, 8, 12, 11); g.DrawLine(p, 12, 11, 16, 5); break;
                        case StageIcon.Solve:
                            PointF[] tri = { new PointF(6, 3), new PointF(16, 10), new PointF(6, 17) }; g.FillPolygon(b, tri); break;
                        case StageIcon.Results:
                            g.DrawRectangle(p, 3, 3, 14, 14); g.FillRectangle(soft, 5, 11, 2, 4); g.FillRectangle(soft, 9, 8, 2, 7); g.FillRectangle(soft, 13, 5, 2, 10); break;
                    }
                }
            }
            return bmp;
        }
    }
}
