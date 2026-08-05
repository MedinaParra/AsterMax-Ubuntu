using System.Diagnostics;
using System.Reflection;
using System.Runtime.CompilerServices;

namespace AsterMax.MechanicalGui;

internal static class CadViewerQualityBootstrap
{
    private static readonly ConditionalWeakTable<SelectableCadMeshCanvas, AdvancedCadViewport> Viewers = new();
    private static readonly Dictionary<Form, DateTime> ProgressStarted = new();
    private static readonly System.Windows.Forms.Timer Monitor = new() { Interval = 250 };

    [ModuleInitializer]
    internal static void Install()
    {
        Monitor.Tick += (_, _) => Tick();
        Monitor.Start();
    }

    private static void Tick()
    {
        foreach (Form form in Application.OpenForms.Cast<Form>().ToArray())
            foreach (var legacy in Descendants(form).OfType<SelectableCadMeshCanvas>().ToArray())
                EnsureAdvancedViewer(legacy);
        CloseCompletedOrStalledProgressWindows();
    }

    private static void EnsureAdvancedViewer(SelectableCadMeshCanvas legacy)
    {
        if (legacy.IsDisposed || legacy.Parent is null) return;
        if (!Viewers.TryGetValue(legacy, out var viewer))
        {
            viewer = new AdvancedCadViewport(legacy) { Dock = DockStyle.Fill };
            legacy.Controls.Add(viewer);
            viewer.BringToFront();
            Viewers.Add(legacy, viewer);
        }
        viewer.Visible = legacy.Visible;
        viewer.SyncFromLegacy();
    }

    private static IEnumerable<Control> Descendants(Control root)
    {
        foreach (Control child in root.Controls)
        {
            yield return child;
            foreach (var nested in Descendants(child)) yield return nested;
        }
    }

    private static void CloseCompletedOrStalledProgressWindows()
    {
        var mechanical = Application.OpenForms.Cast<Form>().OfType<MechanicalForm>().FirstOrDefault();
        var previewReady = mechanical is not null && GetField<CadMesh>(mechanical, "_cadSurfacePreview") is not null;
        var busy = mechanical is not null && GetField<bool>(mechanical, "_busy");

        foreach (Form form in Application.OpenForms.Cast<Form>().ToArray())
        {
            if (form is MechanicalForm || form.IsDisposed) continue;
            var text = string.Join(" ", Descendants(form).OfType<Label>().Select(label => label.Text));
            var stepProgress = text.Contains("Importing STEP", StringComparison.OrdinalIgnoreCase) ||
                               text.Contains("Reading topology", StringComparison.OrdinalIgnoreCase);
            if (!stepProgress) continue;
            if (!ProgressStarted.TryGetValue(form, out var started)) ProgressStarted[form] = started = DateTime.UtcNow;

            if (previewReady && !busy)
            {
                form.BeginInvoke(form.Close);
                ProgressStarted.Remove(form);
                continue;
            }

            if (DateTime.UtcNow - started > TimeSpan.FromSeconds(90))
            {
                KillBundledGmshProcesses();
                form.BeginInvoke(form.Close);
                ProgressStarted.Remove(form);
                if (mechanical is not null)
                    mechanical.BeginInvoke(() => MessageBox.Show(mechanical,
                        "La importación STEP excedió 90 segundos y fue cancelada automáticamente. Revise que el sólido esté cerrado o simplifique detalles extremadamente pequeños.",
                        "Importación STEP cancelada", MessageBoxButtons.OK, MessageBoxIcon.Warning));
            }
        }
    }

    private static void KillBundledGmshProcesses()
    {
        foreach (var process in Process.GetProcessesByName("gmsh"))
        {
            try
            {
                var path = process.MainModule?.FileName ?? string.Empty;
                if (path.Contains("AsterMax", StringComparison.OrdinalIgnoreCase) || path.Contains(Path.Combine("tools", "gmsh"), StringComparison.OrdinalIgnoreCase))
                    process.Kill(true);
            }
            catch { }
            finally { process.Dispose(); }
        }
    }

