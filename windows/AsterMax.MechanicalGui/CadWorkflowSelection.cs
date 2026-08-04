using System.Runtime.CompilerServices;

namespace AsterMax.MechanicalGui;

internal sealed record CadSurfaceFace(
    int Tag,
    IReadOnlyList<int> TriangleIndices,
    IReadOnlyList<int> NodeIndices,
    Vec3 Centroid,
    Vec3 Normal,
    double AreaMm2);

internal sealed class CadSurfaceTopology
{
    public required int[] TriangleFaceTags { get; init; }
    public required IReadOnlyDictionary<int, CadSurfaceFace> Faces { get; init; }
}

internal sealed record CadSurfaceSelection(
    int Tag,
    int TriangleCount,
    int NodeCount,
    Vec3 Centroid,
    Vec3 Normal,
    double AreaMm2);

internal static class CadTopologyRegistry
{
    private static readonly ConditionalWeakTable<CadMesh, CadSurfaceTopology> Table = new();

    public static void Register(CadMesh mesh, IReadOnlyList<int> sourceTags)
    {
        Table.Remove(mesh);
        Table.Add(mesh, Build(mesh, sourceTags));
    }

    public static CadSurfaceTopology Get(CadMesh mesh)
    {
        if (Table.TryGetValue(mesh, out var topology)) return topology;
        var fallback = Build(mesh, Enumerable.Repeat(0, mesh.SurfaceTriangles.Count).ToArray());
        Table.Add(mesh, fallback);
        return fallback;
    }

    private static CadSurfaceTopology Build(CadMesh mesh, IReadOnlyList<int> sourceTags)
    {
        var triangleCount = mesh.SurfaceTriangles.Count;
        var normals = new Vec3[triangleCount];
        var areas = new double[triangleCount];
        var centroids = new Vec3[triangleCount];
        for (var index = 0; index < triangleCount; index++)
        {
            var triangle = mesh.SurfaceTriangles[index];
            var a = mesh.Nodes[triangle[0]];
            var b = mesh.Nodes[triangle[1]];
            var c = mesh.Nodes[triangle[2]];
            var cross = Cross(b - a, c - a);
            var twiceArea = cross.Length;
            areas[index] = twiceArea * .5;
            normals[index] = twiceArea <= 1e-18 ? Vec3.Zero : cross / twiceArea;
            centroids[index] = (a + b + c) / 3.0;
        }

        var normalizedSourceTags = Enumerable.Range(0, triangleCount)
            .Select(index => index < sourceTags.Count ? sourceTags[index] : 0)
            .ToArray();
        var positiveTags = normalizedSourceTags.Where(tag => tag > 0).Distinct().ToArray();
        int[] faceTags;
        if (positiveTags.Length > 1)
        {
            faceTags = normalizedSourceTags;
            var next = positiveTags.Max() + 1;
            for (var index = 0; index < faceTags.Length; index++)
                if (faceTags[index] <= 0) faceTags[index] = next++;
        }
        else
        {
            faceTags = BuildSmoothConnectedFaceTags(mesh, normals);
        }

        var faces = new Dictionary<int, CadSurfaceFace>();
        foreach (var group in Enumerable.Range(0, triangleCount).GroupBy(index => faceTags[index]))
        {
            var triangleIndices = group.ToArray();
            var nodes = triangleIndices
                .SelectMany(index => mesh.SurfaceTriangles[index])
                .Distinct()
                .OrderBy(index => index)
                .ToArray();
            var area = triangleIndices.Sum(index => areas[index]);
            var centroid = area <= 1e-18
                ? triangleIndices.Aggregate(Vec3.Zero, (sum, index) => sum + centroids[index]) / Math.Max(triangleIndices.Length, 1)
                : triangleIndices.Aggregate(Vec3.Zero, (sum, index) => sum + centroids[index] * areas[index]) / area;
            var weightedNormal = triangleIndices.Aggregate(Vec3.Zero, (sum, index) => sum + normals[index] * areas[index]);
            var normal = weightedNormal.Length <= 1e-18 ? Vec3.Zero : weightedNormal / weightedNormal.Length;
            faces[group.Key] = new CadSurfaceFace(group.Key, triangleIndices, nodes, centroid, normal, area);
        }

        return new CadSurfaceTopology { TriangleFaceTags = faceTags, Faces = faces };
    }

