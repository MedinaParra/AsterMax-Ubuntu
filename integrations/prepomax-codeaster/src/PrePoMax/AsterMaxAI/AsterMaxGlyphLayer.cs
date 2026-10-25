using System;
using System.Collections;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Reflection;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    // Screen-space engineering glyph layer. It visualizes observed model objects only.
    // It is intentionally NOT entity-anchored and MUST NOT be interpreted as solver evidence.
    public sealed class AsterMaxGlyphLayer : UserControl
    {
        private readonly Controller _controller;
        private readonly Timer _timer;
        private ObservedSummary _summary;

        public AsterMaxGlyphLayer(Controller controller)
        {
            _controller = controller;
            Name = "ucAsterMaxGlyphLayer";
            Size = new Size(214, 204);
            MinimumSize = Size;
            MaximumSize = Size;
            BackColor = AsterMaxUiTheme.SurfaceRaised;
            ForeColor = AsterMaxUiTheme.TextPrimary;
            Padding = new Padding(0);
            Anchor = AnchorStyles.Top | AnchorStyles.Left;
            DoubleBuffered = true;

            _timer = new Timer();
            _timer.Interval = 1200;
            _timer.Tick += (s, e) => RefreshObservedState();
            _timer.Start();
            Disposed += (s, e) => _timer.Dispose();

            RefreshObservedState();
        }

        public void RefreshObservedState()
        {
            object model = null;
            try { if (_controller != null) model = _controller.Model; } catch { }

            ObservedSummary next = new ObservedSummary();
            // C8.59 correction: BC/load collections belong to Step objects, not directly to FeModel.
            next.Fixed = ProbeStepTypedCount(model, "BoundaryConditions",
                new[] { "fixed", "constraint", "displacement", "support" });
            next.Forces = ProbeStepTypedCount(model, "Loads",
                new[] { "cload", "force", "concentrated" });
            next.Pressures = ProbeStepTypedCount(model, "Loads",
                new[] { "pressure" });
            // C8.59 correction: FeModel.Mesh always exists, even before FE meshing. Count actual
            // elements instead of treating the mere mesh container as one mesh object.
            next.Mesh = ProbeMeshElementCount(model);
            next.ModelPresent = model != null;
            _summary = next;
            Invalidate();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            using (Pen border = new Pen(AsterMaxUiTheme.Border, 1f))
                g.DrawRectangle(border, 0, 0, Width - 1, Height - 1);

            using (Font title = new Font(SystemFonts.MessageBoxFont.FontFamily, 9.2f, FontStyle.Bold))
            using (Font small = new Font(SystemFonts.MessageBoxFont.FontFamily, 7.3f, FontStyle.Regular))
            using (Font rowFont = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.1f, FontStyle.Bold))
            {
                TextRenderer.DrawText(g, "ENGINEERING GLYPHS", title, new Rectangle(12, 9, 185, 20),
                    AsterMaxUiTheme.AccentGlow, TextFormatFlags.Left | TextFormatFlags.VerticalCenter);
                TextRenderer.DrawText(g, "SCREEN SPACE · OBSERVED MODEL STATE", small,
                    new Rectangle(12, 29, 190, 17), AsterMaxUiTheme.TextSecondary,
                    TextFormatFlags.Left | TextFormatFlags.VerticalCenter);

                DrawGlyphRow(g, 52, Glyph.Fixed, "FIXED SUPPORT", _summary.Fixed, rowFont);
                DrawGlyphRow(g, 82, Glyph.Force, "FORCE", _summary.Forces, rowFont);
                DrawGlyphRow(g, 112, Glyph.Pressure, "PRESSURE", _summary.Pressures, rowFont);
                DrawGlyphRow(g, 142, Glyph.Mesh, "MESH ELEMENTS", _summary.Mesh, rowFont);

                TextRenderer.DrawText(g, "NOT ENTITY-ANCHORED · NOT SOLVER VERIFIED", small,
                    new Rectangle(12, 178, 190, 18), AsterMaxUiTheme.Warning,
                    TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis);
            }
        }

        private static void DrawGlyphRow(Graphics g, int y, Glyph glyph, string label, ProbeState state, Font font)
        {
            Rectangle iconRect = new Rectangle(12, y + 2, 24, 24);
            DrawGlyph(g, iconRect, glyph, state);
            string stateText = state.Known ? state.Count.ToString() : "?";
            Color fore = state.Known && state.Count > 0 ? AsterMaxUiTheme.Success :
                         state.Known ? AsterMaxUiTheme.TextSecondary : AsterMaxUiTheme.Warning;
            TextRenderer.DrawText(g, label, font, new Rectangle(46, y, 116, 28),
                AsterMaxUiTheme.TextPrimary, TextFormatFlags.Left | TextFormatFlags.VerticalCenter);
            TextRenderer.DrawText(g, stateText, font, new Rectangle(164, y, 34, 28),
                fore, TextFormatFlags.Right | TextFormatFlags.VerticalCenter);
        }

        private static void DrawGlyph(Graphics g, Rectangle r, Glyph glyph, ProbeState state)
        {
            Color c = state.Known && state.Count > 0 ? AsterMaxUiTheme.AccentGlow : AsterMaxUiTheme.TextSecondary;
            using (Pen p = new Pen(c, 1.8f))
            using (Brush b = new SolidBrush(Color.FromArgb(60, c)))
            {
                p.StartCap = LineCap.Round;
                p.EndCap = LineCap.Round;
                if (glyph == Glyph.Fixed)
                {
                    int x = r.Left + 7;
                    g.DrawLine(p, x, r.Top + 3, x, r.Bottom - 4);
                    g.DrawLine(p, x, r.Top + 5, r.Right - 3, r.Top + 5);
                    g.DrawLine(p, x, r.Bottom - 6, r.Right - 3, r.Bottom - 6);
                    for (int yy = r.Top + 7; yy < r.Bottom - 5; yy += 5)
                        g.DrawLine(p, r.Left + 2, yy + 2, x, yy - 1);
                }
                else if (glyph == Glyph.Force)
                {
                    int cx = r.Left + r.Width / 2;
                    g.DrawLine(p, cx, r.Top + 2, cx, r.Bottom - 7);
                    g.DrawLine(p, cx, r.Bottom - 7, cx - 5, r.Bottom - 12);
                    g.DrawLine(p, cx, r.Bottom - 7, cx + 5, r.Bottom - 12);
                    g.FillEllipse(b, cx - 3, r.Top + 1, 6, 6);
                }
                else if (glyph == Glyph.Pressure)
                {
                    for (int x = r.Left + 5; x <= r.Right - 5; x += 7)
                    {
                        g.DrawLine(p, x, r.Top + 2, x, r.Bottom - 9);
                        g.DrawLine(p, x, r.Bottom - 9, x - 3, r.Bottom - 12);
                        g.DrawLine(p, x, r.Bottom - 9, x + 3, r.Bottom - 12);
                    }
                    g.DrawLine(p, r.Left + 2, r.Bottom - 5, r.Right - 2, r.Bottom - 5);
                }
                else if (glyph == Glyph.Mesh)
                {
                    g.DrawRectangle(p, r.Left + 2, r.Top + 2, r.Width - 5, r.Height - 5);
                    g.DrawLine(p, r.Left + 2, r.Top + 2, r.Right - 3, r.Bottom - 3);
                    g.DrawLine(p, r.Right - 3, r.Top + 2, r.Left + 2, r.Bottom - 3);
                    g.DrawLine(p, r.Left + r.Width / 2, r.Top + 2, r.Left + r.Width / 2, r.Bottom - 3);
                }
            }
        }

        private static ProbeState ProbeMeshElementCount(object model)
        {
            if (model == null) return new ProbeState(true, 0);
            object mesh;
            if (!TryGetPropertyValue(model, new[] { "Mesh" }, out mesh)) return ProbeState.Unknown;
            if (mesh == null) return new ProbeState(true, 0);
            object elements;
            if (!TryGetPropertyValue(mesh, new[] { "Elements" }, out elements)) return ProbeState.Unknown;
            if (elements == null) return new ProbeState(true, 0);
            int count;
            return TryGetCount(elements, out count) ? new ProbeState(true, count) : ProbeState.Unknown;
        }

        private static ProbeState ProbeStepTypedCount(object model, string collectionName, string[] typeTokens)
        {
            if (model == null) return new ProbeState(true, 0);
            object stepCollection;
            if (!TryGetPropertyValue(model, new[] { "StepCollection" }, out stepCollection) || stepCollection == null)
                return ProbeState.Unknown;
            object stepsRaw;
            if (!TryGetPropertyValue(stepCollection, new[] { "StepsList" }, out stepsRaw) || stepsRaw == null)
                return ProbeState.Unknown;
            IEnumerable steps = stepsRaw as IEnumerable;
            if (steps == null) return ProbeState.Unknown;
            int matched = 0;
            try
            {
                foreach (object rawStep in steps)
                {
                    object step = UnwrapValue(rawStep);
                    if (step == null) continue;
                    object collection;
                    if (!TryGetPropertyValue(step, new[] { collectionName }, out collection) || collection == null) continue;
                    IEnumerable items = collection as IEnumerable;
                    if (items == null) continue;
                    foreach (object rawItem in items)
                    {
                        object item = UnwrapValue(rawItem);
                        if (item == null) continue;
                        string haystack = (item.GetType().Name + " " + item.ToString()).ToLowerInvariant();
                        foreach (string token in typeTokens)
                        {
                            if (haystack.Contains(token.ToLowerInvariant())) { matched++; break; }
                        }
                    }
                }
                return new ProbeState(true, matched);
            }
            catch { return ProbeState.Unknown; }
        }

        private static object UnwrapValue(object item)
        {
            if (item == null) return null;
            try
            {
                PropertyInfo p = item.GetType().GetProperty("Value", BindingFlags.Public | BindingFlags.Instance);
                return p == null ? item : (p.GetValue(item, null) ?? item);
            }
            catch { return item; }
        }

        private static bool TryGetPropertyValue(object root, string[] names, out object value)
        {
            value = null;
            if (root == null) return false;
            Type type = root.GetType();
            foreach (string name in names)
            {
                try
                {
                    PropertyInfo pi = type.GetProperty(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                    if (pi == null) continue;
                    value = pi.GetValue(root, null);
                    return true;
                }
                catch { return false; }
            }
            return false;
        }

        private static bool TryGetCount(object value, out int count)
        {
            count = 0;
            ICollection collection = value as ICollection;
            if (collection != null) { count = collection.Count; return true; }
            try
            {
                PropertyInfo pi = value.GetType().GetProperty("Count", BindingFlags.Public | BindingFlags.Instance);
                if (pi == null) return false;
                object raw = pi.GetValue(value, null);
                return raw != null && Int32.TryParse(raw.ToString(), out count);
            }
            catch { return false; }
        }

        private struct ObservedSummary
        {
            public bool ModelPresent;
            public ProbeState Fixed;
            public ProbeState Forces;
            public ProbeState Pressures;
            public ProbeState Mesh;
        }

        private struct ProbeState
        {
            public readonly bool Known;
            public readonly int Count;
            public ProbeState(bool known, int count) { Known = known; Count = count; }
            public static ProbeState Unknown { get { return new ProbeState(false, 0); } }
        }

        private enum Glyph { Fixed, Force, Pressure, Mesh }
    }
}
