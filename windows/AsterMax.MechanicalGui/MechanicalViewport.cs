using System.Drawing.Drawing2D;

namespace AsterMax.MechanicalGui;

internal sealed class MechanicalViewport : Control
{
    private float _zoom = 1f;
    private float _yaw = -0.35f;
    private Point _last;
    private bool _dragging;
    private bool _darkTheme;
    private SimpleStepSolid? _solid;
    private TetMesh? _mesh;
    private StaticSolution? _solution;

    public bool MeshVisible { get; set; }
    public bool ResultVisible { get; set; }
    public bool SupportVisible { get; set; }
    public bool ForceVisible { get; set; }
    public string Caption { get; set; } = "Graphics";
    public string SubCaption { get; set; } = "Import a simple STEP prism to begin";
    public SimpleFace FixedFace { get; set; } = SimpleFace.XMin;
    public SimpleFace LoadFace { get; set; } = SimpleFace.XMax;
    public Vec3 ForceVector { get; set; } = new(0, 0, -1000);

    public MechanicalViewport()
    {
        Dock = DockStyle.Fill;
        DoubleBuffered = true;
        BackColor = Color.FromArgb(236, 242, 248);
        MouseWheel += (_, e) => { _zoom = Math.Clamp(_zoom + (e.Delta > 0 ? .1f : -.1f), .35f, 3.0f); Invalidate(); };
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

    public void SetDarkTheme(bool dark)
    {
        _darkTheme = dark;
        BackColor = dark ? Color.FromArgb(28, 32, 38) : Color.FromArgb(236, 242, 248);
        Invalidate();
    }

    public void ClearModel()
    {
        _solid = null;
        _mesh = null;
        _solution = null;
        MeshVisible = ResultVisible = SupportVisible = ForceVisible = false;
        Caption = "Graphics";
        SubCaption = "Import a simple STEP prism or create the Tutorial 01 example";
        Fit();
    }

    public void SetSolid(SimpleStepSolid solid)
    {
        _solid = solid;
        _mesh = null;
        _solution = null;
        Caption = "Geometry";
        SubCaption = $"{Path.GetFileName(solid.SourcePath)}  |  {solid.LengthX:0.###} × {solid.LengthY:0.###} × {solid.LengthZ:0.###} mm";
        Fit();
    }

    public void SetMesh(TetMesh mesh)
    {
        _mesh = mesh;
        _solution = null;
        MeshVisible = true;
        ResultVisible = false;
        Caption = "Mesh";
        SubCaption = $"{mesh.Nodes.Count:N0} nodes · {mesh.Elements.Count:N0} TET4";
        Invalidate();
    }

    public void SetSolution(StaticSolution solution)
    {
        _solution = solution;
        ResultVisible = true;
        MeshVisible = true;
        Caption = "Equivalent Stress";
        SubCaption = $"Max {solution.MaxVonMisesMpa:0.###} MPa · Umax {solution.MaxDisplacementMm:0.######} mm";
        Invalidate();
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
        g.PixelOffsetMode = PixelOffsetMode.HighQuality;
        DrawBackground(g);
        DrawFloor(g);
        if (_solid is null) DrawEmptyState(g);
        else DrawSolid(g);
        DrawTriad(g);
        DrawOverlay(g);
        if (ResultVisible && _solution is not null) DrawLegend(g);
    }

    private void DrawBackground(Graphics g)
    {
        var top = _darkTheme ? Color.FromArgb(54, 60, 70) : Color.FromArgb(251, 253, 255);
        var bottom = _darkTheme ? Color.FromArgb(17, 20, 24) : Color.FromArgb(217, 228, 239);
        using var background = new LinearGradientBrush(ClientRectangle, top, bottom, 90f);
        g.FillRectangle(background, ClientRectangle);
    }

    private void DrawFloor(Graphics g)
    {
        var line = _darkTheme ? Color.FromArgb(34, 230, 235, 240) : Color.FromArgb(58, 110, 132, 156);
        using var pen = new Pen(line, .8f);
        var horizon = ClientSize.Height * .72f;
        for (var i = -12; i <= 12; i++)
        {
            var x = ClientSize.Width / 2f + i * 45f;
            g.DrawLine(pen, x, horizon - 65, x + i * 10, ClientSize.Height);
        }
        for (var j = 0; j < 9; j++)
        {
            var y = horizon + j * j * 4.2f;
            g.DrawLine(pen, 0, y, ClientSize.Width, y);
        }
    }

    private void DrawEmptyState(Graphics g)
    {
        var box = new RectangleF(ClientSize.Width / 2f - 250, ClientSize.Height / 2f - 78, 500, 156);
        using var fill = new SolidBrush(_darkTheme ? Color.FromArgb(175, 25, 30, 36) : Color.FromArgb(225, 255, 255, 255));
        using var border = new Pen(_darkTheme ? Color.FromArgb(90, 115, 135) : Color.FromArgb(160, 181, 201), 1.2f);
        g.FillRectangle(fill, box);
        g.DrawRectangle(border, box.X, box.Y, box.Width, box.Height);
        using var title = new Font("Segoe UI Semibold", 14f);
        using var text = new Font("Segoe UI", 9.5f);
        var main = _darkTheme ? Brushes.White : Brushes.DarkSlateGray;
        var muted = _darkTheme ? Brushes.LightGray : Brushes.SlateGray;
        DrawCentered(g, "No geometry loaded", title, main, new RectangleF(box.X, box.Y + 25, box.Width, 30));
        DrawCentered(g, "Static Tutorial → Import STEP or Example STEP", text, muted, new RectangleF(box.X, box.Y + 66, box.Width, 24));
        DrawCentered(g, "Supported now: one rectangular/prismatic solid without holes or curves", text, muted, new RectangleF(box.X, box.Y + 94, box.Width, 24));
    }

    private void DrawSolid(Graphics g)
    {
        var solid = _solid!;
        var center = solid.Center;
        var maxDimension = Math.Max(solid.LengthX, Math.Max(solid.LengthY, solid.LengthZ));
        var target = Math.Min(ClientSize.Width, ClientSize.Height) * .42f * _zoom;
        var scale = target / Math.Max(maxDimension, 1e-9);
        var cx = ClientSize.Width * .51f;
        var cy = ClientSize.Height * .46f;
        var cosine = MathF.Cos(_yaw);
        var sine = MathF.Sin(_yaw);
        var exaggeration = _solution is { MaxDisplacementMm: > 1e-15 }
            ? Math.Min(maxDimension * .18 / _solution.MaxDisplacementMm, 1e6)
            : 0.0;

        Vec3 Deform(Vec3 point)
        {
            if (_solution is null || !ResultVisible) return point;
            var fraction = FixedFace switch
            {
                SimpleFace.XMin => (point.X - solid.Min.X) / solid.LengthX,
                SimpleFace.XMax => (solid.Max.X - point.X) / solid.LengthX,
                SimpleFace.YMin => (point.Y - solid.Min.Y) / solid.LengthY,
                SimpleFace.YMax => (solid.Max.Y - point.Y) / solid.LengthY,
                SimpleFace.ZMin => (point.Z - solid.Min.Z) / solid.LengthZ,
                SimpleFace.ZMax => (solid.Max.Z - point.Z) / solid.LengthZ,
                _ => 0
            };
            fraction = Math.Clamp(fraction, 0, 1);
            return point + _solution.LoadedFaceAverageDisplacementMm * (exaggeration * fraction * fraction);
        }

        PointF Project(Vec3 modelPoint)
        {
            var point = Deform(modelPoint) - center;
            var x = (float)(point.X * scale);
            var y = (float)(-point.Z * scale);
            var z = (float)(point.Y * scale);
            var rotatedX = x * cosine - z * sine;
            var rotatedZ = x * sine + z * cosine;
            return new PointF(cx + rotatedX, cy + y + rotatedZ * .36f);
        }

        var model = Corners(solid);
        var p = model.Select(Project).ToArray();
        DrawFace(g, FaceColor(.25), p[0], p[1], p[2], p[3]);
        DrawFace(g, FaceColor(.52), p[4], p[5], p[6], p[7]);
        DrawFace(g, FaceColor(.82), p[1], p[5], p[6], p[2]);
        DrawFace(g, FaceColor(.66), p[0], p[4], p[5], p[1]);
        DrawFace(g, FaceColor(.12), p[0], p[3], p[7], p[4]);
        DrawFace(g, FaceColor(.40), p[3], p[2], p[6], p[7]);

        using var edge = new Pen(_darkTheme ? Color.FromArgb(215, 230, 240) : Color.FromArgb(37, 71, 96), 1.15f);
        foreach (var pair in new[] { (0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7) })
            g.DrawLine(edge, p[pair.Item1], p[pair.Item2]);

        if (MeshVisible && _mesh is not null) DrawStructuredMesh(g, p, _mesh);
        if (SupportVisible) DrawSupport(g, Project(FaceCenter(solid, FixedFace)));
        if (ForceVisible) DrawForce(g, Project(FaceCenter(solid, LoadFace)), ForceVector);
        DrawDimensions(g, solid);

        Color FaceColor(double position)
        {
            if (!ResultVisible || _solution is null) return Blend(Color.FromArgb(50, 142, 202), Color.FromArgb(126, 191, 226), position);
            var hot = Color.FromArgb(220, 63, 43);
            var cold = Color.FromArgb(25, 105, 210);
            return Blend(hot, cold, position);
        }
    }

    private static Vec3[] Corners(SimpleStepSolid solid) =>
    [
        new(solid.Min.X, solid.Min.Y, solid.Min.Z), new(solid.Max.X, solid.Min.Y, solid.Min.Z),
        new(solid.Max.X, solid.Max.Y, solid.Min.Z), new(solid.Min.X, solid.Max.Y, solid.Min.Z),
        new(solid.Min.X, solid.Min.Y, solid.Max.Z), new(solid.Max.X, solid.Min.Y, solid.Max.Z),
        new(solid.Max.X, solid.Max.Y, solid.Max.Z), new(solid.Min.X, solid.Max.Y, solid.Max.Z)
    ];

    private static Vec3 FaceCenter(SimpleStepSolid solid, SimpleFace face) => face switch
    {
        SimpleFace.XMin => new(solid.Min.X, solid.Center.Y, solid.Center.Z),
        SimpleFace.XMax => new(solid.Max.X, solid.Center.Y, solid.Center.Z),
        SimpleFace.YMin => new(solid.Center.X, solid.Min.Y, solid.Center.Z),
        SimpleFace.YMax => new(solid.Center.X, solid.Max.Y, solid.Center.Z),
        SimpleFace.ZMin => new(solid.Center.X, solid.Center.Y, solid.Min.Z),
        SimpleFace.ZMax => new(solid.Center.X, solid.Center.Y, solid.Max.Z),
        _ => solid.Center
    };

    private static void DrawFace(Graphics g, Color color, params PointF[] points)
    {
        using var brush = new SolidBrush(color);
        g.FillPolygon(brush, points);
    }

    private static void DrawStructuredMesh(Graphics g, PointF[] p, TetMesh mesh)
    {
        using var pen = new Pen(Color.FromArgb(120, 27, 45, 60), .65f);
        DrawFamily(p[0], p[1], p[3], p[2], mesh.DivisionsX);
        DrawFamily(p[4], p[5], p[7], p[6], mesh.DivisionsX);
        DrawFamily(p[0], p[3], p[1], p[2], mesh.DivisionsY);
        DrawFamily(p[4], p[7], p[5], p[6], mesh.DivisionsY);
        DrawFamily(p[0], p[4], p[1], p[5], mesh.DivisionsZ);
        DrawFamily(p[3], p[7], p[2], p[6], mesh.DivisionsZ);

        void DrawFamily(PointF a, PointF b, PointF c, PointF d, int divisions)
        {
            for (var index = 1; index < divisions; index++)
            {
                var t = index / (float)divisions;
                g.DrawLine(pen, Lerp(a, b, t), Lerp(c, d, t));
            }
        }
    }

    private static PointF Lerp(PointF a, PointF b, float t) => new(a.X + (b.X - a.X) * t, a.Y + (b.Y - a.Y) * t);

    private static void DrawSupport(Graphics g, PointF point)
    {
        using var pen = new Pen(Color.FromArgb(0, 161, 155), 2f);
        for (var index = -3; index <= 3; index++)
            g.DrawLine(pen, point.X - 5, point.Y + index * 7, point.X - 28, point.Y + index * 7 + 11);
        using var font = new Font("Segoe UI Semibold", 8.5f);
        g.DrawString("Fixed", font, Brushes.Teal, point.X - 38, point.Y - 34);
    }

    private static void DrawForce(Graphics g, PointF point, Vec3 force)
    {
        var magnitude = Math.Max(force.Length, 1e-9);
        var dx = (float)(force.X / magnitude * 72 + force.Y / magnitude * 26);
        var dy = (float)(-force.Z / magnitude * 72 - force.X / magnitude * 14);
        if (Math.Abs(dx) + Math.Abs(dy) < 15) dx = 65;
        using var pen = new Pen(Color.FromArgb(218, 49, 49), 3f) { EndCap = LineCap.ArrowAnchor };
        g.DrawLine(pen, point.X - dx, point.Y - dy, point.X, point.Y);
        using var font = new Font("Segoe UI Semibold", 8.5f);
        g.DrawString($"F = {force.Length:0.###} N", font, Brushes.Firebrick, point.X - dx - 20, point.Y - dy - 23);
    }

    private void DrawDimensions(Graphics g, SimpleStepSolid solid)
    {
        using var font = new Font("Segoe UI", 8.3f);
        var brush = _darkTheme ? Brushes.Gainsboro : Brushes.DarkSlateGray;
        g.DrawString($"X = {solid.LengthX:0.###} mm", font, brush, 18, ClientSize.Height - 66);
        g.DrawString($"Y = {solid.LengthY:0.###} mm", font, brush, 18, ClientSize.Height - 47);
        g.DrawString($"Z = {solid.LengthZ:0.###} mm", font, brush, 18, ClientSize.Height - 28);
    }

    private void DrawTriad(Graphics g)
    {
        var origin = new PointF(ClientSize.Width - 74, ClientSize.Height - 57);
        using var x = new Pen(Color.IndianRed, 2f) { EndCap = LineCap.ArrowAnchor };
        using var y = new Pen(Color.ForestGreen, 2f) { EndCap = LineCap.ArrowAnchor };
        using var z = new Pen(Color.RoyalBlue, 2f) { EndCap = LineCap.ArrowAnchor };
        g.DrawLine(x, origin, new PointF(origin.X + 38, origin.Y));
        g.DrawLine(z, origin, new PointF(origin.X, origin.Y - 38));
        g.DrawLine(y, origin, new PointF(origin.X - 25, origin.Y + 22));
        using var font = new Font("Segoe UI Semibold", 7.5f);
        g.DrawString("X", font, Brushes.IndianRed, origin.X + 40, origin.Y - 7);
        g.DrawString("Z", font, Brushes.RoyalBlue, origin.X - 5, origin.Y - 52);
        g.DrawString("Y", font, Brushes.ForestGreen, origin.X - 37, origin.Y + 19);
    }

    private void DrawOverlay(Graphics g)
    {
        var rectangle = new RectangleF(14, 14, Math.Min(470, ClientSize.Width - 28), 62);
        using var panel = new SolidBrush(_darkTheme ? Color.FromArgb(175, 10, 13, 17) : Color.FromArgb(222, 255, 255, 255));
        g.FillRectangle(panel, rectangle);
        using var title = new Font("Segoe UI Semibold", 10f);
        using var text = new Font("Segoe UI", 8.7f);
        var main = _darkTheme ? Brushes.White : Brushes.DarkSlateGray;
        var muted = _darkTheme ? Brushes.LightGray : Brushes.SlateGray;
        g.DrawString(Caption, title, main, 25, 22);
        g.DrawString(SubCaption, text, muted, 25, 47);
        g.DrawString("Ctrl + drag: rotate    Wheel: zoom    F7: fit", text, muted, ClientSize.Width / 2f - 125, ClientSize.Height - 24);
    }

    private void DrawLegend(Graphics g)
    {
        var rectangle = new Rectangle(ClientSize.Width - 128, 92, 24, Math.Max(145, ClientSize.Height / 3));
        using var gradient = new LinearGradientBrush(rectangle, Color.Red, Color.Blue, 90f)
        {
            InterpolationColors = new ColorBlend
            {
                Colors = [Color.Red, Color.Orange, Color.Yellow, Color.LimeGreen, Color.Cyan, Color.Blue],
                Positions = [0f, .2f, .4f, .6f, .8f, 1f]
            }
        };
        g.FillRectangle(gradient, rectangle);
        g.DrawRectangle(Pens.DimGray, rectangle);
        using var font = new Font("Segoe UI", 8f);
        var brush = _darkTheme ? Brushes.White : Brushes.DarkSlateGray;
        g.DrawString($"{_solution?.MaxVonMisesMpa:0.###}", font, brush, rectangle.Right + 5, rectangle.Top - 3);
        g.DrawString("0", font, brush, rectangle.Right + 5, rectangle.Bottom - 11);
        g.DrawString("MPa", font, brush, rectangle.Right - 3, rectangle.Bottom + 5);
    }

    private static void DrawCentered(Graphics g, string value, Font font, Brush brush, RectangleF rectangle)
    {
        using var format = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
        g.DrawString(value, font, brush, rectangle, format);
    }

    private static Color Blend(Color first, Color second, double fraction)
    {
        fraction = Math.Clamp(fraction, 0, 1);
        return Color.FromArgb(
            (int)(first.R + (second.R - first.R) * fraction),
            (int)(first.G + (second.G - first.G) * fraction),
            (int)(first.B + (second.B - first.B) * fraction));
    }
}
