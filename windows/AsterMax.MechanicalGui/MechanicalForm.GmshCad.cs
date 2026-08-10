namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private string? _cadStepPath;
    private SimpleStepSolid? _cadEnvelope;
    private CadModelMetadata? _cadMetadata;
    private CadMesh? _cadSurfacePreview;
    private CadMesh? _cadVolumeMesh;
    private SelectableCadMeshCanvas? _cadCanvas;
    private OperationController? _activeOperation;
    private System.Windows.Forms.Timer? _activeOperationUiTimer;

    private TimeSpan PreviewTimeout => ReadTimeout("ASTERMAX_STEP_PREVIEW_TIMEOUT_SECONDS", 60);
    private TimeSpan VolumeMeshTimeout => ReadTimeout("ASTERMAX_STEP_VOLUME_TIMEOUT_SECONDS", 180);

    private async Task ImportCadStepAsync(string path)
    {
        if (_busy) return;

        var gmsh = GmshCliMesher.FindExecutable();
        if (gmsh is null)
        {
            MessageBox.Show(this,
                "AsterMax requires the bundled tools\\gmsh\\gmsh.exe for general STEP import. " +
                "Use the complete Windows package or configure GMSH_EXE.",
                "Gmsh engine not found",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            return;
        }

        using var operation = BeginOperation("File validation", "Preparing transactional STEP import.");
        try
        {
            var result = await StepImportService.ImportSurfaceAsync(gmsh, path, operation, PreviewTimeout);
            operation.Token.ThrowIfCancellationRequested();

            operation.Report("Commit model", "Replacing the active model only after successful validation.", 0.97);
            if (result.VerifiedPrismFastPath is { } prism)
                CommitVerifiedPrismFastPath(path, prism, result.Metadata, result.Diagnostics);
            else
                CommitGeneralCadImport(path, result);

            operation.Complete(OperationOutcome.Succeeded,
                $"STEP import succeeded in {operation.Elapsed.TotalSeconds:0.00} s.");
            _statusMain.Text = "STEP loaded — click a face or generate the real volume mesh";
        }
        catch (OperationCanceledException)
        {
            operation.Complete(OperationOutcome.Cancelled, "STEP import cancelled; previous model preserved.");
            Log("STEP IMPORT CANCELLED: previous model preserved; temporary workspace cleaned.");
            _statusMain.Text = "STEP import cancelled — previous model preserved";
        }
        catch (TimeoutException exception)
        {
            operation.Complete(OperationOutcome.TimedOut, exception.Message);
            Log("STEP IMPORT TIMEOUT: " + exception.Message);
            MessageBox.Show(this, exception.Message, "STEP import timed out", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            _statusMain.Text = "STEP import timed out — previous model preserved";
        }
        catch (Exception exception)
        {
            operation.Complete(OperationOutcome.Failed, exception.Message);
            Log("GMSH STEP IMPORT ERROR: " + exception);
            MessageBox.Show(this, exception.Message, "STEP import failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            _statusMain.Text = "STEP import failed — previous model preserved";
        }
        finally
        {
            EndOperation(operation);
        }
    }

    private void CommitGeneralCadImport(string path, CadImportResult result)
    {
        // Transaction commit boundary: destructive state changes begin only after OCC + mesh validation succeeded.
        ClearSimpleStateForCadImport();
        ResetCadState();

        var preview = result.Surface.Mesh;
        var metadata = result.Metadata;
        _cadStepPath = path;
        _cadMetadata = metadata;
        _cadEnvelope = CompatibilityEnvelope(metadata);
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
        bodyObject.Properties["Length X"] = $"{metadata.Dimensions.X:0.###} mm";
        bodyObject.Properties["Length Y"] = $"{metadata.Dimensions.Y:0.###} mm";
        bodyObject.Properties["Length Z"] = $"{metadata.Dimensions.Z:0.###} mm";
        bodyObject.Properties["Volume"] = $"{metadata.VolumeMm3:0.###} mm³";
        bodyObject.Properties["Closed Solid"] = metadata.IsClosed ? "Yes" : "No";
        bodyObject.Properties["Solid Count"] = metadata.SolidCount.ToString();
        bodyObject.Properties["Selectable Faces"] = topology.Faces.Count.ToString("N0");
        bodyObject.Properties["Surface Nodes"] = preview.Nodes.Count.ToString("N0");
        bodyObject.Properties["Surface Triangles"] = preview.SurfaceTriangles.Count.ToString("N0");
        bodyObject.Properties["Source Unit"] = metadata.SourceUnit;
        bodyObject.Properties["Internal Unit"] = "millimetre";
        bodyObject.Properties["SHA-256"] = metadata.Sha256;
        bodyObject.Properties["Material"] = _simpleMaterial.Name;
        bodyObject.Properties["Source"] = path;
        bodyObject.Properties["CAD Engine"] = $"Gmsh / OpenCASCADE ({metadata.GmshVersion})";
        geometry.Nodes.Add(body);
        geometry.Expand();
        SetState(geometry, ObjectState.UpToDate);
        SetState(_nodes["Model"], ObjectState.Ready);
        SetState(_nodes["Mesh"], ObjectState.NeedsAttention);
        MarkSolutionDirty();

        EnsureCadCanvas().SetMesh(_cadEnvelope, preview, false);
        SelectNode("Geometry");
        Log("REAL STEP PREVIEW: " + result.Diagnostics);
        Log("Normal left click selects a complete OpenCASCADE face. Ctrl + drag or middle drag rotates the model.");
    }

    private void CommitVerifiedPrismFastPath(string path, SimpleStepSolid solid, CadModelMetadata metadata, string diagnostics)
    {
        // The fast path is selected only after OCC has already accepted the file. It never validates or rejects general CAD.
        ResetCadState();
        _simpleSolid = solid;
        _simpleMesh = null;
        _simpleSolution = null;
        _simpleSetupDefined = false;
        _geometryPath = path;
        _meshGenerated = false;
        _solved = false;
        _viewport.SetSolid(solid);
        _viewport.MeshVisible = false;
        _viewport.ResultVisible = false;
        _viewport.SupportVisible = false;
        _viewport.ForceVisible = false;

        var geometry = _nodes["Geometry"];
        geometry.Nodes.Clear();
        var body = MakeNode(Path.GetFileNameWithoutExtension(path), ObjectKind.Body, ObjectState.UpToDate, "Verified Prismatic Solid");
        var bodyObject = (ModelObject)body.Tag;
        bodyObject.Properties["Geometry Fidelity"] = "OCC-verified rectangular STEP; optimized structured path";
        bodyObject.Properties["Length X"] = $"{solid.LengthX:0.###} mm";
        bodyObject.Properties["Length Y"] = $"{solid.LengthY:0.###} mm";
        bodyObject.Properties["Length Z"] = $"{solid.LengthZ:0.###} mm";
        bodyObject.Properties["Volume"] = $"{solid.Volume:0.###} mm³";
        bodyObject.Properties["Source Unit"] = metadata.SourceUnit;
        bodyObject.Properties["SHA-256"] = metadata.Sha256;
        bodyObject.Properties["Material"] = _simpleMaterial.Name;
        bodyObject.Properties["Source"] = path;
        bodyObject.Properties["CAD Validation"] = "Gmsh / OpenCASCADE passed before fast-path selection";
        geometry.Nodes.Add(body);
        geometry.Expand();
        SetState(geometry, ObjectState.UpToDate);
        SetState(_nodes["Mesh"], ObjectState.NeedsAttention);
        MarkSolutionDirty();
        _outline.SelectedNode = body;
        Log("REAL STEP IMPORT / VERIFIED PRISM FAST PATH: " + diagnostics);
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
        if (_cadStepPath is null || _cadMetadata is null || _cadEnvelope is null)
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

        var dimensions = _cadMetadata.Dimensions;
        var longest = Math.Max(dimensions.X, Math.Max(dimensions.Y, dimensions.Z));
        using var dialog = new GmshMeshSizeDialog(Math.Max(longest / 12.0, longest * 1e-4));
        if (dialog.ShowDialog(this) != DialogResult.OK) return;

        using var operation = BeginOperation("Volume mesh", "Generating unstructured tetrahedral mesh with Gmsh/OpenCASCADE.");
        try
        {
            var run = await ManagedGmshMesher.GenerateAsync(
                gmsh,
                _cadStepPath,
                dialog.TargetSizeMm,
                3,
                VolumeMeshTimeout,
                operation.Token);
            var mesh = run.Mesh;
            if (mesh.Tetrahedra.Count == 0)
                throw new InvalidDataException("Gmsh did not generate tetrahedral volume elements. Verify that the STEP contains a closed solid volume.");

            operation.Report("MSH parse", "Validating volume elements and selectable surface topology.", 0.88);
            var volumeMetadata = StepImportService.MetadataFromVolume(_cadMetadata, mesh);
            if (!volumeMetadata.IsClosed || volumeMetadata.VolumeMm3 <= 0)
                throw new InvalidDataException("Generated volume mesh failed closed-solid or positive-volume verification.");

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
                meshObject.Properties["Mesh Volume"] = $"{volumeMetadata.VolumeMm3:0.###} mm³";
            }
            MarkSolutionDirty();
            EnsureCadCanvas().SetMesh(_cadEnvelope, mesh, true);
            RefreshCadScopeMarkers();
            PopulateCadMeshTable(mesh, dialog.TargetSizeMm);
            SelectLowerTab("Worksheet");
            SelectNode("Mesh");
            Log($"REAL GMSH VOLUME MESH: {mesh.Nodes.Count:N0} nodes, {mesh.SurfaceTriangles.Count:N0} boundary triangles, {mesh.Tetrahedra.Count:N0} TET4, {topology.Faces.Count:N0} selectable faces; {run.Elapsed.TotalMilliseconds:0} ms; gmsh={run.Version}.");
            operation.Complete(OperationOutcome.Succeeded, $"Volume mesh complete in {operation.Elapsed.TotalSeconds:0.00} s.");
            _statusMain.Text = "Volume mesh ready — click a face, then insert Fixed Support or Force";
        }
        catch (OperationCanceledException)
        {
            operation.Complete(OperationOutcome.Cancelled, "Volume mesh cancelled; previous mesh state preserved.");
            Log("GMSH VOLUME MESH CANCELLED: previous mesh state preserved.");
            _statusMain.Text = "Volume mesh cancelled";
        }
        catch (TimeoutException exception)
        {
            operation.Complete(OperationOutcome.TimedOut, exception.Message);
            Log("GMSH VOLUME MESH TIMEOUT: " + exception.Message);
            MessageBox.Show(this, exception.Message, "Gmsh meshing timed out", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        catch (Exception exception)
        {
            operation.Complete(OperationOutcome.Failed, exception.Message);
            Log("GMSH MESH ERROR: " + exception);
            MessageBox.Show(this, exception.Message, "Gmsh meshing failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            EndOperation(operation);
        }
    }

    private OperationController BeginOperation(string stage, string detail)
    {
        var operation = new OperationController();
        _activeOperation = operation;
        _busy = true;
        ToggleUi(false);
        Cursor = Cursors.WaitCursor;
        operation.ProgressChanged += HandleOperationProgress;
        operation.Report(stage, detail, 0.01);
        ShowOperationOverlay(stage + Environment.NewLine + detail);
        EnsureOperationOverlayControls();
        _activeOperationUiTimer = new System.Windows.Forms.Timer { Interval = 250 };
        _activeOperationUiTimer.Tick += (_, _) => RefreshOperationOverlayClock();
        _activeOperationUiTimer.Start();
        RefreshOperationOverlayClock();
        return operation;
    }

    private void EndOperation(OperationController operation)
    {
        if (_activeOperationUiTimer is not null)
        {
            _activeOperationUiTimer.Stop();
            _activeOperationUiTimer.Dispose();
            _activeOperationUiTimer = null;
        }
        operation.ProgressChanged -= HandleOperationProgress;
        if (ReferenceEquals(_activeOperation, operation)) _activeOperation = null;
        _busy = false;
        ToggleUi(true);
        Cursor = Cursors.Default;
        CloseOperationOverlay();
    }

    private void HandleOperationProgress(OperationProgress progress)
    {
        if (IsDisposed) return;
        if (InvokeRequired)
        {
            BeginInvoke(() => HandleOperationProgress(progress));
            return;
        }
        _statusMain.Text = $"{progress.Stage}: {progress.Detail}";
        ShowOperationOverlay("Processing geometry…");
        EnsureOperationOverlayControls();
        var detail = _operationOverlay?.Controls.Find("OperationStageDetail", true).FirstOrDefault() as Label;
        if (detail is not null) detail.Text = $"{progress.Stage}\n{progress.Detail}";
        RefreshOperationOverlayClock();
    }

    private void EnsureOperationOverlayControls()
    {
        if (_operationOverlay is null || _operationOverlay.IsDisposed) return;
        if (_operationOverlay.Controls.Find("OperationFooter", true).Length > 0) return;

        _operationOverlay.Height = 195;
        var footer = new Panel
        {
            Name = "OperationFooter",
            Dock = DockStyle.Bottom,
            Height = 68,
            Padding = new Padding(10, 4, 10, 6),
            BackColor = Panel
        };
        var detail = new Label
        {
            Name = "OperationStageDetail",
            Dock = DockStyle.Fill,
            Text = "Preparing operation…",
            TextAlign = ContentAlignment.MiddleLeft,
            ForeColor = TextMain,
            AutoEllipsis = true
        };
        var elapsed = new Label
        {
            Name = "OperationElapsed",
            Dock = DockStyle.Right,
            Width = 90,
            TextAlign = ContentAlignment.MiddleCenter,
            ForeColor = TextMuted
        };
        var cancel = new Button
        {
            Name = "OperationCancel",
            Dock = DockStyle.Right,
            Width = 86,
            Text = "Cancel",
            UseVisualStyleBackColor = true
        };
        cancel.Click += (_, _) =>
        {
            cancel.Enabled = false;
            cancel.Text = "Cancelling…";
            _activeOperation?.Cancel();
        };
        footer.Controls.Add(detail);
        footer.Controls.Add(elapsed);
        footer.Controls.Add(cancel);
        _operationOverlay.Controls.Add(footer);
        footer.BringToFront();
    }

    private void RefreshOperationOverlayClock()
    {
        if (_operationOverlay is null || _activeOperation is null) return;
        var elapsed = _operationOverlay.Controls.Find("OperationElapsed", true).FirstOrDefault() as Label;
        if (elapsed is not null) elapsed.Text = $"{_activeOperation.Elapsed.TotalSeconds:0.0} s";
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
        _cadMetadata = null;
        _cadSurfacePreview = null;
        _cadVolumeMesh = null;
        HideCadCanvas();
    }

    private static SimpleStepSolid CompatibilityEnvelope(CadModelMetadata metadata) => new()
    {
        SourcePath = metadata.SourcePath,
        Min = metadata.Min,
        Max = metadata.Max,
        CartesianPointCount = 0,
        IsSupportedPrism = false,
        FidelityMessage = "Compatibility display envelope derived from OpenCASCADE mesh metadata; not used as a CAD validity gate."
    };

    private static TimeSpan ReadTimeout(string variable, double fallbackSeconds)
    {
        var text = Environment.GetEnvironmentVariable(variable);
        return double.TryParse(text, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var seconds) &&
               double.IsFinite(seconds) && seconds > 0
            ? TimeSpan.FromSeconds(seconds)
            : TimeSpan.FromSeconds(fallbackSeconds);
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