    internal static T? GetField<T>(object instance, string name)
    {
        var field = instance.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
        return field is null ? default : (T?)field.GetValue(instance);
    }
}

internal sealed class AdvancedCadViewport : Control
{
    private readonly SelectableCadMeshCanvas _legacy;
    private readonly Action<CadSurfaceSelection>? _selectionCallback;
    private CadMesh? _mesh;
    private CadSurfaceTopology? _topology;
    private HashSet<int> _supportTags = new();
    private HashSet<int> _loadTags = new();
    private int? _selectedTag;
    private bool _volumeMesh;
    private bool _showMesh;
    private double _yaw = -0.65;
    private double _pitch = 0.38;
    private double _zoom = 1.0;
    private PointF _pan;
    private Point _last;
    private DragMode _dragMode;
    private readonly List<HitTriangle> _hits = new();
    private Rectangle _cubeBounds;
    private Rectangle _meshButtonBounds;

    public AdvancedCadViewport(SelectableCadMeshCanvas legacy)
    {
        _legacy = legacy;
        DoubleBuffered = true;
        BackColor = Color.FromArgb(234, 241, 248);
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer, true);
        _selectionCallback = CadViewerQualityBootstrap.GetField<Action<CadSurfaceSelection>>(legacy, "_selectionCallback");
        TabStop = true;
    }

    public void SyncFromLegacy()
    {
        var mesh = CadViewerQualityBootstrap.GetField<CadMesh>(_legacy, "_mesh");
        var topology = CadViewerQualityBootstrap.GetField<CadSurfaceTopology>(_legacy, "_topology");
        var volume = CadViewerQualityBootstrap.GetField<bool>(_legacy, "_volumeMesh");
        var selected = CadViewerQualityBootstrap.GetField<int?>(_legacy, "_selectedFaceTag");
        var supports = CadViewerQualityBootstrap.GetField<HashSet<int>>(_legacy, "_supportFaceTags") ?? new();
        var loads = CadViewerQualityBootstrap.GetField<HashSet<int>>(_legacy, "_loadFaceTags") ?? new();
        var changed = !ReferenceEquals(mesh, _mesh) || volume != _volumeMesh;
        _mesh = mesh; _topology = topology; _volumeMesh = volume; _selectedTag = selected; _supportTags = supports; _loadTags = loads;
        if (changed) { _showMesh = volume; Fit(); }
        Invalidate();
    }

    protected override void OnMouseWheel(MouseEventArgs e)
    {
        base.OnMouseWheel(e);
        _zoom = Math.Clamp(_zoom * (e.Delta > 0 ? 1.12 : 1 / 1.12), 0.08, 18.0);
        Invalidate();
    }

    protected override void OnMouseDown(MouseEventArgs e)
    {
        base.OnMouseDown(e);
        Focus(); _last = e.Location;
        if (_cubeBounds.Contains(e.Location) && e.Button == MouseButtons.Left) { ApplyCubeView(e.Location); return; }
        if (_meshButtonBounds.Contains(e.Location) && e.Button == MouseButtons.Left) { _showMesh = !_showMesh; Invalidate(); return; }
        _dragMode = e.Button switch
        {
            MouseButtons.Right => DragMode.Pan,
            MouseButtons.Middle when ModifierKeys.HasFlag(Keys.Shift) => DragMode.Pan,
            MouseButtons.Middle => DragMode.Orbit,
            MouseButtons.Left when ModifierKeys.HasFlag(Keys.Control) => DragMode.Orbit,
            _ => DragMode.None
        };
        if (_dragMode != DragMode.None) Capture = true;
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        var dx = e.X - _last.X; var dy = e.Y - _last.Y;
        if (_dragMode == DragMode.Orbit)
        {
            _yaw += dx * 0.009; _pitch = Math.Clamp(_pitch + dy * 0.009, -Math.PI * 0.495, Math.PI * 0.495); _last = e.Location; Invalidate();
        }
        else if (_dragMode == DragMode.Pan)
        {
            _pan = new PointF(_pan.X + dx, _pan.Y + dy); _last = e.Location; Invalidate();
        }
    }

    protected override void OnMouseUp(MouseEventArgs e)
    {
        base.OnMouseUp(e);
        var wasDragging = _dragMode != DragMode.None; _dragMode = DragMode.None; Capture = false;
        if (!wasDragging && e.Button == MouseButtons.Left && !_cubeBounds.Contains(e.Location) && !_meshButtonBounds.Contains(e.Location)) SelectAt(e.Location);
    }

    protected override void OnDoubleClick(EventArgs e) { Fit(); base.OnDoubleClick(e); }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics; g.SmoothingMode = SmoothingMode.AntiAlias;
        using var background = new LinearGradientBrush(ClientRectangle, Color.White, Color.FromArgb(218, 231, 243), 90f);
        g.FillRectangle(background, ClientRectangle); DrawFloor(g); _hits.Clear();
        if (_mesh is null || _topology is null) return;

        var center = (_mesh.Min + _mesh.Max) / 2.0; var size = _mesh.Max - _mesh.Min;
        var maximum = Math.Max(size.X, Math.Max(size.Y, size.Z));
        var scale = Math.Min(ClientSize.Width, ClientSize.Height) * 0.62 * _zoom / Math.Max(maximum, 1e-9);
        var cy = Math.Cos(_yaw); var sy = Math.Sin(_yaw); var cp = Math.Cos(_pitch); var sp = Math.Sin(_pitch);

        (PointF Point, double Depth, Vec3 NormalView) Project(Vec3 original, Vec3 normal)
        {
            var p = original - center; var x1 = p.X * cy - p.Y * sy; var y1 = p.X * sy + p.Y * cy; var z1 = p.Z;
            var y2 = y1 * cp - z1 * sp; var z2 = y1 * sp + z1 * cp;
            var nx1 = normal.X * cy - normal.Y * sy; var ny1 = normal.X * sy + normal.Y * cy; var nz1 = normal.Z;
            var ny2 = ny1 * cp - nz1 * sp; var nz2 = ny1 * sp + nz1 * cp;
            return (new PointF((float)(ClientSize.Width * 0.5 + _pan.X + x1 * scale), (float)(ClientSize.Height * 0.51 + _pan.Y - z2 * scale)), y2, new Vec3(nx1, ny2, nz2));
        }

        var rendered = new List<RenderTriangle>(_mesh.SurfaceTriangles.Count);
        for (var i = 0; i < _mesh.SurfaceTriangles.Count; i++)
        {
            var tri = _mesh.SurfaceTriangles[i]; var a = _mesh.Nodes[tri[0]]; var b = _mesh.Nodes[tri[1]]; var c = _mesh.Nodes[tri[2]];
            var normal = Normalize(Cross(b - a, c - a)); var pa = Project(a, normal); var pb = Project(b, normal); var pc3 = Project(c, normal);
            rendered.Add(new RenderTriangle(_topology.TriangleFaceTags[i], new[] { pa.Point, pb.Point, pc3.Point }, (pa.Depth + pb.Depth + pc3.Depth) / 3.0, pa.NormalView));
        }
        rendered.Sort((a, b) => a.Depth.CompareTo(b.Depth));
        var light = Normalize(new Vec3(-0.35, -0.55, 0.76)); var edgeStride = Math.Max(1, rendered.Count / 45000);
        using var meshPen = new Pen(Color.FromArgb(95, 31, 57, 76), 0.55f);

        for (var index = 0; index < rendered.Count; index++)
        {
            var item = rendered[index]; var illumination = Math.Clamp(0.42 + 0.58 * Math.Abs(Dot(item.NormalView, light)), 0.30, 1.0);
            var color = Shade(Color.FromArgb(78, 164, 211), illumination);
            if (_supportTags.Contains(item.FaceTag)) color = Blend(color, Color.FromArgb(0, 172, 160), 0.58);
            if (_loadTags.Contains(item.FaceTag)) color = Blend(color, Color.FromArgb(220, 63, 63), 0.58);
            if (_selectedTag == item.FaceTag) color = Blend(color, Color.FromArgb(255, 188, 44), 0.67);
            using var brush = new SolidBrush(color); g.FillPolygon(brush, item.Points);
            if (_volumeMesh && _showMesh && index % edgeStride == 0) g.DrawPolygon(meshPen, item.Points);
            _hits.Add(new HitTriangle(item.FaceTag, item.Points, item.Depth));
        }
        DrawHeader(g); DrawNavigationCube(g); DrawMeshButton(g);
    }

    private void DrawHeader(Graphics g)
    {
        if (_mesh is null) return;
        using var panel = new SolidBrush(Color.FromArgb(226, 255, 255, 255));
        g.FillRectangle(panel, new Rectangle(14, 14, Math.Min(735, Math.Max(260, Width - 170)), 78));
        using var title = new Font("Segoe UI Semibold", 10.5f); using var text = new Font("Segoe UI", 8.4f);
        g.DrawString(_volumeMesh ? "Geometría CAD + superposición de malla" : "Geometría CAD suavizada", title, Brushes.DarkSlateGray, 27, 24);
        g.DrawString($"{_mesh.Nodes.Count:N0} nodos · {_mesh.SurfaceTriangles.Count:N0} caras de visualización · {_mesh.Tetrahedra.Count:N0} TET4", text, Brushes.SlateGray, 27, 48);
        g.DrawString("Rotar: botón central/Ctrl+arrastrar · Desplazar: botón derecho · Zoom: rueda · Ajustar: doble clic", text, Brushes.SlateGray, 27, 66);
    }

    private void DrawMeshButton(Graphics g)
    {
        _meshButtonBounds = new Rectangle(Width - 126, 126, 104, 30);
        using var brush = new SolidBrush(_showMesh ? Color.FromArgb(32, 122, 183) : Color.FromArgb(242, 247, 251));
        using var border = new Pen(Color.FromArgb(82, 111, 132));
        g.FillRectangle(brush, _meshButtonBounds); g.DrawRectangle(border, _meshButtonBounds);
        using var font = new Font("Segoe UI Semibold", 8.5f);
        g.DrawString(_showMesh ? "Ocultar malla" : "Mostrar malla", font, _showMesh ? Brushes.White : Brushes.DarkSlateGray, _meshButtonBounds.X + 9, _meshButtonBounds.Y + 7);
    }

    private void DrawNavigationCube(Graphics g)
    {
        _cubeBounds = new Rectangle(Width - 132, 18, 108, 98); var center = new PointF(_cubeBounds.Left + 54, _cubeBounds.Top + 49);
        var top = new[] { new PointF(center.X, center.Y - 34), new PointF(center.X + 36, center.Y - 15), new PointF(center.X, center.Y + 4), new PointF(center.X - 36, center.Y - 15) };
        var left = new[] { top[3], top[2], new PointF(center.X, center.Y + 43), new PointF(center.X - 36, center.Y + 24) };
        var right = new[] { top[2], top[1], new PointF(center.X + 36, center.Y + 24), new PointF(center.X, center.Y + 43) };
        using var topBrush = new SolidBrush(Color.FromArgb(241, 246, 250)); using var leftBrush = new SolidBrush(Color.FromArgb(207, 221, 233)); using var rightBrush = new SolidBrush(Color.FromArgb(224, 235, 243)); using var border = new Pen(Color.FromArgb(74, 99, 118), 1.1f);
        g.FillPolygon(topBrush, top); g.FillPolygon(leftBrush, left); g.FillPolygon(rightBrush, right); g.DrawPolygon(border, top); g.DrawPolygon(border, left); g.DrawPolygon(border, right);
        using var font = new Font("Segoe UI Semibold", 7.6f);
        g.DrawString("TOP", font, Brushes.DarkSlateGray, center.X - 14, center.Y - 21); g.DrawString("FRONT", font, Brushes.DarkSlateGray, center.X - 31, center.Y + 15); g.DrawString("RIGHT", font, Brushes.DarkSlateGray, center.X + 5, center.Y + 15);
    }

    private void ApplyCubeView(Point location)
    {
        var localX = location.X - _cubeBounds.Left; var localY = location.Y - _cubeBounds.Top;
        if (localY < 45) { _yaw = 0; _pitch = Math.PI / 2 - 0.001; }
        else if (localX < 54) { _yaw = 0; _pitch = 0; }
        else { _yaw = -Math.PI / 2; _pitch = 0; }
        _pan = PointF.Empty; Invalidate();
    }

    private void SelectAt(Point point)
    {
        var hit = _hits.Where(item => PointInTriangle(point, item.Points[0], item.Points[1], item.Points[2])).OrderBy(item => item.Depth).LastOrDefault();
        if (hit is null || _topology is null || !_topology.Faces.TryGetValue(hit.FaceTag, out var face)) return;
        _selectedTag = face.Tag;
        _legacy.GetType().GetField("_selectedFaceTag", BindingFlags.Instance | BindingFlags.NonPublic)?.SetValue(_legacy, face.Tag);
        _selectionCallback?.Invoke(new CadSurfaceSelection(face.Tag, face.TriangleIndices.Count, face.NodeIndices.Count, face.Centroid, face.Normal, face.AreaMm2));
        Invalidate();
    }

    private void Fit() { _zoom = 1.0; _pan = PointF.Empty; Invalidate(); }
    private void DrawFloor(Graphics g)
    {
        using var pen = new Pen(Color.FromArgb(34, 91, 120, 145), 0.7f); var horizon = Height * 0.78f;
        for (var i = -14; i <= 14; i++) { var x = Width / 2f + i * 46f; g.DrawLine(pen, x, horizon - 60, x + i * 8, Height); }
        for (var row = 0; row < 8; row++) { var y = horizon + row * row * 4.2f; g.DrawLine(pen, 0, y, Width, y); }
    }

    private static Vec3 Cross(Vec3 a, Vec3 b) => new(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X);
    private static double Dot(Vec3 a, Vec3 b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;
    private static Vec3 Normalize(Vec3 value) => value.Length <= 1e-20 ? new Vec3(0, 0, 1) : value / value.Length;
    private static Color Shade(Color color, double factor) => Color.FromArgb(color.A, (int)Math.Clamp(color.R * factor, 0, 255), (int)Math.Clamp(color.G * factor, 0, 255), (int)Math.Clamp(color.B * factor, 0, 255));
    private static Color Blend(Color a, Color b, double t) => Color.FromArgb((int)(a.R + (b.R - a.R) * t), (int)(a.G + (b.G - a.G) * t), (int)(a.B + (b.B - a.B) * t));
    private static bool PointInTriangle(Point p, PointF a, PointF b, PointF c)
    {
        static float Sign(PointF p1, PointF p2, PointF p3) => (p1.X - p3.X) * (p2.Y - p3.Y) - (p2.X - p3.X) * (p1.Y - p3.Y);
        var q = new PointF(p.X, p.Y); var d1 = Sign(q, a, b); var d2 = Sign(q, b, c); var d3 = Sign(q, c, a);
        return !((d1 < 0 || d2 < 0 || d3 < 0) && (d1 > 0 || d2 > 0 || d3 > 0));
    }

    private enum DragMode { None, Orbit, Pan }
    private sealed record RenderTriangle(int FaceTag, PointF[] Points, double Depth, Vec3 NormalView);
    private sealed record HitTriangle(int FaceTag, PointF[] Points, double Depth);
}