    private static int[] BuildSmoothConnectedFaceTags(CadMesh mesh, IReadOnlyList<Vec3> normals)
    {
        var edgeOwners = new Dictionary<(int A, int B), List<int>>();
        for (var triangleIndex = 0; triangleIndex < mesh.SurfaceTriangles.Count; triangleIndex++)
        {
            var triangle = mesh.SurfaceTriangles[triangleIndex];
            AddEdge(triangle[0], triangle[1], triangleIndex);
            AddEdge(triangle[1], triangle[2], triangleIndex);
            AddEdge(triangle[2], triangle[0], triangleIndex);
        }

        var neighbours = Enumerable.Range(0, mesh.SurfaceTriangles.Count).Select(_ => new List<int>()).ToArray();
        foreach (var owners in edgeOwners.Values)
        {
            if (owners.Count != 2) continue;
            neighbours[owners[0]].Add(owners[1]);
            neighbours[owners[1]].Add(owners[0]);
        }

        var tags = new int[mesh.SurfaceTriangles.Count];
        var nextTag = 1;
        var cosineLimit = Math.Cos(30.0 * Math.PI / 180.0);
        for (var seed = 0; seed < tags.Length; seed++)
        {
            if (tags[seed] != 0) continue;
            tags[seed] = nextTag;
            var queue = new Queue<int>();
            queue.Enqueue(seed);
            while (queue.Count > 0)
            {
                var current = queue.Dequeue();
                foreach (var neighbour in neighbours[current])
                {
                    if (tags[neighbour] != 0) continue;
                    var dot = Dot(normals[current], normals[neighbour]);
                    if (Math.Abs(dot) < cosineLimit) continue;
                    tags[neighbour] = nextTag;
                    queue.Enqueue(neighbour);
                }
            }
            nextTag++;
        }
        return tags;

        void AddEdge(int first, int second, int owner)
        {
            var edge = first < second ? (first, second) : (second, first);
            if (!edgeOwners.TryGetValue(edge, out var list)) edgeOwners[edge] = list = new List<int>(2);
            list.Add(owner);
        }
    }

    private static Vec3 Cross(Vec3 first, Vec3 second) => new(
        first.Y * second.Z - first.Z * second.Y,
        first.Z * second.X - first.X * second.Z,
        first.X * second.Y - first.Y * second.X);

    private static double Dot(Vec3 first, Vec3 second) => first.X * second.X + first.Y * second.Y + first.Z * second.Z;
}

