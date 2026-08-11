namespace AsterMax.MechanicalGui;

/// <summary>
/// Responsive WinForms CAD preview designed for large STEP assemblies.
///
/// The complete CadMesh/topology is retained for meshing and scoping. Rendering is capped
/// to a representative triangle subset so repainting the window cannot monopolize the UI
/// thread. At least one triangle per CAD face is retained whenever the face count fits the
/// render budget, which keeps face picking useful even on large assemblies.
/// </summary>
internal sealed class ResponsiveCadMeshCanvas : Control
{
    private const int MaxDisplayTriangles = 24000;

    private readonly Action<CadSurfaceSelection> _selectionCallback;
    private SimpleStepSolid? _envelope;
    private CadMesh? _mesh;
    private CadSurfaceTopology? _topology;
    private bool _volumeMesh;
    private float _zoom = 1f;
    private float _yaw = -.55f;
    private float _pitch = .45f;
    private float _panX;
    private float _panY;
    private Point _last;
    private bool _orbiting;
    private bool _panning;
    private int? _selectedFaceTag;
    private HashSet<int> _supportFaceTags = new();
    private HashSet<int> _loadFaceTags = new();

    private int[] _renderTriangleIndices = Array.Empty<int>();
    private int[] _renderNodeIndices = Array.Empty<int>();
    private Dictionary<int, int> _renderNodeMap = new();
    private PointF[] _projectedPoints = Array.Empty<PointF>();
    private float[] _projectedDepths = Array.Empty<float>();
    private readonly List<ProjectedTriangle> _projectedTriangles = new();

    public ResponsiveCadMeshCanvas(Action<CadSurfaceSelection> selectionCallback)
    {
        _selectionCallback = selectionCallback;
        DoubleBuffered = true;
        ResizeRedraw = true;
        BackColor = Color.FromArgb(236, 242, 248);
        TabStop = true;

        MouseWheel += (_, eventArgs) =>
        {
            _zoom = Math.Clamp(_zoom * (eventArgs.Delta > 0 ? 1.10f : .90f), .05f, 20f);
            Invalidate();
        };

        MouseDown += (_, eventArgs) =>
        {
            Focus();
            var shift = ModifierKeys.HasFlag(Keys.Shift);
            if (eventArgs.Button == MouseButtons.Right || eventArgs.Button == MouseButtons.Middle && shift)
            {
                _panning = true;
                _last = eventArgs.Location;
                Cursor = Cursors.SizeAll;
                return;
            }

            if (eventArgs.Button == MouseButtons.Middle ||
                eventArgs.Button == MouseButtons.Left && ModifierKeys.HasFlag(Keys.Control))
            {
                _orbiting = true;
                _last = eventArgs.Location;
                Cursor = Cursors.Hand;
            }
        };

        MouseMove += (_, eventArgs) =>
        {
            if (_orbiting)
            {
                var dx = eventArgs.X - _last.X;
                var dy = eventArgs.Y - _last.Y;
                _yaw = NormalizeAngle(_yaw + dx * .0105f);
                _pitch = NormalizeAngle(_pitch + dy * .0105f);
                _last = eventArgs.Location;
                Invalidate();
                return;
            }

            if (_panning)
            {
                _panX += eventArgs.X - _last.X;
                _panY += eventArgs.Y - _last.Y;
                _last = eventArgs.Location;
                Invalidate();
            }
        };

        MouseUp += (_, _) =>
        {
            _orbiting = false;
            _panning = false;
            Cursor = Cursors.Default;
        };

        MouseClick += (_, eventArgs) =>
        {
            if (eventArgs.Button != MouseButtons.Left || ModifierKeys.HasFlag(Keys.Control)) return;
            SelectAt(eventArgs.Location);
        };
    }

    public void SetMesh(SimpleStepSolid envelope, CadMesh mesh, bool volumeMesh)
    {
        _envelope = envelope;
        _mesh = mesh;
        _topology = CadTopologyRegistry.Get(mesh);
        _volumeMesh = volumeMesh;
        _zoom = 1f;
        _yaw = -.55f;
        _pitch = .45f;
        _panX = 0;
        _panY = 0;
        _selectedFaceTag = null;
        BuildRenderSubset();
        Visible = true;
        Invalidate();
    }

    public void ClearModel()
    {
        _envelope = null;
        _mesh = null;
        _topology = null;
        _selectedFaceTag = null;
        _supportFaceTags.Clear();
        _loadFaceTags.Clear();
        _renderTriangleIndices = Array.Empty<int>();
        _renderNodeIndices = Array.Empty<int>();
        _renderNodeMap.Clear();
        _projectedPoints = Array.Empty<PointF>();
        _projectedDepths = Array.Empty<float>();
        _projectedTriangles.Clear();
        Visible = false;
        Invalidate();
    }

