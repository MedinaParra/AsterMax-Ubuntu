using System.Runtime.CompilerServices;

namespace AsterMax.MechanicalGui;

internal enum CadMeshStrategy
{
    Automatic,
    Curvature,
    Uniform
}

internal sealed record CadMeshGenerationSettings(
    CadMeshStrategy Strategy,
    double MinimumSizeMm,
    double MaximumSizeMm,
    int CurvaturePoints,
    double GrowthRate,
    bool Optimize,
    bool ShowMeshEdges);

internal static class AutomaticMeshingViewportBootstrap
{
    [ModuleInitializer]
    internal static void Install() => Application.AddMessageFilter(new AutomaticMeshingMessageFilter());

    private sealed class AutomaticMeshingMessageFilter : IMessageFilter
    {
        private const int WmLeftButtonUp = 0x0202;
        private const int WmKeyUp = 0x0101;

        public bool PreFilterMessage(ref Message message)
        {
            var control = Control.FromHandle(message.HWnd);
            var form = control?.FindForm() as MechanicalForm;
            if (form is null) return false;

            form.EnsureAdvancedCadViewport();
            if (message.Msg is not (WmLeftButtonUp or WmKeyUp)) return false;

            var button = FindButton(control);
            if (button is null || !IsGenerateMeshButton(button)) return false;
            if (message.Msg == WmKeyUp)
            {
                var key = (Keys)(int)message.WParam;
                if (key is not (Keys.Space or Keys.Enter)) return false;
            }
            if (!form.CanUseAutomaticCadMeshing()) return false;

            form.BeginInvoke(() => _ = form.GenerateAutomaticCadMeshAsync());
            return true;
        }

        private static Button? FindButton(Control? control)
        {
            while (control is not null)
            {
                if (control is Button button) return button;
                control = control.Parent;
            }
            return null;
        }

        private static bool IsGenerateMeshButton(Button button)
        {
            var text = button.Text.Replace("&", string.Empty).Trim();
            return text.Contains("Generate", StringComparison.OrdinalIgnoreCase) &&
                   text.Contains("Mesh", StringComparison.OrdinalIgnoreCase);
        }
    }
}

internal sealed partial class MechanicalForm
{
    private AdvancedCadMeshCanvas? _advancedCadCanvas;
    private CadMesh? _advancedDisplayedMesh;
    private CadMeshGenerationSettings? _lastCadMeshSettings;

    internal bool CanUseAutomaticCadMeshing() =>
        !_busy && _cadStepPath is not null && _cadEnvelope is { IsSupportedPrism: false };

    internal void EnsureAdvancedCadViewport()
    {
        var mesh = _cadVolumeMesh ?? _cadSurfacePreview;
        if (mesh is null || _cadEnvelope is null) return;

        _advancedCadCanvas ??= new AdvancedCadMeshCanvas(HandleCadFaceSelected);
        if (_advancedCadCanvas.Parent != _viewport)
        {
            _advancedCadCanvas.Dock = DockStyle.Fill;
            _viewport.Controls.Add(_advancedCadCanvas);
        }
        if (!ReferenceEquals(mesh, _advancedDisplayedMesh))
        {
            _advancedDisplayedMesh = mesh;
            _advancedCadCanvas.SetMesh(_cadEnvelope, mesh, ReferenceEquals(mesh, _cadVolumeMesh));
            _advancedCadCanvas.ShowMeshEdges = _lastCadMeshSettings?.ShowMeshEdges ?? ReferenceEquals(mesh, _cadVolumeMesh);
        }
        _advancedCadCanvas.SetScopeMarkers(ScopedCadTags(ObjectKind.Support), ScopedCadTags(ObjectKind.Load));
        _advancedCadCanvas.Visible = true;
        _advancedCadCanvas.BringToFront();
        if (_cadCanvas is not null) _cadCanvas.Visible = false;
    }