internal static class SelectableGmshMesher
{
    public static async Task<CadMesh> GenerateAsync(
        string executable,
        string stepPath,
        double targetSizeMm,
        int dimension,
        CancellationToken cancellationToken)
    {
        if (dimension is not (2 or 3)) throw new ArgumentOutOfRangeException(nameof(dimension));
        if (!File.Exists(stepPath)) throw new FileNotFoundException("STEP file not found.", stepPath);
        if (!double.IsFinite(targetSizeMm) || targetSizeMm <= 0) throw new ArgumentOutOfRangeException(nameof(targetSizeMm));

        var runDirectory = Path.Combine(Path.GetTempPath(), "AsterMax", "gmsh", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDirectory);
        var localStep = Path.Combine(runDirectory, "model.step");
        var meshPath = Path.Combine(runDirectory, dimension == 3 ? "volume.msh" : "surface.msh");
        File.Copy(stepPath, localStep, true);

        var info = new ProcessStartInfo
        {
            FileName = executable,
            WorkingDirectory = runDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        info.ArgumentList.Add(localStep);
        info.ArgumentList.Add(dimension == 3 ? "-3" : "-2");
        info.ArgumentList.Add("-format");
        info.ArgumentList.Add("msh2");
        info.ArgumentList.Add("-order");
        info.ArgumentList.Add("1");
        info.ArgumentList.Add("-o");
        info.ArgumentList.Add(meshPath);
        info.ArgumentList.Add("-setnumber");
        info.ArgumentList.Add("Mesh.MeshSizeMin");
        info.ArgumentList.Add(targetSizeMm.ToString("G17", CultureInfo.InvariantCulture));
        info.ArgumentList.Add("-setnumber");
        info.ArgumentList.Add("Mesh.MeshSizeMax");
        info.ArgumentList.Add(targetSizeMm.ToString("G17", CultureInfo.InvariantCulture));
        info.ArgumentList.Add("-nopopup");
        info.ArgumentList.Add("-v");
        info.ArgumentList.Add("3");

        using var process = new Process { StartInfo = info };
        process.Start();
        var stdoutTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var stderrTask = process.StandardError.ReadToEndAsync(cancellationToken);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromMinutes(3));
        await process.WaitForExitAsync(timeout.Token);
        var log = await stdoutTask + Environment.NewLine + await stderrTask;
        if (process.ExitCode != 0)
            throw new InvalidOperationException($"Gmsh exited with code {process.ExitCode}.\n\n{LastLines(log, 18)}");
        if (!File.Exists(meshPath))
            throw new InvalidDataException("Gmsh finished without creating the requested MSH file.\n\n" + LastLines(log, 18));

        var mesh = ParseMsh2(meshPath, log);
        try { Directory.Delete(runDirectory, true); } catch { }
        return mesh;
    }

    internal static CadMesh ParseMsh2(string path, string engineLog)
    {
        var lines = File.ReadAllLines(path);
        var nodeById = new Dictionary<int, int>();
        var nodes = new List<Vec3>();
        var triangles = new List<int[]>();
        var triangleEntityTags = new List<int>();
        var tetrahedra = new List<int[]>();

        for (var index = 0; index < lines.Length; index++)
        {
            if (lines[index].Trim() == "$Nodes")
            {
                var count = int.Parse(lines[++index], CultureInfo.InvariantCulture);
                for (var row = 0; row < count; row++)
                {
                    var fields = lines[++index].Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
                    var id = int.Parse(fields[0], CultureInfo.InvariantCulture);
                    nodeById[id] = nodes.Count;
                    nodes.Add(new Vec3(
                        double.Parse(fields[1], CultureInfo.InvariantCulture),
                        double.Parse(fields[2], CultureInfo.InvariantCulture),
                        double.Parse(fields[3], CultureInfo.InvariantCulture)));
                }
            }
            else if (lines[index].Trim() == "$Elements")
            {
                var count = int.Parse(lines[++index], CultureInfo.InvariantCulture);
                for (var row = 0; row < count; row++)
                {
                    var fields = lines[++index].Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
                    if (fields.Length < 4) continue;
                    var type = int.Parse(fields[1], CultureInfo.InvariantCulture);
                    var tagCount = int.Parse(fields[2], CultureInfo.InvariantCulture);
                    var firstNode = 3 + tagCount;
                    if (type == 2 && fields.Length >= firstNode + 3)
                    {
                        triangles.Add([
                            nodeById[int.Parse(fields[firstNode], CultureInfo.InvariantCulture)],
                            nodeById[int.Parse(fields[firstNode + 1], CultureInfo.InvariantCulture)],
                            nodeById[int.Parse(fields[firstNode + 2], CultureInfo.InvariantCulture)]]);
                        var entityTag = tagCount >= 2
                            ? int.Parse(fields[4], CultureInfo.InvariantCulture)
                            : tagCount == 1
                                ? int.Parse(fields[3], CultureInfo.InvariantCulture)
                                : 0;
                        triangleEntityTags.Add(entityTag);
                    }
                    else if (type == 4 && fields.Length >= firstNode + 4)
                    {
                        tetrahedra.Add([
                            nodeById[int.Parse(fields[firstNode], CultureInfo.InvariantCulture)],
                            nodeById[int.Parse(fields[firstNode + 1], CultureInfo.InvariantCulture)],
                            nodeById[int.Parse(fields[firstNode + 2], CultureInfo.InvariantCulture)],
                            nodeById[int.Parse(fields[firstNode + 3], CultureInfo.InvariantCulture)]]);
                    }
                }
            }
        }

        if (nodes.Count == 0) throw new InvalidDataException("The MSH file contains no nodes.");
        var mesh = new CadMesh
        {
            Nodes = nodes,
            SurfaceTriangles = triangles,
            Tetrahedra = tetrahedra,
            Min = new Vec3(nodes.Min(point => point.X), nodes.Min(point => point.Y), nodes.Min(point => point.Z)),
            Max = new Vec3(nodes.Max(point => point.X), nodes.Max(point => point.Y), nodes.Max(point => point.Z)),
            EngineLog = engineLog
        };
        CadTopologyRegistry.Register(mesh, triangleEntityTags);
        return mesh;
    }