    public void SetView(float yaw, float pitch, float zoom, bool resetPan = true)
    {
        _yaw = NormalizeAngle(yaw);
        _pitch = NormalizeAngle(pitch);
        _zoom = Math.Clamp(zoom, .05f, 20f);
        if (resetPan)
        {
            _panX = 0;
            _panY = 0;
        }
        Invalidate();
    }

    public void FitView() => SetView(-.55f, .45f, 1f);

    public void SetScopeMarkers(IEnumerable<int> supportTags, IEnumerable<int> loadTags)
    {
        _supportFaceTags = supportTags.ToHashSet();
        _loadFaceTags = loadTags.ToHashSet();
        Invalidate();
    }

    public void SelectSurface(int? tag)
    {
        _selectedFaceTag = tag;
        Invalidate();
    }

    private void BuildRenderSubset()
    {
        if (_mesh is null || _topology is null)
        {
            _renderTriangleIndices = Array.Empty<int>();
            _renderNodeIndices = Array.Empty<int>();
            _renderNodeMap.Clear();
            _projectedPoints = Array.Empty<PointF>();
            _projectedDepths = Array.Empty<float>();
            return;
        }

        var total = _mesh.SurfaceTriangles.Count;
        if (total <= MaxDisplayTriangles)
        {
            _renderTriangleIndices = Enumerable.Range(0, total).ToArray();
        }
        else
        {
            var chosen = new HashSet<int>();

            // Preserve one representative triangle per selectable CAD face first.
            foreach (var face in _topology.Faces.Values.OrderBy(face => face.Tag))
            {
                if (face.TriangleIndices.Count == 0) continue;
                chosen.Add(face.TriangleIndices[0]);
                if (chosen.Count >= MaxDisplayTriangles) break;
            }

            if (chosen.Count < MaxDisplayTriangles)
            {
                var remaining = MaxDisplayTriangles - chosen.Count;
                var stride = Math.Max(1, (int)Math.Ceiling(total / (double)Math.Max(remaining, 1)));
                for (var index = 0; index < total && chosen.Count < MaxDisplayTriangles; index += stride)
                    chosen.Add(index);
            }

            _renderTriangleIndices = chosen.OrderBy(index => index).ToArray();
        }

        _renderNodeIndices = _renderTriangleIndices
            .SelectMany(index => _mesh.SurfaceTriangles[index])
            .Distinct()
            .OrderBy(index => index)
            .ToArray();
        _renderNodeMap = _renderNodeIndices
            .Select((globalIndex, compactIndex) => (globalIndex, compactIndex))
            .ToDictionary(item => item.globalIndex, item => item.compactIndex);
        _projectedPoints = new PointF[_renderNodeIndices.Length];
        _projectedDepths = new float[_renderNodeIndices.Length];
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var graphics = e.Graphics;
        using var background = new LinearGradientBrush(ClientRectangle, Color.White, Color.FromArgb(216, 229, 241), 90f);
        graphics.FillRectangle(background, ClientRectangle);
        DrawFloor(graphics);
        _projectedTriangles.Clear();

        if (_mesh is null || _envelope is null || _topology is null || _renderTriangleIndices.Length == 0)
        {
            DrawTriad(graphics);
            return;
        }

        var center = (_mesh.Min + _mesh.Max) / 2.0;
        var dimensions = _mesh.Max - _mesh.Min;
        var maximum = Math.Max(dimensions.X, Math.Max(dimensions.Y, dimensions.Z));
        var scale = Math.Min(ClientSize.Width, ClientSize.Height) * .62f * _zoom / Math.Max(maximum, 1e-9);
        var cy = MathF.Cos(_yaw);
        var sy = MathF.Sin(_yaw);
        var cp = MathF.Cos(_pitch);
        var sp = MathF.Sin(_pitch);

        for (var compact = 0; compact < _renderNodeIndices.Length; compact++)
        {
            var original = _mesh.Nodes[_renderNodeIndices[compact]];
            var point = original - center;
            var x = (float)point.X;
            var y = (float)point.Y;
            var z = (float)point.Z;

            // Yaw around global Z, then pitch around camera X. Unlike the old preview,
            // vertical mouse movement therefore changes the camera elevation freely.
            var x1 = x * cy - y * sy;
            var y1 = x * sy + y * cy;
            var y2 = y1 * cp - z * sp;
            var z2 = y1 * sp + z * cp;

            _projectedPoints[compact] = new PointF(
                ClientSize.Width * .50f + _panX + x1 * (float)scale,
                ClientSize.Height * .52f + _panY - z2 * (float)scale);
            _projectedDepths[compact] = y2;
        }

        foreach (var triangleIndex in _renderTriangleIndices)
        {
            var triangle = _mesh.SurfaceTriangles[triangleIndex];
            var a = _renderNodeMap[triangle[0]];
            var b = _renderNodeMap[triangle[1]];
            var c = _renderNodeMap[triangle[2]];
            _projectedTriangles.Add(new ProjectedTriangle(
                triangleIndex,
                _topology.TriangleFaceTags[triangleIndex],
                new[] { _projectedPoints[a], _projectedPoints[b], _projectedPoints[c] },
                (_projectedDepths[a] + _projectedDepths[b] + _projectedDepths[c]) / 3f));
        }

        _projectedTriangles.Sort((first, second) => first.Depth.CompareTo(second.Depth));
        graphics.SmoothingMode = _projectedTriangles.Count <= 12000 ? SmoothingMode.AntiAlias : SmoothingMode.HighSpeed;
        var edgeStride = Math.Max(1, (int)Math.Ceiling(_projectedTriangles.Count / 12000.0));
        using var edge = new Pen(Color.FromArgb(_volumeMesh ? 52 : 68, 24, 58, 82), _volumeMesh ? .45f : .55f);

        for (var index = 0; index < _projectedTriangles.Count; index++)
        {
            var item = _projectedTriangles[index];
            var normalized = maximum <= 1e-12 ? .5 : Math.Clamp((item.Depth + maximum / 2) / maximum, 0, 1);
            var color = Blend(Color.FromArgb(52, 142, 199), Color.FromArgb(156, 211, 235), normalized);
            using var brush = new SolidBrush(color);
            graphics.FillPolygon(brush, item.Points);
            if (index % edgeStride == 0) graphics.DrawPolygon(edge, item.Points);
        }

        DrawAssignedAndSelectedFaces(graphics, _projectedTriangles);
        DrawHeader(graphics);
        DrawTriad(graphics);
    }

