namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private string? _cadStepPath;
    private SimpleStepSolid? _cadEnvelope;
    private CadMesh? _cadSurfacePreview;
    private CadMesh? _cadVolumeMesh;
    private SelectableCadMeshCanvas? _cadCanvas;

    private async Task ImportCadStepAsync(string path)
    {
        if (_busy) return;
        ClearSimpleStateForCadImport();
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
            _statusMain.Text = "Importing STEP through OpenCASCADE and building selectable surfaces…";
            var longest = Math.Max(envelope.LengthX, Math.Max(envelope.LengthY, envelope.LengthZ));
            var previewSize = Math.Max(longest / 24.0, longest * 1e-4);
            var preview = await SelectableGmshMesher.GenerateAsync(gmsh, path, previewSize, 2, CancellationToken.None);
            if (preview.SurfaceTriangles.Count == 0)
                throw new InvalidDataException("Gmsh imported the STEP but did not generate surface triangles.");

            _cadStepPath = path;
            _cadEnvelope = envelope;
            _cadSurfacePreview = preview;
            _cadVolumeMesh = null;
            _geometryPath = path;
            _meshGenerated = false;
            _solved = false;

            var topology = CadTopologyRegistry.Get(preview);
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
            bodyObject.Properties["Selectable Faces"] = topology.Faces.Count.ToString("N0");
            bodyObject.Properties["Material"] = _simpleMaterial.Name;
            bodyObject.Properties["Source"] = path;
            bodyObject.Properties["CAD Engine"] = "Gmsh / OpenCASCADE";
            geometry.Nodes.Add(body);
            geometry.Expand();
            SetState(geometry, ObjectState.UpToDate);
            SetState(_nodes["Model"], ObjectState.Ready);
            SetState(_nodes["Mesh"], ObjectState.NeedsAttention);
            MarkSolutionDirty();

            EnsureCadCanvas().SetMesh(envelope, preview, false);
            SelectNode("Geometry");
            Log($"REAL STEP PREVIEW: {Path.GetFileName(path)}; {preview.Nodes.Count:N0} nodes, {preview.SurfaceTriangles.Count:N0} surface triangles, {topology.Faces.Count:N0} selectable faces.");
            Log("Normal left click selects a complete OpenCASCADE face. Ctrl + drag or middle drag rotates the model.");
            _statusMain.Text = "STEP loaded — click a face or generate the real volume mesh";
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

    private void ClearSimpleStateForCadImport()
    {
        _simpleSolid = null;
        _simpleMesh = null;
        _simpleSolution = null;
        _simpleSetupDefined = false;
        foreach (var node in AllNodes().Where(node =>
                     node.Tag is ModelObject model &&
                     model.Properties.TryGetValue("Tutorial", out var tutorial) &&
                     tutorial == "SimpleStatic").ToArray())
            node.Remove();
        _viewport.ClearModel();
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
            var mesh = await SelectableGmshMesher.GenerateAsync(gmsh, _cadStepPath, dialog.TargetSizeMm, 3, CancellationToken.None);
            if (mesh.Tetrahedra.Count == 0)
                throw new InvalidDataException("Gmsh did not generate tetrahedral volume elements. Verify that the STEP contains a closed solid volume.");

            _cadVolumeMesh = mesh;
            _meshGenerated = true;
            _solved = false;
            var topology = CadTopologyRegistry.Get(mesh);
            SetState(_nodes["Mesh"], ObjectState.UpToDate);
            if (_nodes["Mesh"].Tag is ModelObject meshObject)
            {
                meshObject.Properties["Mesher"] = "Gmsh OpenCASCADE unstructured TET4";
                meshObject.Properties["Element Order"] = "Linear / TET4";
                meshObject.Properties["Target Size"] = $"{dialog.TargetSizeMm:0.###} mm";
                meshObject.Properties["Nodes"] = mesh.Nodes.Count.ToString("N0");
                meshObject.Properties["Surface Triangles"] = mesh.SurfaceTriangles.Count.ToString("N0");
                meshObject.Properties["Tetrahedra"] = mesh.Tetrahedra.Count.ToString("N0");
                meshObject.Properties["Selectable Faces"] = topology.Faces.Count.ToString("N0");
            }
            MarkSolutionDirty();
            EnsureCadCanvas().SetMesh(_cadEnvelope, mesh, true);
            RefreshCadScopeMarkers();
            PopulateCadMeshTable(mesh, dialog.TargetSizeMm);
            SelectLowerTab("Worksheet");
            SelectNode("Mesh");
            Log($"REAL GMSH VOLUME MESH: {mesh.Nodes.Count:N0} nodes, {mesh.SurfaceTriangles.Count:N0} boundary triangles, {mesh.Tetrahedra.Count:N0} TET4, {topology.Faces.Count:N0} selectable faces.");
            _statusMain.Text = "Volume mesh ready — click a face, then insert Fixed Support or Force";
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
        var topology = CadTopologyRegistry.Get(mesh);
        _worksheet.Columns.Clear();
        _worksheet.Rows.Clear();
        _worksheet.Columns.Add("Property", "Mesh Property");
        _worksheet.Columns.Add("Value", "Value");
        _worksheet.Rows.Add("CAD kernel", "OpenCASCADE through Gmsh");
        _worksheet.Rows.Add("Displayed geometry", "Closed exterior skin only");
        _worksheet.Rows.Add("Element type", "Linear tetrahedron / TET4");
        _worksheet.Rows.Add("Target size", $"{targetSizeMm:0.###} mm");
        _worksheet.Rows.Add("Nodes", mesh.Nodes.Count.ToString("N0"));
        _worksheet.Rows.Add("Boundary triangles", mesh.SurfaceTriangles.Count.ToString("N0"));
        _worksheet.Rows.Add("Volume tetrahedra", mesh.Tetrahedra.Count.ToString("N0"));
        _worksheet.Rows.Add("Selectable CAD faces", topology.Faces.Count.ToString("N0"));
        _worksheet.Rows.Add("Boundary-condition status", "Click a face to scope supports and loads");
    }

    private SelectableCadMeshCanvas EnsureCadCanvas()
    {
        _cadCanvas ??= new SelectableCadMeshCanvas(HandleCadFaceSelected);
        if (_cadCanvas.Parent != _viewport)
        {
            _cadCanvas.Dock = DockStyle.Fill;
            _viewport.Controls.Add(_cadCanvas);
        }
        _cadCanvas.Visible = true;
        _cadCanvas.BringToFront();
        RefreshCadScopeMarkers();
        return _cadCanvas;
    }

    private void HideCadCanvas()
    {
        if (_cadCanvas is not null) _cadCanvas.Visible = false;
    }

    private void ResetCadState()
    {
        _selectedCadSurfaceTag = null;
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
            Text = "Smaller values create more tetrahedra and require more memory. Start coarse and refine only after checking the boundary-condition faces.",
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
