using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    public sealed class AsterMaxModelReadiness : UserControl
    {
        private readonly Controller _controller;
        private readonly Label _status;
        private readonly Timer _timer;

        public AsterMaxModelReadiness(Controller controller)
        {
            _controller = controller;
            Name = "ucAsterMaxModelReadiness";
            Dock = DockStyle.Bottom;
            Height = 28;
            BackColor = AsterMaxUiTheme.SurfaceRaised;
            Padding = new Padding(8, 3, 8, 3);
            _status = new Label { Dock = DockStyle.Fill, AutoEllipsis = true, TextAlign = System.Drawing.ContentAlignment.MiddleLeft, BackColor = AsterMaxUiTheme.SurfaceRaised, ForeColor = AsterMaxUiTheme.TextSecondary };
            Controls.Add(_status);
            _timer = new Timer { Interval = 1000 };
            _timer.Tick += (s, e) => RefreshReadiness();
            _timer.Start();
            Disposed += (s, e) => _timer.Dispose();
            RefreshReadiness();
        }

        public void RefreshReadiness()
        {
            object model = null;
            try { if (_controller != null) model = _controller.Model; } catch { }
            List<string> missing = new List<string>();
            Readiness cad = Probe(model, new[] { "Geometry", "GeometryParts", "Parts" });
            Readiness mesh = Probe(model, new[] { "Mesh", "Meshes", "FeMesh" });
            Readiness material = Probe(model, new[] { "Materials", "MaterialAssignments", "Sections" });
            Readiness bc = Probe(model, new[] { "BoundaryConditions", "Constraints", "Bcs" });
            Readiness load = Probe(model, new[] { "Loads", "Forces", "Pressures" });
            Readiness analysis = Probe(model, new[] { "Steps", "Analyses", "AnalysisSteps" });
            AddMissing(missing, "CAD", cad); AddMissing(missing, "MESH", mesh); AddMissing(missing, "MATERIAL", material); AddMissing(missing, "BC", bc); AddMissing(missing, "LOAD", load); AddMissing(missing, "ANALYSIS", analysis);
            bool ready = cad == Readiness.Present && mesh == Readiness.Present && material == Readiness.Present && bc == Readiness.Present && load == Readiness.Present && analysis == Readiness.Present;
            _status.Text = ready ? "MODEL READINESS · READY TO ATTEMPT SOLVE · NOT SOLVER VERIFIED" : "MODEL READINESS · BLOCKED/UNKNOWN · " + String.Join(" · ", missing.ToArray()) + " · NOT SOLVER VERIFIED";
            _status.ForeColor = ready ? AsterMaxUiTheme.Success : AsterMaxUiTheme.Warning;
        }

        private static void AddMissing(List<string> list, string name, Readiness state)
        {
            if (state != Readiness.Present) list.Add(name + "=" + state.ToString().ToUpperInvariant());
        }

        private static Readiness Probe(object root, string[] names)
        {
            if (root == null) return Readiness.Missing;
            Type type = root.GetType();
            foreach (string name in names)
            {
                try
                {
                    PropertyInfo pi = type.GetProperty(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                    if (pi == null) continue;
                    object value = pi.GetValue(root, null);
                    if (value == null) return Readiness.Missing;
                    ICollection c = value as ICollection;
                    if (c != null) return c.Count > 0 ? Readiness.Present : Readiness.Missing;
                    PropertyInfo count = value.GetType().GetProperty("Count", BindingFlags.Public | BindingFlags.Instance);
                    if (count != null) { int n; object v = count.GetValue(value, null); if (v != null && Int32.TryParse(v.ToString(), out n)) return n > 0 ? Readiness.Present : Readiness.Missing; }
                    return Readiness.Present;
                }
                catch { return Readiness.Unknown; }
            }
            return Readiness.Unknown;
        }

        private enum Readiness { Unknown, Missing, Present }
    }
}