    private void DrawAssignedAndSelectedFaces(Graphics graphics, IReadOnlyList<ProjectedTriangle> triangles)
    {
        foreach (var item in triangles)
        {
            Color? overlay = null;
            if (_selectedFaceTag == item.FaceTag) overlay = Color.FromArgb(195, 255, 183, 48);
            else if (_supportFaceTags.Contains(item.FaceTag)) overlay = Color.FromArgb(170, 0, 166, 160);
            else if (_loadFaceTags.Contains(item.FaceTag)) overlay = Color.FromArgb(170, 218, 61, 61);
            if (overlay is null) continue;
            using var brush = new SolidBrush(overlay.Value);
            graphics.FillPolygon(brush, item.Points);
        }

        using var selectedEdge = new Pen(Color.FromArgb(245, 123, 75, 0), 1.55f);
        if (_selectedFaceTag is int selected)
            foreach (var item in triangles.Where(item => item.FaceTag == selected))
                graphics.DrawPolygon(selectedEdge, item.Points);
    }

    private void SelectAt(Point location)
    {
        if (_mesh is null || _topology is null) return;
        var hit = _projectedTriangles
            .Where(item => PointInTriangle(location, item.Points[0], item.Points[1], item.Points[2]))
            .OrderBy(item => item.Depth)
            .LastOrDefault();
        if (hit is null || !_topology.Faces.TryGetValue(hit.FaceTag, out var face)) return;

        _selectedFaceTag = face.Tag;
        Invalidate();
        _selectionCallback(new CadSurfaceSelection(
            face.Tag,
            face.TriangleIndices.Count,
            face.NodeIndices.Count,
            face.Centroid,
            face.Normal,
            face.AreaMm2));
    }