    internal async Task GenerateAutomaticCadMeshAsync()
    {
        if (!CanUseAutomaticCadMeshing() || _cadStepPath is null || _cadEnvelope is null) return;
        var gmsh = GmshCliMesher.FindExecutable();
        if (gmsh is null)
        {
            MessageBox.Show(this, "Gmsh was not found. Run AsterMax from the complete ZIP package.", "Automatic meshing", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        var longest = Math.Max(_cadEnvelope.LengthX, Math.Max(_cadEnvelope.LengthY, _cadEnvelope.LengthZ));
        var suggestedMaximum = Math.Max(longest / 18.0, longest * 1e-4);
        using var dialog = new AutomaticCadMeshDialog(suggestedMaximum, _lastCadMeshSettings);
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        var settings = dialog.Settings;
        _lastCadMeshSettings = settings;

        try
        {
            _busy = true;
            ToggleUi(false);
            _statusMain.Text = settings.Strategy == CadMeshStrategy.Uniform
                ? "Generating uniform tetrahedral mesh…"
                : "Generating curvature-adaptive tetrahedral mesh…";

            var mesh = await AdaptiveSelectableGmshMesher.GenerateAsync(
                gmsh, _cadStepPath, settings, CancellationToken.None);
            if (mesh.Tetrahedra.Count == 0)
                throw new InvalidDataException("Gmsh did not generate tetrahedral volume elements. Verify that the STEP is a closed solid.");

            _cadVolumeMesh = mesh;
            _meshGenerated = true;
            _solved = false;
            var topology = CadTopologyRegistry.Get(mesh);
            SetState(_nodes["Mesh"], ObjectState.UpToDate);
            if (_nodes["Mesh"].Tag is ModelObject meshObject)
            {
                meshObject.Properties["Meshing Strategy"] = settings.Strategy switch
                {
                    CadMeshStrategy.Automatic => "Automatic curvature-adaptive",
                    CadMeshStrategy.Curvature => "Curvature controlled",
                    _ => "Uniform global size"
                };
                meshObject.Properties["Element Type"] = "Tetrahedral / Linear TET4";
                meshObject.Properties["Minimum Size"] = $"{settings.MinimumSizeMm:0.###} mm";
                meshObject.Properties["Maximum Size"] = $"{settings.MaximumSizeMm:0.###} mm";
                meshObject.Properties["Curvature Resolution"] = settings.Strategy == CadMeshStrategy.Uniform
                    ? "Disabled"
                    : $"{settings.CurvaturePoints} points per circle";
                meshObject.Properties["Growth Rate"] = settings.GrowthRate.ToString("0.00", CultureInfo.InvariantCulture);
                meshObject.Properties["Mesh Optimization"] = settings.Optimize ? "Netgen + Gmsh" : "Disabled";
                meshObject.Properties["Display Mesh"] = settings.ShowMeshEdges ? "Shown" : "Hidden";
                meshObject.Properties["Nodes"] = mesh.Nodes.Count.ToString("N0");
                meshObject.Properties["Surface Triangles"] = mesh.SurfaceTriangles.Count.ToString("N0");
                meshObject.Properties["Tetrahedra"] = mesh.Tetrahedra.Count.ToString("N0");
                meshObject.Properties["Selectable Faces"] = topology.Faces.Count.ToString("N0");
            }

            MarkSolutionDirty();
            _advancedDisplayedMesh = null;
            EnsureAdvancedCadViewport();
            if (_advancedCadCanvas is not null) _advancedCadCanvas.ShowMeshEdges = settings.ShowMeshEdges;
            PopulateCadMeshTable(mesh, settings.MaximumSizeMm);
            _worksheet.Rows.Insert(3, "Meshing strategy", settings.Strategy.ToString());
            _worksheet.Rows.Insert(4, "Minimum element size", $"{settings.MinimumSizeMm:0.###} mm");
            _worksheet.Rows.Insert(5, "Curvature resolution", settings.Strategy == CadMeshStrategy.Uniform ? "Disabled" : $"{settings.CurvaturePoints} points/circle");
            SelectLowerTab("Worksheet");
            SelectNode("Mesh");
            Log($"AUTOMATIC CAD MESH: {settings.Strategy}; {mesh.Nodes.Count:N0} nodes, {mesh.Tetrahedra.Count:N0} TET4, sizes {settings.MinimumSizeMm:0.###}–{settings.MaximumSizeMm:0.###} mm.");
            _statusMain.Text = "Adaptive tetrahedral mesh ready";
        }
        catch (Exception exception)
        {
            Log("AUTOMATIC MESH ERROR: " + exception);
            MessageBox.Show(this, exception.Message, "Automatic meshing failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            _busy = false;
            ToggleUi(true);
        }
    }
}

internal static class AdaptiveSelectableGmshMesher
{
    public static async Task<CadMesh> GenerateAsync(
        string executable,
        string stepPath,
        CadMeshGenerationSettings settings,
        CancellationToken cancellationToken)
    {
        if (!File.Exists(stepPath)) throw new FileNotFoundException("STEP file not found.", stepPath);
        if (settings.MinimumSizeMm <= 0 || settings.MaximumSizeMm < settings.MinimumSizeMm)
            throw new ArgumentException("Mesh sizes are invalid.");

        var runDirectory = Path.Combine(Path.GetTempPath(), "AsterMax", "adaptive-gmsh", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDirectory);
        var localStep = Path.Combine(runDirectory, "model.step");
        var meshPath = Path.Combine(runDirectory, "volume.msh");
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
        info.ArgumentList.Add("-3");
        info.ArgumentList.Add("-format");
        info.ArgumentList.Add("msh2");
        info.ArgumentList.Add("-order");
        info.ArgumentList.Add("1");
        info.ArgumentList.Add("-o");
        info.ArgumentList.Add(meshPath);
        AddNumber("Mesh.MeshSizeMin", settings.MinimumSizeMm);
        AddNumber("Mesh.MeshSizeMax", settings.MaximumSizeMm);
        AddNumber("Mesh.MeshSizeFactor", 1.0);
        AddNumber("Mesh.MeshSizeExtendFromBoundary", settings.Strategy == CadMeshStrategy.Uniform ? 0 : 1);
        AddNumber("Mesh.MeshSizeFromCurvature", settings.Strategy == CadMeshStrategy.Uniform ? 0 : settings.CurvaturePoints);
        AddNumber("Mesh.MinimumCirclePoints", settings.Strategy == CadMeshStrategy.Uniform ? 6 : settings.CurvaturePoints);
        AddNumber("Mesh.Smoothing", settings.Optimize ? 10 : 2);
        AddNumber("Mesh.Optimize", settings.Optimize ? 1 : 0);
        AddNumber("Mesh.OptimizeNetgen", settings.Optimize ? 1 : 0);
        info.ArgumentList.Add("-nopopup");
        info.ArgumentList.Add("-v");
        info.ArgumentList.Add("3");

        using var process = new Process { StartInfo = info };
        process.Start();
        var stdoutTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var stderrTask = process.StandardError.ReadToEndAsync(cancellationToken);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromMinutes(8));
        await process.WaitForExitAsync(timeout.Token);
        var log = await stdoutTask + Environment.NewLine + await stderrTask;
        if (process.ExitCode != 0)
            throw new InvalidOperationException($"Gmsh exited with code {process.ExitCode}.\n\n{LastLines(log, 20)}");
        if (!File.Exists(meshPath))
            throw new InvalidDataException("Gmsh finished without creating the volume mesh.\n\n" + LastLines(log, 20));

        var mesh = SelectableGmshMesher.ParseMsh2(meshPath, log);
        try { Directory.Delete(runDirectory, true); } catch { }
        return mesh;

        void AddNumber(string name, double value)
        {
            info.ArgumentList.Add("-setnumber");
            info.ArgumentList.Add(name);
            info.ArgumentList.Add(value.ToString("G17", CultureInfo.InvariantCulture));
        }
    }

    private static string LastLines(string text, int count) =>
        string.Join(Environment.NewLine, text.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None).TakeLast(count));
}

internal sealed class AutomaticCadMeshDialog : Form
{
    private readonly ComboBox _strategy = new() { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly ComboBox _elementType = new() { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly NumericUpDown _minimum = NumberBox();
    private readonly NumericUpDown _maximum = NumberBox();
    private readonly NumericUpDown _curvature = new() { Dock = DockStyle.Fill, Minimum = 6, Maximum = 64, Value = 18 };
    private readonly NumericUpDown _growth = new() { Dock = DockStyle.Fill, Minimum = 105, Maximum = 200, Value = 130, DecimalPlaces = 0 };
    private readonly CheckBox _optimize = new() { Text = "Optimize tetrahedral quality", Checked = true, AutoSize = true };
    private readonly CheckBox _showEdges = new() { Text = "Show mesh after generation", Checked = true, AutoSize = true };

    public CadMeshGenerationSettings Settings => new(
        (CadMeshStrategy)_strategy.SelectedIndex,
        (double)_minimum.Value,
        (double)_maximum.Value,
        (int)_curvature.Value,
        (double)_growth.Value / 100.0,
        _optimize.Checked,
        _showEdges.Checked);

    public AutomaticCadMeshDialog(double suggestedMaximum, CadMeshGenerationSettings? previous)
    {
        Text = "Automatic tetrahedral mesh";
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = MinimizeBox = false;
        ClientSize = new Size(560, 390);
        _strategy.Items.AddRange(["Automatic", "Curvature controlled", "Uniform global size"]);
        _elementType.Items.Add("Tetrahedral — Linear TET4");
        _elementType.SelectedIndex = 0;
        _strategy.SelectedIndex = previous is null ? 0 : (int)previous.Strategy;
        _maximum.Value = Clamp(previous?.MaximumSizeMm ?? suggestedMaximum, _maximum);
        _minimum.Value = Clamp(previous?.MinimumSizeMm ?? suggestedMaximum / 4.0, _minimum);
        _curvature.Value = Math.Clamp(previous?.CurvaturePoints ?? 18, (int)_curvature.Minimum, (int)_curvature.Maximum);
        _growth.Value = Math.Clamp((decimal)((previous?.GrowthRate ?? 1.30) * 100), _growth.Minimum, _growth.Maximum);
        _optimize.Checked = previous?.Optimize ?? true;
        _showEdges.Checked = previous?.ShowMeshEdges ?? true;

        var table = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(18), ColumnCount = 2, RowCount = 10 };
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 215));
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        AddRow(table, 0, "Meshing strategy", _strategy);
        AddRow(table, 1, "Element type", _elementType);
        AddRow(table, 2, "Minimum element size (mm)", _minimum);
        AddRow(table, 3, "Maximum element size (mm)", _maximum);
        AddRow(table, 4, "Curvature points per circle", _curvature);
        AddRow(table, 5, "Maximum growth rate (%)", _growth);
        table.Controls.Add(_optimize, 1, 6);
        table.Controls.Add(_showEdges, 1, 7);
        var note = new Label
        {
            Text = "Automatic mode refines teeth, holes, fillets and curved regions while keeping flatter areas coarser. Tetrahedral TET4 is used for the 3-D structural solver.",
            Dock = DockStyle.Fill,
            ForeColor = MechanicalForm.TextMuted
        };
        table.Controls.Add(note, 0, 8);
        table.SetColumnSpan(note, 2);
        var buttons = ObjectGeneratorDialog.DialogButtons(this);
        table.Controls.Add(buttons, 0, 9);
        table.SetColumnSpan(buttons, 2);
        Controls.Add(table);

