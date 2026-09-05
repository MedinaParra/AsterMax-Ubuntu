using System;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Reflection;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    // C8.56: projects observed FE anchors through the real pinned VTK renderer.
    // Position can be FE-anchor qualified; exact CAD centroid, load direction and solver state are NOT inferred.
    public sealed class AsterMaxViewportProjectionOverlay : UserControl
    {
        private readonly Controller _controller;
        private readonly Control _vtkControl;
        private readonly object _renderer;
        private readonly Timer _timer;
        private readonly List<ProjectedGlyph> _glyphs;
        private string _status;

        private AsterMaxViewportProjectionOverlay(Controller controller, Control vtkControl, object renderer)
        {
            _controller = controller;
            _vtkControl = vtkControl;
            _renderer = renderer;
            _glyphs = new List<ProjectedGlyph>();
            _status = "VTK PROJECTION READY · MODEL ANCHORS 0";

            Name = "ucAsterMaxViewportProjectionOverlay";
            Dock = DockStyle.Fill;
            BackColor = Color.Transparent;
            TabStop = false;
            Enabled = false; // never steals picking/rotation/zoom input from the native viewport
            SetStyle(ControlStyles.UserPaint | ControlStyles.SupportsTransparentBackColor |
                     ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);

            _timer = new Timer();
            _timer.Interval = 120;
            _timer.Tick += (s, e) => RefreshProjectedAnchors();
            _timer.Start();
            Disposed += (s, e) => _timer.Dispose();
            RefreshProjectedAnchors();
        }

        public static bool TryCreate(Controller controller, Control root, out AsterMaxViewportProjectionOverlay overlay)
        {
            overlay = null;
            Control vtk = FindVtkControl(root);
            if (vtk == null) return false;

            object renderer = null;
            try
            {
                FieldInfo field = vtk.GetType().GetField("_renderer", BindingFlags.NonPublic | BindingFlags.Instance);
                if (field != null) renderer = field.GetValue(vtk);
            }
            catch { renderer = null; }
            if (renderer == null) return false;

            overlay = new AsterMaxViewportProjectionOverlay(controller, vtk, renderer);
            vtk.Controls.Add(overlay);
            overlay.BringToFront();
            return true;
        }

        private static Control FindVtkControl(Control root)
        {
            if (root == null) return null;
            Type t = root.GetType();
            if (String.Equals(t.FullName, "vtkControl.vtkControl", StringComparison.Ordinal)) return root;
            foreach (Control child in root.Controls)
            {
                Control found = FindVtkControl(child);
                if (found != null) return found;
            }
            return null;
        }

        public void RefreshProjectedAnchors()
        {
            _glyphs.Clear();
            object model = null;
            try { if (_controller != null) model = _controller.Model; } catch { }
            if (model == null)
            {
                _status = "VTK PROJECTION READY · MODEL MISSING";
                Invalidate();
                return;
            }

            int resolved = 0;
            int unqualified = 0;
            object stepCollection = ReadMember(model, "StepCollection");
            IEnumerable steps = ReadMember(stepCollection, "StepsList") as IEnumerable;
            if (steps == null)
            {
                _status = "VTK PROJECTION READY · STEP API UNKNOWN";
                Invalidate();
                return;
            }

            foreach (object step in steps)
            {
                if (step == null) continue;
                CollectProjected(step, model, "BoundaryConditions", ref resolved, ref unqualified);
                CollectProjected(step, model, "Loads", ref resolved, ref unqualified);
            }

            _status = "FE XYZ → VTK WorldToDisplay · ANCHORS " + resolved + " · UNQUALIFIED " + unqualified;
            Invalidate();
        }

        private void CollectProjected(object step, object model, string collectionName, ref int resolved, ref int unqualified)
        {
            IEnumerable items = ReadMember(step, collectionName) as IEnumerable;
            if (items == null) return;
            foreach (object raw in items)
            {
                object target = UnwrapDictionaryEntry(raw);
                if (target == null) continue;
                GlyphKind kind = Classify(target);
                if (kind == GlyphKind.Unsupported) continue;

                double[] xyz;
                if (!TryResolveFeAnchor(model, target, out xyz)) { unqualified++; continue; }
                PointF display;
                if (!TryProjectWorld(xyz, out display)) { unqualified++; continue; }

                string name = Safe(ReadMember(target, "Name"));
                _glyphs.Add(new ProjectedGlyph(kind, display, name));
                resolved++;
            }
        }

        private static bool TryResolveFeAnchor(object model, object target, out double[] xyz)
        {
            xyz = null;
            try
            {
                MethodInfo resolver = typeof(AsterMaxRegionBindingInspector).GetMethod("ResolveAnchor",
                    BindingFlags.NonPublic | BindingFlags.Static);
                if (resolver == null) return false;
                object resolution = resolver.Invoke(null, new object[] { model, target });
                if (resolution == null) return false;
                Type rt = resolution.GetType();
                FieldInfo resolvedField = rt.GetField("_resolved", BindingFlags.NonPublic | BindingFlags.Instance);
                FieldInfo xyzField = rt.GetField("_xyz", BindingFlags.NonPublic | BindingFlags.Instance);
                if (resolvedField == null || xyzField == null) return false;
                object resolvedValue = resolvedField.GetValue(resolution);
                if (!(resolvedValue is bool) || !(bool)resolvedValue) return false;
                xyz = xyzField.GetValue(resolution) as double[];
                return xyz != null && xyz.Length >= 3;
            }
            catch { return false; }
        }

        private bool TryProjectWorld(double[] xyz, out PointF displayPoint)
        {
            displayPoint = PointF.Empty;
            if (_renderer == null || xyz == null || xyz.Length < 3) return false;
            try
            {
                Type type = _renderer.GetType();
                MethodInfo setWorld = type.GetMethod("SetWorldPoint", BindingFlags.Public | BindingFlags.Instance,
                    null, new Type[] { typeof(double), typeof(double), typeof(double), typeof(double) }, null);
                MethodInfo worldToDisplay = type.GetMethod("WorldToDisplay", BindingFlags.Public | BindingFlags.Instance,
                    null, Type.EmptyTypes, null);
                MethodInfo getDisplay = type.GetMethod("GetDisplayPoint", BindingFlags.Public | BindingFlags.Instance,
                    null, Type.EmptyTypes, null);
                if (setWorld == null || worldToDisplay == null || getDisplay == null) return false;

                setWorld.Invoke(_renderer, new object[] { xyz[0], xyz[1], xyz[2], 1.0 });
                worldToDisplay.Invoke(_renderer, null);
                double[] d = getDisplay.Invoke(_renderer, null) as double[];
                if (d == null || d.Length < 2 || Double.IsNaN(d[0]) || Double.IsNaN(d[1]) ||
                    Double.IsInfinity(d[0]) || Double.IsInfinity(d[1])) return false;

                // VTK display origin is bottom-left; WinForms client origin is top-left.
                float x = (float)d[0];
                float y = (float)(_vtkControl.ClientSize.Height - d[1]);
                displayPoint = new PointF(x, y);
                return true;
            }
            catch { return false; }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            DrawProjectionStatus(g);

            foreach (ProjectedGlyph glyph in _glyphs)
            {
                if (glyph.Point.X < -24 || glyph.Point.Y < -24 ||
                    glyph.Point.X > Width + 24 || glyph.Point.Y > Height + 24) continue;
                DrawAnchoredGlyph(g, glyph);
            }
        }

        private void DrawProjectionStatus(Graphics g)
        {
            Rectangle r = new Rectangle(12, 12, Math.Min(390, Math.Max(220, Width - 24)), 42);
            using (Brush bg = new SolidBrush(Color.FromArgb(205, AsterMaxUiTheme.Background)))
            using (Pen border = new Pen(AsterMaxUiTheme.Border, 1f))
            {
                g.FillRectangle(bg, r);
                g.DrawRectangle(border, r);
            }
            using (Font title = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.2f, FontStyle.Bold))
            using (Font small = new Font(SystemFonts.MessageBoxFont.FontFamily, 7.0f, FontStyle.Regular))
            {
                TextRenderer.DrawText(g, "ANCHORED GLYPHS · NATIVE VTK PROJECTION", title,
                    new Rectangle(r.Left + 8, r.Top + 4, r.Width - 16, 16), AsterMaxUiTheme.AccentGlow,
                    TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis);
                TextRenderer.DrawText(g, _status + " · POSITION ONLY · NOT SOLVER VERIFIED", small,
                    new Rectangle(r.Left + 8, r.Top + 21, r.Width - 16, 15), AsterMaxUiTheme.TextSecondary,
                    TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis);
            }
        }

        private static void DrawAnchoredGlyph(Graphics g, ProjectedGlyph glyph)
        {
            float x = glyph.Point.X;
            float y = glyph.Point.Y;
            Color c = glyph.Kind == GlyphKind.Fixed ? AsterMaxUiTheme.AccentGlow :
                      glyph.Kind == GlyphKind.Pressure ? AsterMaxUiTheme.Warning : AsterMaxUiTheme.Success;
            using (Pen p = new Pen(c, 2.0f))
            using (Brush halo = new SolidBrush(Color.FromArgb(48, c)))
            using (Brush dot = new SolidBrush(c))
            using (Font f = new Font(SystemFonts.MessageBoxFont.FontFamily, 7.0f, FontStyle.Bold))
            {
                g.FillEllipse(halo, x - 12, y - 12, 24, 24);
                g.FillEllipse(dot, x - 2.5f, y - 2.5f, 5, 5);
                if (glyph.Kind == GlyphKind.Fixed)
                {
                    g.DrawLine(p, x - 8, y - 7, x - 8, y + 8);
                    g.DrawLine(p, x - 8, y - 7, x + 7, y - 7);
                    for (int yy = -4; yy <= 7; yy += 4) g.DrawLine(p, x - 13, y + yy + 3, x - 8, y + yy);
                }
                else if (glyph.Kind == GlyphKind.Pressure)
                {
                    for (int dx = -8; dx <= 8; dx += 8)
                    {
                        g.DrawLine(p, x + dx, y - 14, x + dx, y - 5);
                        g.DrawLine(p, x + dx, y - 5, x + dx - 3, y - 9);
                        g.DrawLine(p, x + dx, y - 5, x + dx + 3, y - 9);
                    }
                }
                else
                {
                    g.DrawLine(p, x, y - 16, x, y - 5);
                    g.DrawLine(p, x, y - 5, x - 4, y - 10);
                    g.DrawLine(p, x, y - 5, x + 4, y - 10);
                }
                TextRenderer.DrawText(g, glyph.Name, f, new Rectangle((int)x + 12, (int)y - 9, 120, 18),
                    c, TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis);
            }
        }

        private static GlyphKind Classify(object target)
        {
            string haystack = (target.GetType().Name + " " + Safe(ReadMember(target, "Name"))).ToLowerInvariant();
            if (haystack.Contains("pressure")) return GlyphKind.Pressure;
            if (haystack.Contains("force") || haystack.Contains("concentrated")) return GlyphKind.Force;
            if (haystack.Contains("fixed") || haystack.Contains("constraint") ||
                haystack.Contains("displacement") || haystack.Contains("support")) return GlyphKind.Fixed;
            return GlyphKind.Unsupported;
        }

        private static object ReadMember(object target, string name)
        {
            if (target == null) return null;
            try
            {
                Type t = target.GetType();
                PropertyInfo p = t.GetProperty(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                if (p != null) return p.GetValue(target, null);
                FieldInfo f = t.GetField(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                if (f != null) return f.GetValue(target);
            }
            catch { }
            return null;
        }

        private static object UnwrapDictionaryEntry(object item)
        {
            if (item == null) return null;
            object value = ReadMember(item, "Value");
            return value ?? item;
        }

        private static string Safe(object value)
        {
            if (value == null) return "?";
            string s = value.ToString();
            return String.IsNullOrWhiteSpace(s) ? "?" : s;
        }

        private sealed class ProjectedGlyph
        {
            public readonly GlyphKind Kind;
            public readonly PointF Point;
            public readonly string Name;
            public ProjectedGlyph(GlyphKind kind, PointF point, string name)
            {
                Kind = kind; Point = point; Name = name;
            }
        }

        private enum GlyphKind { Unsupported, Fixed, Force, Pressure }
    }
}
