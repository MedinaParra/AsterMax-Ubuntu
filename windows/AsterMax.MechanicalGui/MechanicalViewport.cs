using System.Drawing.Drawing2D;

namespace AsterMax.MechanicalGui;

internal sealed class MechanicalViewport : Control
{
    private float _zoom = 1f;
    private float _yaw = -0.35f;
    private Point _last;
    private bool _dragging;

    public bool MeshVisible { get; set; }
    public bool ResultVisible { get; set; }
    public bool SupportVisible { get; set; }
    public bool ForceVisible { get; set; }
    public string Caption { get; set; } = "Geometry";
    public string SubCaption { get; set; } = "Import geometry to begin";

    public MechanicalViewport()
    {
        Dock = DockStyle.Fill;
        DoubleBuffered = true;
        BackColor = Color.FromArgb(28, 32, 38);
        MouseWheel += (_, e) => { _zoom = Math.Clamp(_zoom + (e.Delta > 0 ? .1f : -.1f), .45f, 2.4f); Invalidate(); };
        MouseDown += (_, e) => { if (e.Button == MouseButtons.Middle || e.Button == MouseButtons.Left && ModifierKeys.HasFlag(Keys.Control)) { _dragging = true; _last = e.Location; } };
        MouseMove += (_, e) => { if (!_dragging) return; _yaw += (e.X - _last.X) * .01f; _last = e.Location; Invalidate(); };
        MouseUp += (_, _) => _dragging = false;
    }

    public void Fit()
    {
        _zoom = 1f;
        _yaw = -.35f;
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        using (var bg = new LinearGradientBrush(ClientRectangle, Color.FromArgb(54, 60, 70), Color.FromArgb(17, 20, 24), 90f))
            g.FillRectangle(bg, ClientRectangle);
        DrawFloor(g);
        DrawPart(g);
        DrawTriad(g);
        DrawOverlay(g);
        if (ResultVisible) DrawLegend(g);
    }

    private void DrawFloor(Graphics g)
    {
        using var pen = new Pen(Color.FromArgb(28, 230, 235, 240));
        var h = ClientSize.Height * .72f;
        for (var i = -11; i <= 11; i++)
        {
            var x = ClientSize.Width / 2f + i * 42f;
            g.DrawLine(pen, x, h - 70, x + i * 9, ClientSize.Height);
        }
        for (var j = 0; j < 8; j++)
        {
            var y = h + j * j * 4.5f;
            g.DrawLine(pen, 0, y, ClientSize.Width, y);
        }
    }

    private void DrawPart(Graphics g)
    {
        var cx = ClientSize.Width * .5f;
        var cy = ClientSize.Height * .47f;
        var s = Math.Min(ClientSize.Width, ClientSize.Height) * .30f * _zoom;
        var length = s * 1.85f;
        var height = s * .58f;
        var depth = s * .38f;
        var c = MathF.Cos(_yaw);
        var sn = MathF.Sin(_yaw);

        PointF P(float x, float y, float z)
        {
            var rx = x * c - z * sn;
            var rz = x * sn + z * c;
            return new PointF(cx + rx, cy + y + rz * .38f);
        }

        var a = P(-length / 2, -height / 2, -depth / 2);
        var b = P(length / 2, -height / 2, -depth / 2);
        var c1 = P(length / 2, height / 2, -depth / 2);
        var d = P(-length / 2, height / 2, -depth / 2);
        var e = P(-length / 2, -height / 2, depth / 2);
        var f = P(length / 2, -height / 2, depth / 2);
        var h = P(length / 2, height / 2, depth / 2);
        var i = P(-length / 2, height / 2, depth / 2);

        Color Face(int band, float shade)
        {
            if (!ResultVisible)
                return Color.FromArgb((int)(76 * shade), (int)(142 * shade), (int)(188 * shade));
            return band switch
            {
                0 => Color.FromArgb(30, 90, 220),
                1 => Color.FromArgb(20, 185, 210),
                2 => Color.FromArgb(70, 205, 95),
                3 => Color.FromArgb(245, 205, 45),
                _ => Color.FromArgb(232, 65, 40)
            };
        }

        Fill(g, Face(1, .82f), a, b, c1, d);
        Fill(g, Face(2, 1f), e, f, h, i);
        Fill(g, Face(4, 1f), b, f, h, c1);
        Fill(g, Face(3, 1f), a, e, f, b);
        Fill(g, Face(0, .72f), a, d, i, e);
        Fill(g, Face(2, .88f), d, c1, h, i);

        using var edge = new Pen(Color.FromArgb(205, 226, 236), 1.2f);
        foreach (var pair in new[] { (a,b),(b,c1),(c1,d),(d,a),(e,f),(f,h),(h,i),(i,e),(a,e),(b,f),(c1,h),(d,i) })
            g.DrawLine(edge, pair.Item1, pair.Item2);

        DrawHoles(g, P, length, height, depth);
        if (MeshVisible) DrawMesh(g, new[] { a, b, c1, d, e, f, h, i });
        if (SupportVisible) DrawSupport(g, P(-length * .51f, 0, 0));
        if (ForceVisible) DrawForce(g, P(length * .52f, 0, 0));
    }