        _strategy.SelectedIndexChanged += (_, _) => UpdateAvailability();
        _minimum.ValueChanged += (_, _) => { if (_minimum.Value > _maximum.Value) _maximum.Value = _minimum.Value; };
        _maximum.ValueChanged += (_, _) => { if (_maximum.Value < _minimum.Value) _minimum.Value = _maximum.Value; };
        UpdateAvailability();
    }

    private void UpdateAvailability()
    {
        var curvatureEnabled = _strategy.SelectedIndex != (int)CadMeshStrategy.Uniform;
        _curvature.Enabled = curvatureEnabled;
        _growth.Enabled = curvatureEnabled;
    }

    private static NumericUpDown NumberBox() => new()
    {
        Dock = DockStyle.Fill,
        Minimum = .001M,
        Maximum = 1000000M,
        DecimalPlaces = 3,
        ThousandsSeparator = true
    };

    private static decimal Clamp(double value, NumericUpDown control) =>
        Math.Clamp((decimal)value, control.Minimum, control.Maximum);

    private static void AddRow(TableLayoutPanel table, int row, string label, Control control)
    {
        table.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left }, 0, row);
        table.Controls.Add(control, 1, row);
    }
}

internal sealed class AdvancedCadMeshCanvas : Control
{
    private readonly Action<CadSurfaceSelection> _selectionCallback;
    private readonly List<AdvancedProjectedTriangle> _projected = new();
    private SimpleStepSolid? _envelope;
    private CadMesh? _mesh;
    private CadSurfaceTopology? _topology;
    private bool _volumeMesh;
    private bool _orbiting;
    private bool _panning;
    private Point _last;
    private float _yaw = -.65f;
    private float _pitch = .42f;
    private float _zoom = 1f;
    private float _panX;
    private float _panY;
    private int? _selectedFaceTag;
    private HashSet<int> _supportTags = new();
    private HashSet<int> _loadTags = new();
    private readonly ToolStrip _cameraBar;