    private static string LastLines(string text, int count) =>
        string.Join(Environment.NewLine, text.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None).TakeLast(count));
}

internal sealed class SelectableCadMeshCanvas : Control
{
    private readonly Action<CadSurfaceSelection> _selectionCallback;
    private SimpleStepSolid? _envelope;
    private CadMesh? _mesh;
    private CadSurfaceTopology? _topology;
    private bool _volumeMesh;
    private float _zoom = 1f;
    private float _yaw = -.55f;
    private Point _last;
    private bool _dragging;
    private int? _selectedFaceTag;
    private HashSet<int> _supportFaceTags = new();
    private HashSet<int> _loadFaceTags = new();
    private readonly List<ProjectedTriangle> _projectedTriangles = new();

    public SelectableCadMeshCanvas(Action<CadSurfaceSelection> selectionCallback)
    {
        _selectionCallback = selectionCallback;
        DoubleBuffered = true;
        BackColor = Color.FromArgb(236, 242, 248);
        MouseWheel += (_, eventArgs) =>
        {
            _zoom = Math.Clamp(_zoom + (eventArgs.Delta > 0 ? .1f : -.1f), .25f, 4f);
            Invalidate();
        };
        MouseDown += (_, eventArgs) =>
        {
            if (eventArgs.Button == MouseButtons.Middle ||
                eventArgs.Button == MouseButtons.Left && ModifierKeys.HasFlag(Keys.Control))
            {
                _dragging = true;
                _last = eventArgs.Location;
            }
        };
        MouseMove += (_, eventArgs) =>
        {
            if (!_dragging) return;
            _yaw += (eventArgs.X - _last.X) * .01f;
            _last = eventArgs.Location;
            Invalidate();
        };
        MouseUp += (_, _) => _dragging = false;
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
        _selectedFaceTag = null;
        Visible = true;
        Invalidate();
    }

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

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var graphics = e.Graphics;
        using var background = new LinearGradientBrush(ClientRectangle, Color.White, Color.FromArgb(216, 229, 241), 90f);
        graphics.FillRectangle(background, ClientRectangle);
        DrawFloor(graphics);
        _projectedTriangles.Clear();
        if (_mesh is null || _envelope is null || _topology is null) return;

        var center = (_mesh.Min + _mesh.Max) / 2.0;
        var dimensions = _mesh.Max - _mesh.Min;
        var maximum = Math.Max(dimensions.X, Math.Max(dimensions.Y, dimensions.Z));
        var scale = Math.Min(ClientSize.Width, ClientSize.Height) * .58f * _zoom / Math.Max(maximum, 1e-9);
        var cosine = MathF.Cos(_yaw);
        var sine = MathF.Sin(_yaw);

        (PointF Point, float Depth) Project(Vec3 original)
        {
            var point = original - center;
            var x = (float)point.X;
            var y = (float)point.Y;
            var z = (float)point.Z;
            var rotatedX = x * cosine - y * sine;
            var depth = x * sine + y * cosine;
            return (new PointF(
                ClientSize.Width * .51f + rotatedX * (float)scale,
                ClientSize.Height * .49f - z * (float)scale + depth * (float)scale * .34f), depth);
        }