    private static void Fill(Graphics g, Color color, params PointF[] points)
    {
        using var brush = new SolidBrush(color);
        g.FillPolygon(brush, points);
    }

    private static void DrawHoles(Graphics g, Func<float, float, float, PointF> p, float length, float height, float depth)
    {
        using var dark = new SolidBrush(Color.FromArgb(18, 22, 28));
        using var rim = new Pen(Color.FromArgb(220, 230, 238), 1.1f);
        foreach (var sign in new[] { -1, 1 })
        {
            var center = p(sign * length * .31f, 0, depth * .51f);
            var r = Math.Max(11f, height * .16f);
            var rect = new RectangleF(center.X - r, center.Y - r * .55f, r * 2, r * 1.1f);
            g.FillEllipse(dark, rect);
            g.DrawEllipse(rim, rect);
        }
    }

    private static void DrawMesh(Graphics g, PointF[] p)
    {
        using var pen = new Pen(Color.FromArgb(120, 10, 18, 24), .8f);
        for (var n = 1; n < 10; n++)
        {
            var t = n / 10f;
            g.DrawLine(pen, Lerp(p[0], p[1], t), Lerp(p[3], p[2], t));
            g.DrawLine(pen, Lerp(p[4], p[5], t), Lerp(p[7], p[6], t));
            g.DrawLine(pen, Lerp(p[0], p[3], t), Lerp(p[1], p[2], t));
            g.DrawLine(pen, Lerp(p[4], p[7], t), Lerp(p[5], p[6], t));
        }
    }

    private static PointF Lerp(PointF a, PointF b, float t) => new(a.X + (b.X - a.X) * t, a.Y + (b.Y - a.Y) * t);

    private static void DrawSupport(Graphics g, PointF p)
    {
        using var pen = new Pen(Color.FromArgb(50, 225, 220), 2f);
        for (var n = -3; n <= 3; n++) g.DrawLine(pen, p.X - 7, p.Y + n * 6, p.X - 28, p.Y + n * 6 + 10);
    }

    private static void DrawForce(Graphics g, PointF p)
    {
        using var pen = new Pen(Color.FromArgb(245, 75, 75), 3f) { EndCap = LineCap.ArrowAnchor };
        g.DrawLine(pen, p.X + 105, p.Y - 55, p.X + 10, p.Y - 5);
        using var font = new Font("Segoe UI Semibold", 9f);
        g.DrawString("Force", font, Brushes.LightCoral, p.X + 58, p.Y - 78);
    }

    private void DrawTriad(Graphics g)
    {
        var o = new PointF(ClientSize.Width - 75, ClientSize.Height - 58);
        using var x = new Pen(Color.IndianRed, 2f) { EndCap = LineCap.ArrowAnchor };
        using var y = new Pen(Color.LightGreen, 2f) { EndCap = LineCap.ArrowAnchor };
        using var z = new Pen(Color.LightBlue, 2f) { EndCap = LineCap.ArrowAnchor };
        g.DrawLine(x, o, new PointF(o.X + 38, o.Y));
        g.DrawLine(y, o, new PointF(o.X, o.Y - 38));
        g.DrawLine(z, o, new PointF(o.X - 25, o.Y + 22));
    }

    private void DrawOverlay(Graphics g)
    {
        using var panel = new SolidBrush(Color.FromArgb(155, 10, 13, 17));
        g.FillRectangle(panel, 14, 14, 290, 58);
        using var title = new Font("Segoe UI Semibold", 10f);
        using var text = new Font("Segoe UI", 8.7f);
        g.DrawString(Caption, title, Brushes.White, 25, 22);
        g.DrawString(SubCaption, text, Brushes.LightGray, 25, 46);
        g.DrawString("Ctrl + drag: rotate    Wheel: zoom    F7: fit", text, Brushes.LightGray, 14, ClientSize.Height - 25);
    }

    private void DrawLegend(Graphics g)
    {
        var rect = new Rectangle(ClientSize.Width - 115, 38, 30, Math.Max(150, ClientSize.Height / 3));
        using var gradient = new LinearGradientBrush(rect, Color.Red, Color.Blue, 90f);
        gradient.InterpolationColors = new ColorBlend
        {
            Colors = new[] { Color.Red, Color.Orange, Color.Yellow, Color.LimeGreen, Color.Cyan, Color.Blue },
            Positions = new[] { 0f, .2f, .4f, .6f, .8f, 1f }
        };
        g.FillRectangle(gradient, rect);
        g.DrawRectangle(Pens.LightGray, rect);
        using var font = new Font("Segoe UI", 8f);
        g.DrawString("Max", font, Brushes.White, rect.Right + 5, rect.Top - 2);
        g.DrawString("Min", font, Brushes.White, rect.Right + 5, rect.Bottom - 11);
    }
}