    public bool ShowMeshEdges { get; set; } = true;

    public AdvancedCadMeshCanvas(Action<CadSurfaceSelection> selectionCallback)
    {
        _selectionCallback = selectionCallback;
        DoubleBuffered = true;
        TabStop = true;
        BackColor = Color.FromArgb(231, 240, 248);
        _cameraBar = BuildCameraBar();
        Controls.Add(_cameraBar);

        MouseWheel += (_, e) =>
        {
            _zoom = Math.Clamp(_zoom * (e.Delta > 0 ? 1.12f : .89f), .08f, 15f);
            Invalidate();
        };
        MouseDown += (_, e) =>
        {
            Focus();
            _last = e.Location;
            _orbiting = e.Button == MouseButtons.Middle || e.Button == MouseButtons.Left && ModifierKeys.HasFlag(Keys.Control);
            _panning = e.Button == MouseButtons.Right || e.Button == MouseButtons.Middle && ModifierKeys.HasFlag(Keys.Shift);
            if (_orbiting || _panning) Capture = true;
        };
        MouseMove += (_, e) =>
        {
            var dx = e.X - _last.X;
            var dy = e.Y - _last.Y;
            if (_orbiting)
            {
                _yaw += dx * .0105f;
                _pitch = Math.Clamp(_pitch + dy * .0105f, -1.54f, 1.54f);
                _last = e.Location;
                Invalidate();
            }
            else if (_panning)
            {
                _panX += dx;
                _panY += dy;
                _last = e.Location;
                Invalidate();
            }
        };
        MouseUp += (_, _) =>
        {
            _orbiting = _panning = false;
            Capture = false;
        };
        MouseClick += (_, e) =>
        {
            if (e.Button == MouseButtons.Left && !ModifierKeys.HasFlag(Keys.Control)) SelectAt(e.Location);
        };
        Resize += (_, _) => PositionCameraBar();
    }

