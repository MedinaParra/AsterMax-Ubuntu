namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private bool _stableSelectionInstalled;
    private bool _stableSelectionBusy;
    private bool _uiSmokeRunning;

    internal void InstallStableSelectionController()
    {
        if (_stableSelectionInstalled) return;
        _stableSelectionInstalled = true;
        ConfigureDetailsMinimumWidths();

        _outline.BeforeSelect += (_, e) => RenderDetailsSelection(e.Node, "before-select");
        _outline.AfterSelect += (_, e) => CompleteSelectionContext(e.Node, "after-select");
        FormClosing += (_, e) =>
        {
            if (_uiSmokeRunning) e.Cancel = true;
        };

        Shown += async (_, _) =>
        {
            if (IsDisposed || !IsHandleCreated) return;
            CompleteSelectionContext(_outline.SelectedNode, "shown");
            await RunStableSelectionSmokeIfRequestedAsync();
        };
    }

    private void RenderDetailsSelection(TreeNode? node, string source)
    {
        if (IsDisposed || node?.Tag is not ModelObject model) return;
        if (_details.IsCurrentCellInEditMode)
        {
            try { _details.EndEdit(); } catch { _details.CancelEdit(); }
        }
        try { _details.CurrentCell = null; } catch { }

        _statusSelection.Text = $"Selected: {model.Name}";
        _contextTitle.Text = $"{model.Category}\n{model.Name}";
        UpdateDetails(node);
        var renderedName = ReadRenderedDetailsName();
        if (!string.Equals(renderedName, model.Name, StringComparison.Ordinal))
            throw new InvalidOperationException(
                $"Details invariant failed: tree='{model.Name}', details='{renderedName ?? "<none>"}', source={source}.");
        _details.Invalidate();
        _status.Invalidate();
    }

    private void CompleteSelectionContext(TreeNode? node, string source)
    {
        if (_stableSelectionBusy || IsDisposed || node?.Tag is not ModelObject) return;
        try
        {
            _stableSelectionBusy = true;
            ReconcileGeometryVisualState();
            EnsureExclusiveGraphicsSurface();
            RenderDetailsSelection(node, source);
            UpdateContextCommands(node);
            PopulateWorksheet(node);
            HighlightWorkflow(node);
            RefreshProductionSelectionFeedback();
            if (!IsCadGraphicsActive())
                UpdateViewport(node);
            _outline.Invalidate();
        }
        finally
        {
            _stableSelectionBusy = false;
        }
    }

    private bool IsCadGraphicsActive() =>
        _cadCanvas is not null &&
        _cadSurfacePreview is not null &&
        !string.IsNullOrWhiteSpace(_geometryPath);

    /// <summary>
    /// Keep CAD and the legacy MechanicalViewport as mutually exclusive sibling paint
    /// surfaces. The decision is based on model state, never Control.Visible: WinForms can
    /// transiently report Visible=false while a control is being reparented/layouted, and
    /// using that value as application state caused the CAD view to be disabled again.
    /// </summary>
    private void EnsureExclusiveGraphicsSurface()
    {
        if (IsCadGraphicsActive() && _cadCanvas is { } cad)
        {
            var graphicsHost = _viewport.Parent;
            if (graphicsHost is null) return;

            graphicsHost.SuspendLayout();
            try
            {
                if (!ReferenceEquals(cad.Parent, graphicsHost))
                {
                    cad.Parent?.Controls.Remove(cad);
                    graphicsHost.Controls.Add(cad);
                    SmokeTrace("cad-promoted-to-sibling-host");
                }

                cad.Anchor = AnchorStyles.None;
                cad.Dock = DockStyle.Fill;
                _viewport.Visible = false;
                cad.Visible = true;
                cad.BringToFront();
            }
            finally
            {
                graphicsHost.ResumeLayout(true);
            }
            return;
        }

        if (_cadCanvas is not null)
            _cadCanvas.Visible = false;
        _viewport.Visible = true;
        _viewport.BringToFront();
    }

    private void ActivateStableTreeNode(TreeNode? node, string source)
    {
        RenderDetailsSelection(node, source + ":details");
        CompleteSelectionContext(node, source + ":context");
    }

    private void ConfigureDetailsMinimumWidths()
    {
        if (_details.Columns.Count < 2) return;
        _details.Columns[0].MinimumWidth = 110;
        _details.Columns[1].MinimumWidth = 140;
        _details.Columns[0].FillWeight = 43;
        _details.Columns[1].FillWeight = 57;
    }

    private string? ReadRenderedDetailsName()
    {
        foreach (DataGridViewRow row in _details.Rows)
        {
            if (!string.Equals(row.Cells[0].Value?.ToString(), "Name", StringComparison.OrdinalIgnoreCase)) continue;
            return row.Cells.Count > 1 ? row.Cells[1].Value?.ToString() : null;
        }
        return null;
    }

    internal void InitializeStableProductionInteractions()
    {
        if (_productionInteractionsInitialized) return;
        _productionInteractionsInitialized = true;
        ConfigureDetailsSelectionExperience();
        KeyDown += HandleNavigationShortcut;
        FormClosed += (_, _) => CloseOperationOverlay();
    }

    private void ReconcileGeometryVisualState()
    {
        if (!_nodes.TryGetValue("Model", out var modelNode)) return;
        if (!_nodes.TryGetValue("Geometry", out var geometryNode) || geometryNode.TreeView != _outline)
        {
            _nodes.Remove("Geometry");
            geometryNode = MakeNode("Geometry", ObjectKind.Geometry, ObjectState.NeedsAttention, "Geometry");
            modelNode.Nodes.Insert(0, geometryNode);
        }
        foreach (var key in _nodes
                     .Where(pair => pair.Value.TreeView != _outline && !ReferenceEquals(pair.Value, geometryNode))
                     .Select(pair => pair.Key)
                     .ToArray())
            _nodes.Remove(key);
        if (geometryNode.Nodes.Count == 0 && !string.IsNullOrWhiteSpace(_geometryPath))
            ClearImportedGeometryVisualState(geometryNode);
    }

    private void ClearImportedGeometryVisualState(TreeNode geometryNode)
    {
        ResetCadState();
        _geometryPath = null;
        _meshGenerated = false;
        _solved = false;
        _simpleSolid = null;
        _simpleMesh = null;
        _simpleSolution = null;
        _simpleSetupDefined = false;
        _viewport.ClearModel();
        _viewport.MeshVisible = false;
        _viewport.ResultVisible = false;
        _viewport.SupportVisible = false;
        _viewport.ForceVisible = false;
        _viewport.Caption = "Geometry";
        _viewport.SubCaption = "No geometry imported";
        EnsureExclusiveGraphicsSurface();
        _viewport.Invalidate();
        foreach (var scopedNode in AllNodes().Where(node =>
                     node.Tag is ModelObject { Kind: ObjectKind.Support or ObjectKind.Load }).ToArray())
        {
            if (scopedNode.Tag is not ModelObject scoped) continue;
            scoped.Properties.Remove("CadSurfaceTag");
            if (!string.Equals(scoped.Properties.GetValueOrDefault("Geometry"), "All Bodies", StringComparison.OrdinalIgnoreCase))
                scoped.Properties["Geometry"] = "Unscoped";
            SetState(scopedNode, ObjectState.NeedsAttention);
        }
        SetState(geometryNode, ObjectState.NeedsAttention);
        SetState(_nodes.GetValueOrDefault("Model"), ObjectState.NeedsAttention);
        SetState(_nodes.GetValueOrDefault("Mesh"), ObjectState.NeedsAttention);
        MarkSolutionDirty();
        Log("GEOMETRY CLEARED: CAD mesh, preview, solver state and viewport were released together.");
    }

    private static void SmokeTrace(string stage)
    {
        var path = Environment.GetEnvironmentVariable("ASTERMAX_UI_SMOKE_LOG");
        if (string.IsNullOrWhiteSpace(path)) return;
        try
        {
            var directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);
            File.AppendAllText(path, $"{DateTimeOffset.Now:O} | {stage}{Environment.NewLine}");
        }
        catch { }
    }

    private async Task RunStableSelectionSmokeIfRequestedAsync()
    {
        var args = Environment.GetCommandLineArgs();
        if (!args.Any(arg => string.Equals(arg, "--startup-smoke", StringComparison.OrdinalIgnoreCase))) return;

        var success = false;
        _uiSmokeRunning = true;
        try
        {
            SmokeTrace("start");
            void SelectThroughRealTreeEvents(TreeNode node, string stage)
            {
                SmokeTrace("select-begin:" + stage + ":" + node.Text);
                if (ReferenceEquals(_outline.SelectedNode, node))
                {
                    var alternate = AllNodes().FirstOrDefault(candidate => !ReferenceEquals(candidate, node));
                    if (alternate is not null) _outline.SelectedNode = alternate;
                }
                _outline.SelectedNode = node;
                node.EnsureVisible();
                Application.DoEvents();
                if (node.Tag is not ModelObject model)
                    throw new InvalidOperationException($"GUI smoke ({stage}): node has no ModelObject.");
                if (!string.Equals(ReadRenderedDetailsName(), model.Name, StringComparison.Ordinal))
                    throw new InvalidOperationException(
                        $"GUI smoke ({stage}): Details='{ReadRenderedDetailsName()}' while tree='{model.Name}'.");
                if (!_statusSelection.Text.Contains(model.Name, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException(
                        $"GUI smoke ({stage}): status='{_statusSelection.Text}' while tree='{model.Name}'.");
                SmokeTrace("select-pass:" + stage + ":" + model.Name);
            }

            var initialSequence = new[]
            {
                _nodes.GetValueOrDefault("Geometry"), _nodes.GetValueOrDefault("Connections"), FirstAnalysis(),
                AllNodes().FirstOrDefault(node => node.Tag is ModelObject { Kind: ObjectKind.SolutionInformation }),
                AllNodes().FirstOrDefault(node => node.Tag is ModelObject { Kind: ObjectKind.Result })
            }.Where(node => node is not null).Cast<TreeNode>().ToArray();
            foreach (var node in initialSequence) SelectThroughRealTreeEvents(node, "before-cad");
            SmokeTrace("empty-tree-sequence-pass");

            var cylinder = Environment.GetEnvironmentVariable("ASTERMAX_STARTUP_STEP");
            if (string.IsNullOrWhiteSpace(cylinder))
                cylinder = Path.Combine(Environment.CurrentDirectory, "windows", "AsterMax.MechanicalGui", "TestData", "CILINDRO-SIMPLE.stp");

            if (File.Exists(cylinder) && GmshCliMesher.FindExecutable() is { } gmsh)
            {
                SmokeTrace("occ-import-begin");
                using var smokeOperation = new OperationController();
                var result = await StepImportService.ImportSurfaceAsync(gmsh, cylinder, smokeOperation, PreviewTimeout);
                SmokeTrace($"occ-import-pass:nodes={result.Surface.Mesh.Nodes.Count}:tri={result.Surface.Mesh.SurfaceTriangles.Count}");
                CommitGeneralCadImport(cylinder, result);
                SmokeTrace("commit-general-cad-pass");
                EnsureExclusiveGraphicsSurface();
                SmokeTrace("exclusive-graphics-pass");
                Application.DoEvents();
                SmokeTrace("post-commit-doevents-pass");

                if (string.IsNullOrWhiteSpace(_geometryPath) || _nodes["Geometry"].Nodes.Count == 0)
                    throw new InvalidOperationException("GUI smoke: real STEP import did not commit Geometry.");
                SmokeTrace("post-cad-geometry-state-pass");
                if (!IsCadGraphicsActive() || _cadCanvas is not { Visible: true })
                    throw new InvalidOperationException("GUI smoke: responsive CAD canvas is not visible after STEP import.");
                SmokeTrace("post-cad-canvas-visible-pass");
                if (_cadCanvas.Parent == _viewport)
                    throw new InvalidOperationException("GUI smoke: CAD canvas is still nested inside MechanicalViewport.");
                SmokeTrace("post-cad-sibling-pass");

                var analysis = FirstAnalysis() ?? throw new InvalidOperationException("GUI smoke: analysis missing.");
                SmokeTrace("post-cad-analysis-found");
                SelectThroughRealTreeEvents(analysis, "cad-analysis");
                SmokeTrace("add-support-begin");
                AddSupport("Fixed Support");
                Application.DoEvents();
                SmokeTrace("add-support-doevents-pass");
                var support = _outline.SelectedNode;
                if (support?.Tag is not ModelObject { Kind: ObjectKind.Support })
                    throw new InvalidOperationException("GUI smoke: Fixed Support insertion did not select the support.");
                SelectThroughRealTreeEvents(support, "cad-fixed-support");
                SelectThroughRealTreeEvents(_nodes["Connections"], "cad-connections");
                var solutionInformation = AllNodes().First(node => node.Tag is ModelObject { Kind: ObjectKind.SolutionInformation });
                SelectThroughRealTreeEvents(solutionInformation, "cad-solution-information");

                var geometry = _nodes["Geometry"];
                SelectThroughRealTreeEvents(geometry, "cad-geometry");
                var geometryRows = _details.Rows.Cast<DataGridViewRow>()
                    .ToDictionary(row => row.Cells[0].Value?.ToString() ?? string.Empty,
                        row => row.Cells.Count > 1 ? row.Cells[1].Value?.ToString() ?? string.Empty : string.Empty,
                        StringComparer.OrdinalIgnoreCase);
                if (!geometryRows.TryGetValue("Source", out var source) || string.IsNullOrWhiteSpace(source) || source.Contains("No geometry", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("GUI smoke: Geometry Details did not show the imported STEP source.");
                if (!geometryRows.TryGetValue("Bodies", out var bodies) || bodies == "0")
                    throw new InvalidOperationException("GUI smoke: Geometry Details reported zero bodies after STEP import.");
                SmokeTrace("geometry-properties-pass");

                var importedBody = geometry.Nodes.Cast<TreeNode>().First();
                SelectThroughRealTreeEvents(importedBody, "cad-body-before-delete");
                SmokeTrace("delete-begin");
                DeleteSelected();
                Application.DoEvents();
                SmokeTrace("delete-doevents-pass");
                if (!string.IsNullOrWhiteSpace(_geometryPath))
                    throw new InvalidOperationException("GUI smoke: deleting imported Geometry left _geometryPath active.");
                if (_cadCanvas is { Visible: true })
                    throw new InvalidOperationException("GUI smoke: deleting imported Geometry left the CAD canvas visible.");
                if (_nodes["Geometry"].Nodes.Count != 0)
                    throw new InvalidOperationException("GUI smoke: deleting imported Geometry left a body in the tree.");
                if (!_viewport.Visible)
                    throw new InvalidOperationException("GUI smoke: legacy viewport was not restored after deleting CAD.");

                Log("PASS GUI RealTreeEventsWithCad: Details followed Fixed Support, Connections, Solution Information and Geometry with STEP visible.");
                Log("PASS GUI CadImportNavigateDelete: deleting the imported body released the CAD view and model state.");
                SmokeTrace("cad-sequence-pass");
            }

            Log("PASS GUI DetailsFirstSelection: Details follows TreeView through real BeforeSelect/AfterSelect events without polling.");
            SmokeTrace("complete");
            success = true;
        }
        catch (Exception exception)
        {
            SmokeTrace($"EXCEPTION:{exception.GetType().Name}:{exception.Message}");
            throw;
        }
        finally
        {
            _uiSmokeRunning = false;
            if (success && !IsDisposed) Close();
        }
    }
}
