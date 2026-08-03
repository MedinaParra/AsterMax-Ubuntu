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
    public bool DarkTheme { get; set; }
    public string Caption { get; set; } = "Geometry";
    public string SubCaption { get; set; } = "Import geometry to begin";

    public MechanicalViewport()
    {
        Dock = DockStyle.Fill;
        DoubleBuffered = true;
        BackColor = Color.FromArgb(232, 237, 243);
        MouseWheel += (_, e) => { _zoom = Math.Clamp(_zoom + (e.Delta > 0 ? .1f : -.1f), .45f, 2.4f); Invalidate(); };
        MouseDown += (_, e) =>
        {
            if (e.Button == MouseButtons.Middle || e.Button == MouseButtons.Left && ModifierKeys.HasFlag(Keys.Control))
            {
                _dragging = true;
                _last = e.Location;
            }
        };
        MouseMove += (_, e) =>
        {
            if (!_dragging) return;
            _yaw += (e.X - _last.X) * .01f;
            _last = e.Location;
            Invalidate();
        };
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
        var graphics = e.Graphics;
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        var top = DarkTheme ? Color.FromArgb(54, 60, 70) : Color.FromArgb(252, 253, 255);
        var bottom = DarkTheme ? Color.FromArgb(17, 20, 24) : Color.FromArgb(218, 226, 235);
        using (var background = new LinearGradientBrush(ClientRectangle, top, bottom, 90f))
            graphics.FillRectangle(background, ClientRectangle);
        DrawFloor(graphics);
        DrawPart(graphics);
        DrawTriad(graphics);
        DrawOverlay(graphics);
        if (ResultVisible) DrawLegend(graphics);
    }

    private void DrawFloor(Graphics graphics)
    {
        var color = DarkTheme ? Color.FromArgb(28, 230, 235, 240) : Color.FromArgb(50, 87, 107, 127);
        using var pen = new Pen(color);
        var horizon = ClientSize.Height * .72f;
        for (var index = -11; index <= 11; index++)
        {
            var x = ClientSize.Width / 2f + index * 42f;
            graphics.DrawLine(pen, x, horizon - 70, x + index * 9, ClientSize.Height);
        }
        for (var row = 0; row < 8; row++)
        {
            var y = horizon + row * row * 4.5f;
            graphics.DrawLine(pen, 0, y, ClientSize.Width, y);
        }
    }

    private void DrawPart(Graphics graphics)
    {
        var centerX = ClientSize.Width * .5f;
        var centerY = ClientSize.Height * .47f;
        var scale = Math.Min(ClientSize.Width, ClientSize.Height) * .30f * _zoom;
        var length = scale * 1.85f;
        var height = scale * .58f;
        var depth = scale * .38f;
        var cosine = MathF.Cos(_yaw);
        var sine = MathF.Sin(_yaw);

        PointF Project(float x, float y, float z)
        {
            var rotatedX = x * cosine - z * sine;
            var rotatedZ = x * sine + z * cosine;
            return new PointF(centerX + rotatedX, centerY + y + rotatedZ * .38f);
        }

        var a = Project(-length / 2, -height / 2, -depth / 2);
        var b = Project(length / 2, -height / 2, -depth / 2);
        var c = Project(length / 2, height / 2, -depth / 2);
        var d = Project(-length / 2, height / 2, -depth / 2);
        var e = Project(-length / 2, -height / 2, depth / 2);
        var f = Project(length / 2, -height / 2, depth / 2);
        var h = Project(length / 2, height / 2, depth / 2);
        var i = Project(-length / 2, height / 2, depth / 2);

        Color Face(int band, float shade)
        {
            if (!ResultVisible)
            {
                var baseColor = DarkTheme ? Color.FromArgb(76, 142, 188) : Color.FromArgb(70, 142, 190);
                return Color.FromArgb(
                    Math.Clamp((int)(baseColor.R * shade), 0, 255),
                    Math.Clamp((int)(baseColor.G * shade), 0, 255),
                    Math.Clamp((int)(baseColor.B * shade), 0, 255));
            }
            return band switch
            {
                0 => Color.FromArgb(30, 90, 220),
                1 => Color.FromArgb(20, 185, 210),
                2 => Color.FromArgb(70, 205, 95),
                3 => Color.FromArgb(245, 205, 45),
                _ => Color.FromArgb(232, 65, 40)
            };
        }

        Fill(graphics, Face(1, .82f), a, b, c, d);
        Fill(graphics, Face(2, 1f), e, f, h, i);
        Fill(graphics, Face(4, 1f), b, f, h, c);
        Fill(graphics, Face(3, 1f), a, e, f, b);
        Fill(graphics, Face(0, .72f), a, d, i, e);
        Fill(graphics, Face(2, .88f), d, c, h, i);

        using var edge = new Pen(DarkTheme ? Color.FromArgb(205, 226, 236) : Color.FromArgb(49, 67, 82), 1.2f);
        foreach (var pair in new[] { (a,b),(b,c),(c,d),(d,a),(e,f),(f,h),(h,i),(i,e),(a,e),(b,f),(c,h),(d,i) })
            graphics.DrawLine(edge, pair.Item1, pair.Item2);

        DrawHoles(graphics, Project, length, height, depth);
        if (MeshVisible) DrawMesh(graphics, new[] { a, b, c, d, e, f, h, i });
        if (SupportVisible) DrawSupport(graphics, Project(-length * .51f, 0, 0));
        if (ForceVisible) DrawForce(graphics, Project(length * .52f, 0, 0));
    }

    private static void Fill(Graphics graphics, Color color, params PointF[] points)
    {
        using var brush = new SolidBrush(color);
        graphics.FillPolygon(brush, points);
    }

    private void DrawHoles(Graphics graphics, Func<float, float, float, PointF> project, float length, float height, float depth)
    {
        using var dark = new SolidBrush(DarkTheme ? Color.FromArgb(18, 22, 28) : Color.FromArgb(224, 230, 236));
        using var rim = new Pen(DarkTheme ? Color.FromArgb(220, 230, 238) : Color.FromArgb(45, 61, 75), 1.1f);
        foreach (var sign in new[] { -1, 1 })
        {
            var center = project(sign * length * .31f, 0, depth * .51f);
            var radius = Math.Max(11f, height * .16f);
            var rectangle = new RectangleF(center.X - radius, center.Y - radius * .55f, radius * 2, radius * 1.1f);
            graphics.FillEllipse(dark, rectangle);
            graphics.DrawEllipse(rim, rectangle);
        }
    }

    private void DrawMesh(Graphics graphics, PointF[] points)
    {
        using var pen = new Pen(DarkTheme ? Color.FromArgb(120, 10, 18, 24) : Color.FromArgb(125, 30, 48, 62), .8f);
        for (var index = 1; index < 10; index++)
        {
            var t = index / 10f;
            graphics.DrawLine(pen, Lerp(points[0], points[1], t), Lerp(points[3], points[2], t));
            graphics.DrawLine(pen, Lerp(points[4], points[5], t), Lerp(points[7], points[6], t));
            graphics.DrawLine(pen, Lerp(points[0], points[3], t), Lerp(points[1], points[2], t));
            graphics.DrawLine(pen, Lerp(points[4], points[7], t), Lerp(points[5], points[6], t));
        }
    }

    private static PointF Lerp(PointF start, PointF end, float t) =>
        new(start.X + (end.X - start.X) * t, start.Y + (end.Y - start.Y) * t);

    private static void DrawSupport(Graphics graphics, PointF point)
    {
        using var pen = new Pen(Color.FromArgb(0, 175, 180), 2f);
        for (var index = -3; index <= 3; index++)
            graphics.DrawLine(pen, point.X - 7, point.Y + index * 6, point.X - 28, point.Y + index * 6 + 10);
    }

    private static void DrawForce(Graphics graphics, PointF point)
    {
        using var pen = new Pen(Color.FromArgb(220, 45, 55), 3f) { EndCap = LineCap.ArrowAnchor };
        graphics.DrawLine(pen, point.X + 105, point.Y - 55, point.X + 10, point.Y - 5);
        using var font = new Font("Segoe UI Semibold", 9f);
        using var brush = new SolidBrush(Color.FromArgb(196, 35, 48));
        graphics.DrawString("Force", font, brush, point.X + 58, point.Y - 78);
    }

    private void DrawTriad(Graphics graphics)
    {
        var origin = new PointF(ClientSize.Width - 75, ClientSize.Height - 58);
        using var x = new Pen(Color.IndianRed, 2f) { EndCap = LineCap.ArrowAnchor };
        using var y = new Pen(Color.ForestGreen, 2f) { EndCap = LineCap.ArrowAnchor };
        using var z = new Pen(Color.RoyalBlue, 2f) { EndCap = LineCap.ArrowAnchor };
        graphics.DrawLine(x, origin, new PointF(origin.X + 38, origin.Y));
        graphics.DrawLine(y, origin, new PointF(origin.X, origin.Y - 38));
        graphics.DrawLine(z, origin, new PointF(origin.X - 25, origin.Y + 22));
    }

    private void DrawOverlay(Graphics graphics)
    {
        var panelColor = DarkTheme ? Color.FromArgb(155, 10, 13, 17) : Color.FromArgb(215, 255, 255, 255);
        using var panel = new SolidBrush(panelColor);
        graphics.FillRectangle(panel, 14, 14, 310, 58);
        using var border = new Pen(DarkTheme ? Color.FromArgb(75, 100, 115) : Color.FromArgb(177, 188, 200));
        graphics.DrawRectangle(border, 14, 14, 310, 58);
        using var title = new Font("Segoe UI Semibold", 10f);
        using var text = new Font("Segoe UI", 8.7f);
        using var titleBrush = new SolidBrush(DarkTheme ? Color.White : Color.FromArgb(28, 40, 52));
        using var textBrush = new SolidBrush(DarkTheme ? Color.LightGray : Color.FromArgb(73, 87, 102));
        graphics.DrawString(Caption, title, titleBrush, 25, 22);
        graphics.DrawString(SubCaption, text, textBrush, 25, 46);
        graphics.DrawString("Ctrl + drag: rotate    Wheel: zoom    F7: fit", text, textBrush, 14, ClientSize.Height - 25);
    }

    private void DrawLegend(Graphics graphics)
    {
        var rectangle = new Rectangle(ClientSize.Width - 115, 38, 30, Math.Max(150, ClientSize.Height / 3));
        using var gradient = new LinearGradientBrush(rectangle, Color.Red, Color.Blue, 90f);
        gradient.InterpolationColors = new ColorBlend
        {
            Colors = new[] { Color.Red, Color.Orange, Color.Yellow, Color.LimeGreen, Color.Cyan, Color.Blue },
            Positions = new[] { 0f, .2f, .4f, .6f, .8f, 1f }
        };
        graphics.FillRectangle(gradient, rectangle);
        using var border = new Pen(DarkTheme ? Color.LightGray : Color.FromArgb(55, 65, 75));
        graphics.DrawRectangle(border, rectangle);
        using var font = new Font("Segoe UI", 8f);
        using var brush = new SolidBrush(DarkTheme ? Color.White : Color.FromArgb(35, 45, 55));
        graphics.DrawString("Max", font, brush, rectangle.Right + 5, rectangle.Top - 2);
        graphics.DrawString("Min", font, brush, rectangle.Right + 5, rectangle.Bottom - 11);
    }
}