    public void SetMesh(SimpleStepSolid envelope, CadMesh mesh, bool volumeMesh)
    {
        _envelope = envelope;
        _mesh = mesh;
        _topology = CadTopologyRegistry.Get(mesh);
        _volumeMesh = volumeMesh;
        Fit();
        _selectedFaceTag = null;
        Invalidate();
    }

    public void SetScopeMarkers(IEnumerable<int> supportTags, IEnumerable<int> loadTags)
    {
        _supportTags = supportTags.ToHashSet();
        _loadTags = loadTags.ToHashSet();
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
        var g = e.Graphics;
        g.Clear(Color.FromArgb(230, 239, 247));
        DrawGrid(g);
        _projected.Clear();
        if (_mesh is null || _topology is null || _envelope is null) return;

        var center = (_mesh.Min + _mesh.Max) / 2.0;
        var dimensions = _mesh.Max - _mesh.Min;
        var maximum = Math.Max(dimensions.X, Math.Max(dimensions.Y, dimensions.Z));
        var scale = Math.Min(ClientSize.Width, ClientSize.Height) * .62f * _zoom / Math.Max(maximum, 1e-9);
        var cy = MathF.Cos(_yaw);
        var sy = MathF.Sin(_yaw);
        var cp = MathF.Cos(_pitch);
        var sp = MathF.Sin(_pitch);

        (PointF Point, float Depth) Project(Vec3 original)
        {
            var p = original - center;
            var x = (float)p.X;
            var y = (float)p.Y;
            var z = (float)p.Z;
            var x1 = x * cy - y * sy;
            var y1 = x * sy + y * cy;
            var y2 = y1 * cp - z * sp;
            var z2 = y1 * sp + z * cp;
            return (new PointF(ClientSize.Width * .5f + _panX + x1 * (float)scale,
                               ClientSize.Height * .52f + _panY - z2 * (float)scale), y2);
        }

        var projectedNodes = _mesh.Nodes.Select(Project).ToArray();
        var triangles = _mesh.SurfaceTriangles.Select((triangle, index) => new AdvancedProjectedTriangle(
                _topology.TriangleFaceTags[index],
                [projectedNodes[triangle[0]].Point, projectedNodes[triangle[1]].Point, projectedNodes[triangle[2]].Point],
                (projectedNodes[triangle[0]].Depth + projectedNodes[triangle[1]].Depth + projectedNodes[triangle[2]].Depth) / 3f))
            .OrderBy(t => t.Depth).ToArray();
        _projected.AddRange(triangles);

        g.SmoothingMode = triangles.Length < 25000 ? SmoothingMode.AntiAlias : SmoothingMode.HighSpeed;
        var edgeStride = Math.Max(1, (int)Math.Ceiling(triangles.Length / 45000.0));
        using var edge = new Pen(Color.FromArgb(100, 35, 62, 82), .55f);
        for (var i = 0; i < triangles.Length; i++)
        {
            var triangle = triangles[i];
            var shade = maximum <= 1e-12 ? .5 : Math.Clamp((triangle.Depth + maximum / 2) / maximum, 0, 1);
            var fill = Blend(Color.FromArgb(55, 145, 194), Color.FromArgb(177, 220, 239), shade);
            using var brush = new SolidBrush(fill);
            g.FillPolygon(brush, triangle.Points);
            if (ShowMeshEdges && _volumeMesh && i % edgeStride == 0) g.DrawPolygon(edge, triangle.Points);
        }

        DrawScopes(g, triangles);
        DrawInformation(g);
        DrawTriad(g, cy, sy, cp, sp);
        PositionCameraBar();
        _cameraBar.BringToFront();
    }