    private void DrawHeader(Graphics graphics)
    {
        if (_mesh is null || _envelope is null || _topology is null) return;
        using var panel = new SolidBrush(Color.FromArgb(232, 255, 255, 255));
        graphics.FillRectangle(panel, 14, 13, Math.Min(820, Math.Max(220, ClientSize.Width - 28)), 108);
        using var titleFont = new Font("Segoe UI Semibold", 11f);
        using var textFont = new Font("Segoe UI", 8.7f);
        graphics.DrawString(_volumeMesh ? "Gmsh exterior skin of volume mesh" : "OpenCASCADE STEP surface preview", titleFont, Brushes.DarkSlateGray, 26, 22);
        graphics.DrawString($"{_mesh.Nodes.Count:N0} nodes · {_mesh.SurfaceTriangles.Count:N0} triangles · {_mesh.Tetrahedra.Count:N0} TET4 · {_topology.Faces.Count:N0} selectable faces", textFont, Brushes.SlateGray, 26, 48);
        graphics.DrawString($"Envelope {_envelope.LengthX:0.###} × {_envelope.LengthY:0.###} × {_envelope.LengthZ:0.###} mm", textFont, Brushes.SlateGray, 26, 65);
        graphics.DrawString($"Interactive display: {_renderTriangleIndices.Length:N0}/{_mesh.SurfaceTriangles.Count:N0} triangles", textFont, Brushes.SlateGray, 26, 82);
        graphics.DrawString("Click: face · MMB/Ctrl+drag: free orbit · RMB/Shift+MMB: pan · Wheel: zoom", textFont, Brushes.SlateGray, 26, 99);
    }

    private void DrawFloor(Graphics graphics)
    {
        using var pen = new Pen(Color.FromArgb(36, 105, 130, 155), .7f);
        var horizon = ClientSize.Height * .78f;
        for (var index = -12; index <= 12; index++)
        {
            var x = ClientSize.Width / 2f + index * 48f;
            graphics.DrawLine(pen, x, horizon - 58, x + index * 10, ClientSize.Height);
        }
        for (var row = 0; row < 8; row++)
        {
            var y = horizon + row * row * 4.5f;
            graphics.DrawLine(pen, 0, y, ClientSize.Width, y);
        }
    }

    private void DrawTriad(Graphics graphics)
    {
        var origin = new PointF(ClientSize.Width - 72, ClientSize.Height - 60);
        var cy = MathF.Cos(_yaw);
        var sy = MathF.Sin(_yaw);
        var cp = MathF.Cos(_pitch);
        var sp = MathF.Sin(_pitch);

        PointF Axis(float x, float y, float z)
        {
            var x1 = x * cy - y * sy;
            var y1 = x * sy + y * cy;
            var z2 = y1 * sp + z * cp;
            return new PointF(origin.X + x1 * 34f, origin.Y - z2 * 34f);
        }

        using var red = new Pen(Color.FromArgb(210, 54, 54), 2f);
        using var green = new Pen(Color.FromArgb(38, 145, 74), 2f);
        using var blue = new Pen(Color.FromArgb(45, 93, 205), 2f);
        var xEnd = Axis(1, 0, 0);
        var yEnd = Axis(0, 1, 0);
        var zEnd = Axis(0, 0, 1);
        graphics.DrawLine(red, origin, xEnd);
        graphics.DrawLine(green, origin, yEnd);
        graphics.DrawLine(blue, origin, zEnd);
        using var font = new Font("Segoe UI", 8f);
        graphics.DrawString("X", font, Brushes.Firebrick, xEnd);
        graphics.DrawString("Y", font, Brushes.ForestGreen, yEnd);
        graphics.DrawString("Z", font, Brushes.RoyalBlue, zEnd);
    }

    private static float NormalizeAngle(float angle)
    {
        const float twoPi = MathF.PI * 2f;
        while (angle > MathF.PI) angle -= twoPi;
        while (angle < -MathF.PI) angle += twoPi;
        return angle;
    }

    private static bool PointInTriangle(Point point, PointF a, PointF b, PointF c)
    {
        static float Sign(PointF p1, PointF p2, PointF p3) =>
            (p1.X - p3.X) * (p2.Y - p3.Y) - (p2.X - p3.X) * (p1.Y - p3.Y);
        var p = new PointF(point.X, point.Y);
        var d1 = Sign(p, a, b);
        var d2 = Sign(p, b, c);
        var d3 = Sign(p, c, a);
        var hasNegative = d1 < 0 || d2 < 0 || d3 < 0;
        var hasPositive = d1 > 0 || d2 > 0 || d3 > 0;
        return !(hasNegative && hasPositive);
    }

    private static Color Blend(Color first, Color second, double amount)
    {
        amount = Math.Clamp(amount, 0, 1);
        return Color.FromArgb(
            (int)(first.R + (second.R - first.R) * amount),
            (int)(first.G + (second.G - first.G) * amount),
            (int)(first.B + (second.B - first.B) * amount));
    }

    private sealed record ProjectedTriangle(int TriangleIndex, int FaceTag, PointF[] Points, float Depth);
}
