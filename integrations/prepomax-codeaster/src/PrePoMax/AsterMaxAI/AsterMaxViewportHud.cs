using System;
using System.Collections;
using System.Drawing;
using System.Reflection;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    public sealed class AsterMaxViewportHud : UserControl
    {
        private readonly Controller _controller;
        private readonly Label _mode;
        private readonly Label _cad;
        private readonly Label _mesh;
        private readonly Label _bc;
        private readonly Label _loads;
        private readonly Label _results;
        private readonly Label _view;
        private readonly Label _truth;
        private readonly Timer _timer;

        public AsterMaxViewportHud(Controller controller)
        {
            _controller = controller;
            Name = "ucAsterMaxViewportHud";
            Dock = DockStyle.Top;
            Height = 38;
            MinimumSize = new Size(0, 34);
            BackColor = AsterMaxUiTheme.SurfaceRaised;
            Padding = new Padding(8, 5, 8, 4);

            FlowLayoutPanel row = new FlowLayoutPanel();
            row.Dock = DockStyle.Fill;
            row.WrapContents = false;
            row.AutoScroll = true;
            row.FlowDirection = FlowDirection.LeftToRight;
            row.BackColor = AsterMaxUiTheme.SurfaceRaised;
            row.Padding = new Padding(0);

            _mode = MakeChip("VIEWPORT · CAD/FEA", true, 126);
            _cad = MakeChip("■ CAD · UNKNOWN", false, 118);
            _mesh = MakeChip("△ MESH · UNKNOWN", false, 128);
            _bc = MakeChip("⟂ BC · UNKNOWN", false, 108);
            _loads = MakeChip("↓ LOADS · UNKNOWN", false, 124);
            _results = MakeChip("≋ RESULTS · NONE", false, 126);
            _view = MakeChip("VIEW · —", false, 120);
            _truth = MakeChip("OBSERVED ≠ VERIFIED", false, 150);
            _truth.ForeColor = AsterMaxUiTheme.Warning;

            row.Controls.Add(_mode);
            row.Controls.Add(_cad);
            row.Controls.Add(_mesh);
            row.Controls.Add(_bc);
            row.Controls.Add(_loads);
            row.Controls.Add(_results);
            row.Controls.Add(_view);
            row.Controls.Add(_truth);
            Controls.Add(row);

            _timer = new Timer();
            _timer.Interval = 1000;
            _timer.Tick += (s, e) => RefreshObservedState();
            _timer.Start();
            Disposed += (s, e) => _timer.Dispose();

            RefreshObservedState();
        }

        private static Label MakeChip(string text, bool accent, int width)
        {
            Label label = new Label();
            label.Width = width;
            label.Height = 26;
            label.Margin = new Padding(2, 0, 2, 0);
            label.Padding = new Padding(7, 5, 7, 3);
            label.AutoEllipsis = true;
            label.Text = text;
            label.TextAlign = ContentAlignment.MiddleLeft;
            label.BackColor = accent ? AsterMaxUiTheme.Surface : AsterMaxUiTheme.Background;
            label.ForeColor = accent ? AsterMaxUiTheme.AccentGlow : AsterMaxUiTheme.TextSecondary;
            label.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 7.8f, accent ? FontStyle.Bold : FontStyle.Regular);
            return label;
        }

        public void RefreshObservedState()
        {
            object model = null;
            object result = null;
            string view = "—";
            try { if (_controller != null) model = _controller.Model; } catch { }
            try { if (_controller != null) result = _controller.CurrentResult; } catch { }
            try { if (_controller != null) view = _controller.CurrentView.ToString(); } catch { }

            SetState(_cad, "■ CAD", model == null ? ObservedState.Missing : ObservedState.Present);
            SetState(_mesh, "△ MESH", ProbeAny(model, new[] { "Mesh", "Meshes", "FeMesh" }));
            SetState(_bc, "⟂ BC", ProbeAny(model, new[] { "BoundaryConditions", "Constraints", "Bcs" }));
            SetState(_loads, "↓ LOADS", ProbeAny(model, new[] { "Loads", "Forces", "Pressures" }));
            _results.Text = result == null ? "≋ RESULTS · NONE" : "≋ RESULTS · LOADED";
            _results.ForeColor = result == null ? AsterMaxUiTheme.TextSecondary : AsterMaxUiTheme.Success;
            _view.Text = "VIEW · " + view.ToUpperInvariant();
        }

        private static void SetState(Label label, string caption, ObservedState state)
        {
            string text = state == ObservedState.Present ? "PRESENT" : state == ObservedState.Missing ? "MISSING" : "UNKNOWN";
            label.Text = caption + " · " + text;
            label.ForeColor = state == ObservedState.Present ? AsterMaxUiTheme.Success :
                              state == ObservedState.Missing ? AsterMaxUiTheme.Danger :
                              AsterMaxUiTheme.TextSecondary;
        }

        private static ObservedState ProbeAny(object root, string[] names)
        {
            if (root == null) return ObservedState.Missing;
            Type type = root.GetType();
            foreach (string name in names)
            {
                try
                {
                    PropertyInfo pi = type.GetProperty(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                    if (pi == null) continue;
                    object value = pi.GetValue(root, null);
                    if (value == null) return ObservedState.Missing;
                    ICollection collection = value as ICollection;
                    if (collection != null) return collection.Count > 0 ? ObservedState.Present : ObservedState.Missing;
                    PropertyInfo countPi = value.GetType().GetProperty("Count", BindingFlags.Public | BindingFlags.Instance);
                    if (countPi != null)
                    {
                        object countValue = countPi.GetValue(value, null);
                        int count;
                        if (countValue != null && Int32.TryParse(countValue.ToString(), out count))
                            return count > 0 ? ObservedState.Present : ObservedState.Missing;
                    }
                    return ObservedState.Present;
                }
                catch { return ObservedState.Unknown; }
            }
            return ObservedState.Unknown;
        }

        private enum ObservedState { Unknown, Missing, Present }
    }
}