    private ToolStrip BuildCameraBar()
    {
        var bar = new ToolStrip
        {
            GripStyle = ToolStripGripStyle.Hidden,
            RenderMode = ToolStripRenderMode.System,
            BackColor = Color.FromArgb(245, 250, 253),
            AutoSize = true,
            Padding = new Padding(4, 2, 4, 2)
        };
        Add("Fit", Fit);
        Add("ISO", () => SetView(-.65f, .42f));
        Add("Front", () => SetView(0, 0));
        Add("Right", () => SetView(MathF.PI / 2, 0));
        Add("Top", () => SetView(0, 1.53f));
        bar.Items.Add(new ToolStripSeparator());
        Add("Mesh", () => { ShowMeshEdges = !ShowMeshEdges; Invalidate(); });
        return bar;

        void Add(string text, Action action)
        {
            var button = new ToolStripButton(text) { DisplayStyle = ToolStripItemDisplayStyle.Text };
            button.Click += (_, _) => action();
            bar.Items.Add(button);
        }
    }

    private void Fit()
    {
        _zoom = 1f;
        _panX = _panY = 0;
        Invalidate();
    }

    private void SetView(float yaw, float pitch)
    {
        _yaw = yaw;
        _pitch = pitch;
        Fit();
    }

    private void PositionCameraBar()
    {
        _cameraBar.Left = Math.Max(12, ClientSize.Width - _cameraBar.Width - 18);
        _cameraBar.Top = 16;
    }

    private void DrawScopes(Graphics g, IReadOnlyList<AdvancedProjectedTriangle> triangles)
    {
        foreach (var triangle in triangles)
        {
            Color? color = _selectedFaceTag == triangle.FaceTag ? Color.FromArgb(195, 255, 183, 48) :
                _supportTags.Contains(triangle.FaceTag) ? Color.FromArgb(170, 0, 166, 160) :
                _loadTags.Contains(triangle.FaceTag) ? Color.FromArgb(170, 218, 61, 61) : null;
            if (color is null) continue;
            using var brush = new SolidBrush(color.Value);
            g.FillPolygon(brush, triangle.Points);
        }
    }