        var projectedNodes = _mesh.Nodes.Select(Project).ToArray();
        var ordered = _mesh.SurfaceTriangles
            .Select((triangle, index) => new ProjectedTriangle(
                index,
                _topology.TriangleFaceTags[index],
                new[] { projectedNodes[triangle[0]].Point, projectedNodes[triangle[1]].Point, projectedNodes[triangle[2]].Point },
                (projectedNodes[triangle[0]].Depth + projectedNodes[triangle[1]].Depth + projectedNodes[triangle[2]].Depth) / 3f))
            .OrderBy(item => item.Depth)
            .ToArray();
        _projectedTriangles.AddRange(ordered);

        graphics.SmoothingMode = ordered.Length <= 18000 ? SmoothingMode.AntiAlias : SmoothingMode.HighSpeed;
        var edgeStride = Math.Max(1, (int)Math.Ceiling(ordered.Length / 28000.0));
        using var edge = new Pen(Color.FromArgb(_volumeMesh ? 54 : 72, 24, 58, 82), _volumeMesh ? .45f : .55f);
        for (var index = 0; index < ordered.Length; index++)
        {
            var item = ordered[index];
            var normalized = maximum <= 1e-12 ? .5 : Math.Clamp((item.Depth + maximum / 2) / maximum, 0, 1);
            var color = Blend(Color.FromArgb(52, 142, 199), Color.FromArgb(156, 211, 235), normalized);
            using var brush = new SolidBrush(color);
            graphics.FillPolygon(brush, item.Points);
            if (index % edgeStride == 0) graphics.DrawPolygon(edge, item.Points);
        }

        DrawAssignedAndSelectedFaces(graphics, ordered);
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
        graphics.FillRectangle(panel, 14, 13, Math.Min(760, ClientSize.Width - 28), 90);
        using var titleFont = new Font("Segoe UI Semibold", 11f);
        using var textFont = new Font("Segoe UI", 8.7f);
        graphics.DrawString(_volumeMesh ? "Gmsh exterior skin of volume mesh" : "OpenCASCADE STEP surface preview", titleFont, Brushes.DarkSlateGray, 26, 22);
        graphics.DrawString($"{_mesh.Nodes.Count:N0} nodes · {_mesh.SurfaceTriangles.Count:N0} boundary triangles · {_mesh.Tetrahedra.Count:N0} TET4 · {_topology.Faces.Count:N0} selectable faces", textFont, Brushes.SlateGray, 26, 48);
        graphics.DrawString($"Envelope {_envelope.LengthX:0.###} × {_envelope.LengthY:0.###} × {_envelope.LengthZ:0.###} mm", textFont, Brushes.SlateGray, 26, 65);
        graphics.DrawString("Click: select face · Ctrl + drag or middle drag: rotate · Wheel: zoom", textFont, Brushes.SlateGray, 26, 82);
    }

    private void DrawFloor(Graphics graphics)
    {
        using var pen = new Pen(Color.FromArgb(42, 105, 130, 155), .7f);
        var horizon = ClientSize.Height * .76f;
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
        var origin = new PointF(ClientSize.Width - 68, ClientSize.Height - 55);
        using var red = new Pen(Color.FromArgb(210, 54, 54), 2f);
        using var green = new Pen(Color.FromArgb(38, 145, 74), 2f);
        using var blue = new Pen(Color.FromArgb(45, 93, 205), 2f);
        graphics.DrawLine(red, origin, new PointF(origin.X + 34, origin.Y));
        graphics.DrawLine(green, origin, new PointF(origin.X - 23, origin.Y + 20));
        graphics.DrawLine(blue, origin, new PointF(origin.X, origin.Y - 35));
        using var font = new Font("Segoe UI", 8f);
        graphics.DrawString("X", font, Brushes.Firebrick, origin.X + 36, origin.Y - 7);
        graphics.DrawString("Y", font, Brushes.ForestGreen, origin.X - 35, origin.Y + 16);
        graphics.DrawString("Z", font, Brushes.RoyalBlue, origin.X - 4, origin.Y - 49);
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
