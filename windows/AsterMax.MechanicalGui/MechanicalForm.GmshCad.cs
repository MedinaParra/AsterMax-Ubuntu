using System.Drawing.Drawing2D;

namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private string? _cadStepPath;
    private SimpleStepSolid? _cadEnvelope;
    private CadMesh? _cadSurfacePreview;
    private CadMesh? _cadVolumeMesh;
    private CadMeshCanvas? _cadCanvas;

    private async Task ImportCadStepAsync(string path)
    {
        if (_busy) return;
        HideCadCanvas();
        ResetCadState();

        SimpleStepSolid envelope;
        try
        {
            envelope = SimpleStepReader.ReadPrismaticSolid(path);
        }
        catch (Exception exception)
        {
            Log("STEP ENVELOPE ERROR: " + exception.Message);
            MessageBox.Show(this, exception.Message, "STEP import failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        if (envelope.IsSupportedPrism)
        {
            ImportSimpleStep(path);
            return;
        }

        var gmsh = GmshCliMesher.FindExecutable();
        if (gmsh is null)
        {
            MessageBox.Show(this,
                "This STEP contains curved surfaces, holes or non-prismatic topology.\n\n" +
                "Use the complete AsterMax ZIP package, which contains tools\\gmsh\\gmsh.exe, or configure the GMSH_EXE environment variable.",
                "Gmsh engine not found",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            return;
        }

        try
        {
            _busy = true;
            ToggleUi(false);
            _statusMain.Text = "Importing STEP through OpenCASCADE and creating surface preview…";
            var longest = Math.Max(envelope.LengthX, Math.Max(envelope.LengthY, envelope.LengthZ));
            var previewSize = Math.Max(longest / 24.0, longest * 1e-4);
            var preview = await GmshCliMesher.GenerateAsync(gmsh, path, previewSize, 2, CancellationToken.None);
            if (preview.SurfaceTriangles.Count == 0)
                throw new InvalidDataException("Gmsh imported the STEP but did not generate surface triangles.");

            _cadStepPath = path;
            _cadEnvelope = envelope;
            _cadSurfacePreview = preview;
            _cadVolumeMesh = null;
            _geometryPath = path;
            _meshGenerated = false;
            _solved = false;

            var geometry = _nodes["Geometry"];
            geometry.Nodes.Clear();
            var body = MakeNode(Path.GetFileNameWithoutExtension(path), ObjectKind.Body, ObjectState.UpToDate, "OpenCASCADE STEP Solid");
            var bodyObject = (ModelObject)body.Tag;
            bodyObject.Properties["Geometry Fidelity"] = "Native STEP / OpenCASCADE surface topology";
            bodyObject.Properties["Length X"] = $"{envelope.LengthX:0.###} mm";
            bodyObject.Properties["Length Y"] = $"{envelope.LengthY:0.###} mm";
            bodyObject.Properties["Length Z"] = $"{envelope.LengthZ:0.###} mm";
            bodyObject.Properties["Surface Nodes"] = preview.Nodes.Count.ToString("N0");
            bodyObject.Properties["Surface Triangles"] = preview.SurfaceTriangles.Count.ToString("N0");
            bodyObject.Properties["Material"] = _simpleMaterial.Name;
            bodyObject.Properties["Source"] = path;
            bodyObject.Properties["CAD Engine"] = "Gmsh 4.15.2 / OpenCASCADE";
            geometry.Nodes.Add(body);
            geometry.Expand();
            SetState(geometry, ObjectState.UpToDate);
            SetState(_nodes["Model"], ObjectState.Ready);
            SetState(_nodes["Mesh"], ObjectState.NeedsAttention);
            MarkSolutionDirty();

            EnsureCadCanvas().SetMesh(envelope, preview, false);
            SelectNode("Geometry");
            Log($"REAL STEP PREVIEW: {Path.GetFileName(path)}; {preview.Nodes.Count:N0} nodes, {preview.SurfaceTriangles.Count:N0} surface triangles.");
            Log("The geometry is displayed from the imported OpenCASCADE topology, not from a rectangular proxy.");
            _statusMain.Text = "STEP loaded — use Generate Mesh for a real unstructured tetrahedral mesh";
        }
        catch (Exception exception)
        {
            Log("GMSH STEP IMPORT ERROR: " + exception);
            MessageBox.Show(this, exception.Message, "Gmsh STEP import failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            _busy = false;
            ToggleUi(true);
        }
    }

    private async Task GenerateCadMeshAsync()
    {
        if (_busy) return;
        if (_cadStepPath is null || _cadEnvelope is null)
        {
            MessageBox.Show(this, "Import a STEP geometry first.", "Gmsh meshing", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        var gmsh = GmshCliMesher.FindExecutable();
        if (gmsh is null)
        {
            MessageBox.Show(this, "Gmsh was not found. Extract and run AsterMax from the complete ZIP package.", "Gmsh meshing", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        var longest = Math.Max(_cadEnvelope.LengthX, Math.Max(_cadEnvelope.LengthY, _cadEnvelope.LengthZ));
        using var dialog = new GmshMeshSizeDialog(Math.Max(longest / 12.0, longest * 1e-4));
        if (dialog.ShowDialog(this) != DialogResult.OK) return;

        try
        {
            _busy = true;
            ToggleUi(false);
            _statusMain.Text = "Generating unstructured tetrahedral mesh with Gmsh…";
            var mesh = await GmshCliMesher.GenerateAsync(gmsh, _cadStepPath, dialog.TargetSizeMm, 3, CancellationToken.None);
            if (mesh.Tetrahedra.Count == 0)
                throw new InvalidDataException("Gmsh did not generate tetrahedral volume elements. Verify that the STEP contains a closed solid volume.");

            _cadVolumeMesh = mesh;
            _meshGenerated = true;
            _solved = false;
            SetState(_nodes["Mesh"], ObjectState.UpToDate);
            if (_nodes["Mesh"].Tag is ModelObject meshObject)
            {
                meshObject.Properties["Mesher"] = "Gmsh OpenCASCADE unstructured TET4";
                meshObject.Properties["Target Size"] = $"{dialog.TargetSizeMm:0.###} mm";
                meshObject.Properties["Nodes"] = mesh.Nodes.Count.ToString("N0");
                meshObject.Properties["Surface Triangles"] = mesh.SurfaceTriangles.Count.ToString("N0");
                meshObject.Properties["Tetrahedra"] = mesh.Tetrahedra.Count.ToString("N0");
            }
            MarkSolutionDirty();
            EnsureCadCanvas().SetMesh(_cadEnvelope, mesh, true);
            PopulateCadMeshTable(mesh, dialog.TargetSizeMm);
            SelectLowerTab("Worksheet");
            SelectNode("Mesh");
            Log($"REAL GMSH VOLUME MESH: {mesh.Nodes.Count:N0} nodes, {mesh.SurfaceTriangles.Count:N0} boundary triangles, {mesh.Tetrahedra.Count:N0} TET4.");
            _statusMain.Text = "Real Gmsh tetrahedral mesh generated — boundary-condition mapping is the next solver step";
        }
        catch (Exception exception)
        {
            Log("GMSH MESH ERROR: " + exception);
            MessageBox.Show(this, exception.Message, "Gmsh meshing failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            _busy = false;
            ToggleUi(true);
        }
    }

    private void PopulateCadMeshTable(CadMesh mesh, double targetSizeMm)
    {
        _worksheet.Columns.Clear();
        _worksheet.Rows.Clear();
        _worksheet.Columns.Add("Property", "Mesh Property");
        _worksheet.Columns.Add("Value", "Value");
        _worksheet.Rows.Add("CAD kernel", "OpenCASCADE through Gmsh");
        _worksheet.Rows.Add("Element type", "Linear tetrahedron / TET4");
        _worksheet.Rows.Add("Target size", $"{targetSizeMm:0.###} mm");
        _worksheet.Rows.Add("Nodes", mesh.Nodes.Count.ToString("N0"));
        _worksheet.Rows.Add("Boundary triangles", mesh.SurfaceTriangles.Count.ToString("N0"));
        _worksheet.Rows.Add("Volume tetrahedra", mesh.Tetrahedra.Count.ToString("N0"));
        _worksheet.Rows.Add("Solver status", "Mesh ready; general face scoping not yet defined");
    }

    private CadMeshCanvas EnsureCadCanvas()
    {
        _cadCanvas ??= new CadMeshCanvas();
        if (_cadCanvas.Parent != _viewport)
        {
            _cadCanvas.Dock = DockStyle.Fill;
            _viewport.Controls.Add(_cadCanvas);
        }
        _cadCanvas.Visible = true;
        _cadCanvas.BringToFront();
        return _cadCanvas;
    }

    private void HideCadCanvas()
    {
        if (_cadCanvas is not null) _cadCanvas.Visible = false;
    }

    private void ResetCadState()
    {
        _cadStepPath = null;
        _cadEnvelope = null;
        _cadSurfacePreview = null;
        _cadVolumeMesh = null;
        HideCadCanvas();
    }
}

internal sealed class CadMesh
{
    public required List<Vec3> Nodes { get; init; }
    public required List<int[]> SurfaceTriangles { get; init; }
    public required List<int[]> Tetrahedra { get; init; }
    public required Vec3 Min { get; init; }
    public required Vec3 Max { get; init; }
    public required string EngineLog { get; init; }
}

internal static class GmshCliMesher
{
    public static string? FindExecutable()
    {
        var candidates = new[]
        {
            Environment.GetEnvironmentVariable("GMSH_EXE"),
            Path.Combine(AppContext.BaseDirectory, "tools", "gmsh", "gmsh.exe"),
            Path.Combine(AppContext.BaseDirectory, "gmsh.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Gmsh", "gmsh.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Gmsh", "gmsh.exe")
        };
        return candidates.FirstOrDefault(path => !string.IsNullOrWhiteSpace(path) && File.Exists(path));
    }

    public static async Task<CadMesh> GenerateAsync(string executable, string stepPath, double targetSizeMm, int dimension, CancellationToken cancellationToken)
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
        var stdout = await stdoutTask;
        var stderr = await stderrTask;
        var log = stdout + Environment.NewLine + stderr;
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
                    var point = new Vec3(
                        double.Parse(fields[1], CultureInfo.InvariantCulture),
                        double.Parse(fields[2], CultureInfo.InvariantCulture),
                        double.Parse(fields[3], CultureInfo.InvariantCulture));
                    nodeById[id] = nodes.Count;
                    nodes.Add(point);
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
                        triangles.Add([nodeById[int.Parse(fields[firstNode], CultureInfo.InvariantCulture)], nodeById[int.Parse(fields[firstNode + 1], CultureInfo.InvariantCulture)], nodeById[int.Parse(fields[firstNode + 2], CultureInfo.InvariantCulture)]]);
                    else if (type == 4 && fields.Length >= firstNode + 4)
                        tetrahedra.Add([nodeById[int.Parse(fields[firstNode], CultureInfo.InvariantCulture)], nodeById[int.Parse(fields[firstNode + 1], CultureInfo.InvariantCulture)], nodeById[int.Parse(fields[firstNode + 2], CultureInfo.InvariantCulture)], nodeById[int.Parse(fields[firstNode + 3], CultureInfo.InvariantCulture)]]);
                }
            }
        }

        if (nodes.Count == 0) throw new InvalidDataException("The MSH file contains no nodes.");
        var min = new Vec3(nodes.Min(point => point.X), nodes.Min(point => point.Y), nodes.Min(point => point.Z));
        var max = new Vec3(nodes.Max(point => point.X), nodes.Max(point => point.Y), nodes.Max(point => point.Z));
        return new CadMesh
        {
            Nodes = nodes,
            SurfaceTriangles = triangles,
            Tetrahedra = tetrahedra,
            Min = min,
            Max = max,
            EngineLog = engineLog
        };
    }

    private static string LastLines(string text, int count) =>
        string.Join(Environment.NewLine, text.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None).TakeLast(count));
}

internal sealed class CadMeshCanvas : Control
{
    private SimpleStepSolid? _envelope;
    private CadMesh? _mesh;
    private bool _volumeMesh;
    private float _zoom = 1f;
    private float _yaw = -0.55f;
    private Point _last;
    private bool _dragging;

    public CadMeshCanvas()
    {
        DoubleBuffered = true;
        BackColor = Color.FromArgb(236, 242, 248);
        MouseWheel += (_, eventArgs) => { _zoom = Math.Clamp(_zoom + (eventArgs.Delta > 0 ? .1f : -.1f), .25f, 4f); Invalidate(); };
        MouseDown += (_, eventArgs) => { if (eventArgs.Button == MouseButtons.Left || eventArgs.Button == MouseButtons.Middle) { _dragging = true; _last = eventArgs.Location; } };
        MouseMove += (_, eventArgs) => { if (!_dragging) return; _yaw += (eventArgs.X - _last.X) * .01f; _last = eventArgs.Location; Invalidate(); };
        MouseUp += (_, _) => _dragging = false;
    }

    public void SetMesh(SimpleStepSolid envelope, CadMesh mesh, bool volumeMesh)
    {
        _envelope = envelope;
        _mesh = mesh;
        _volumeMesh = volumeMesh;
        _zoom = 1f;
        _yaw = -0.55f;
        Visible = true;
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var graphics = e.Graphics;
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using var background = new LinearGradientBrush(ClientRectangle, Color.White, Color.FromArgb(216, 229, 241), 90f);
        graphics.FillRectangle(background, ClientRectangle);
        DrawFloor(graphics);
        if (_mesh is null || _envelope is null) return;

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
            return (new PointF(ClientSize.Width * .51f + rotatedX * (float)scale,
                ClientSize.Height * .49f - z * (float)scale + depth * (float)scale * .34f), depth);
        }

        var projected = _mesh.Nodes.Select(Project).ToArray();
        var ordered = _mesh.SurfaceTriangles
            .Where(triangle => triangle.Length >= 3)
            .Select(triangle => (Triangle: triangle, Depth: (projected[triangle[0]].Depth + projected[triangle[1]].Depth + projected[triangle[2]].Depth) / 3f))
            .OrderBy(item => item.Depth)
            .ToArray();
        var stride = Math.Max(1, (int)Math.Ceiling(ordered.Length / 14000.0));
        using var edge = new Pen(Color.FromArgb(_volumeMesh ? 105 : 70, 28, 65, 89), _volumeMesh ? .65f : .45f);
        for (var index = 0; index < ordered.Length; index += stride)
        {
            var item = ordered[index];
            var triangle = item.Triangle;
            var points = new[] { projected[triangle[0]].Point, projected[triangle[1]].Point, projected[triangle[2]].Point };
            var normalized = maximum <= 1e-12 ? .5 : Math.Clamp((item.Depth + maximum / 2) / maximum, 0, 1);
            var color = Blend(Color.FromArgb(47, 137, 194), Color.FromArgb(137, 202, 231), normalized);
            using var brush = new SolidBrush(color);
            graphics.FillPolygon(brush, points);
            graphics.DrawPolygon(edge, points);
        }

        DrawHeader(graphics);
        DrawTriad(graphics);
    }

    private void DrawHeader(Graphics graphics)
    {
        if (_mesh is null || _envelope is null) return;
        using var panel = new SolidBrush(Color.FromArgb(222, 255, 255, 255));
        graphics.FillRectangle(panel, 14, 13, Math.Min(650, ClientSize.Width - 28), 72);
        using var titleFont = new Font("Segoe UI Semibold", 11f);
        using var textFont = new Font("Segoe UI", 8.7f);
        graphics.DrawString(_volumeMesh ? "Gmsh unstructured volume mesh" : "OpenCASCADE STEP surface preview", titleFont, Brushes.DarkSlateGray, 26, 22);
        graphics.DrawString($"{_mesh.Nodes.Count:N0} nodes · {_mesh.SurfaceTriangles.Count:N0} boundary triangles · {_mesh.Tetrahedra.Count:N0} TET4", textFont, Brushes.SlateGray, 26, 48);
        graphics.DrawString($"Envelope {_envelope.LengthX:0.###} × {_envelope.LengthY:0.###} × {_envelope.LengthZ:0.###} mm", textFont, Brushes.SlateGray, 26, 65);
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

    private static Color Blend(Color first, Color second, double amount)
    {
        amount = Math.Clamp(amount, 0, 1);
        return Color.FromArgb(
            (int)(first.R + (second.R - first.R) * amount),
            (int)(first.G + (second.G - first.G) * amount),
            (int)(first.B + (second.B - first.B) * amount));
    }
}

internal sealed class GmshMeshSizeDialog : Form
{
    private readonly NumericUpDown _size = new()
    {
        Dock = DockStyle.Fill,
        Minimum = 0.001M,
        Maximum = 1000000M,
        DecimalPlaces = 3,
        ThousandsSeparator = true
    };

    public double TargetSizeMm => (double)_size.Value;

    public GmshMeshSizeDialog(double defaultSize)
    {
        Text = "Gmsh volume mesh settings";
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = MinimizeBox = false;
        ClientSize = new Size(470, 190);
        _size.Value = Math.Clamp((decimal)defaultSize, _size.Minimum, _size.Maximum);
        var table = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(15), ColumnCount = 2, RowCount = 4 };
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 190));
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        table.Controls.Add(new Label { Text = "Target element size (mm)", AutoSize = true, Anchor = AnchorStyles.Left }, 0, 0);
        table.Controls.Add(_size, 1, 0);
        var note = new Label
        {
            Text = "Smaller values create more tetrahedra and require more memory. Start coarse, then run a convergence study.",
            Dock = DockStyle.Fill,
            ForeColor = MechanicalForm.TextMuted
        };
        table.Controls.Add(note, 0, 1);
        table.SetColumnSpan(note, 2);
        var buttons = ObjectGeneratorDialog.DialogButtons(this);
        table.Controls.Add(buttons, 0, 3);
        table.SetColumnSpan(buttons, 2);
        Controls.Add(table);
    }
}