    private void SelectAt(Point point)
    {
        if (_topology is null) return;
        var hit = _projected.Where(t => PointInTriangle(point, t.Points[0], t.Points[1], t.Points[2]))
            .OrderBy(t => t.Depth).LastOrDefault();
        if (hit is null || !_topology.Faces.TryGetValue(hit.FaceTag, out var face)) return;
        _selectedFaceTag = face.Tag;
        Invalidate();
        _selectionCallback(new CadSurfaceSelection(face.Tag, face.TriangleIndices.Count, face.NodeIndices.Count, face.Centroid, face.Normal, face.AreaMm2));
    }

    private void DrawInformation(Graphics g)
    {
        if (_mesh is null || _topology is null) return;
        using var panel = new SolidBrush(Color.FromArgb(225, 255, 255, 255));
        g.FillRectangle(panel, 14, 14, Math.Min(720, Math.Max(300, ClientSize.Width - 260)), 82);
        using var title = new Font("Segoe UI Semibold", 10.5f);
        using var text = new Font("Segoe UI", 8.5f);
        g.DrawString(_volumeMesh ? "Tetrahedral volume mesh" : "STEP surface preview", title, Brushes.DarkSlateGray, 25, 23);
        g.DrawString($"{_mesh.Nodes.Count:N0} nodes · {_mesh.Tetrahedra.Count:N0} TET4 · {_topology.Faces.Count:N0} selectable faces", text, Brushes.SlateGray, 25, 47);
        g.DrawString("MMB/Ctrl+drag: orbit · RMB/Shift+MMB: pan · Wheel: zoom · Mesh: edges on/off", text, Brushes.SlateGray, 25, 67);
    }

    private void DrawGrid(Graphics g)
    {
        using var pen = new Pen(Color.FromArgb(35, 90, 120, 145), .7f);
        var horizon = ClientSize.Height * .78f;
        for (var i = -14; i <= 14; i++)
        {
            var x = ClientSize.Width / 2f + i * 50f;
            g.DrawLine(pen, x, horizon - 55, x + i * 9, ClientSize.Height);
        }
        for (var row = 0; row < 8; row++)
        {
            var y = horizon + row * row * 4.2f;
            g.DrawLine(pen, 0, y, ClientSize.Width, y);
        }
    }

    private static void DrawTriad(Graphics g, float cy, float sy, float cp, float sp)
    {
        var origin = new PointF(g.VisibleClipBounds.Right - 65, g.VisibleClipBounds.Bottom - 55);
        DrawAxis(new Vec3(1, 0, 0), "X", Pens.Red, Brushes.Firebrick);
        DrawAxis(new Vec3(0, 1, 0), "Y", Pens.Green, Brushes.ForestGreen);
        DrawAxis(new Vec3(0, 0, 1), "Z", Pens.Blue, Brushes.RoyalBlue);

        void DrawAxis(Vec3 axis, string label, Pen pen, Brush brush)
        {
            var x = (float)axis.X * cy - (float)axis.Y * sy;
            var y = (float)axis.X * sy + (float)axis.Y * cy;
            var z = y * sp + (float)axis.Z * cp;
            var end = new PointF(origin.X + x * 34, origin.Y - z * 34);
            g.DrawLine(pen, origin, end);
            g.DrawString(label, SystemFonts.SmallCaptionFont, brush, end.X, end.Y);
        }
    }

    private static bool PointInTriangle(Point point, PointF a, PointF b, PointF c)
    {
        static float Sign(PointF p1, PointF p2, PointF p3) => (p1.X - p3.X) * (p2.Y - p3.Y) - (p2.X - p3.X) * (p1.Y - p3.Y);
        var p = new PointF(point.X, point.Y);
        var d1 = Sign(p, a, b);
        var d2 = Sign(p, b, c);
        var d3 = Sign(p, c, a);
        return !((d1 < 0 || d2 < 0 || d3 < 0) && (d1 > 0 || d2 > 0 || d3 > 0));
    }

    private static Color Blend(Color first, Color second, double amount)
    {
        amount = Math.Clamp(amount, 0, 1);
        return Color.FromArgb((int)(first.R + (second.R - first.R) * amount),
            (int)(first.G + (second.G - first.G) * amount),
            (int)(first.B + (second.B - first.B) * amount));
    }

    private sealed record AdvancedProjectedTriangle(int FaceTag, PointF[] Points, float Depth);
}
