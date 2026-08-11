namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private bool _stableSelectionInstalled;
    private bool _stableSelectionBusy;

    /// <summary>
    /// One selection event, one selected node, one synchronous Details render.
    /// No BeforeSelect, mouse fallback, timer, Idle callback or deferred BeginInvoke.
    /// </summary>
    internal void InstallStableSelectionController()
    {
        if (_stableSelectionInstalled) return;
        _stableSelectionInstalled = true;
        ConfigureDetailsMinimumWidths();

        _outline.AfterSelect += (_, e) => ActivateStableTreeNode(e.Node, "after-select");
        Shown += async (_, _) =>
        {
            if (IsDisposed || !IsHandleCreated) return;
            ActivateStableTreeNode(_outline.SelectedNode, "shown");
            await RunStableSelectionSmokeIfRequestedAsync();
        };
    }

    private void ActivateStableTreeNode(TreeNode? node, string source)
    {
        if (_stableSelectionBusy || IsDisposed || node?.Tag is not ModelObject model) return;

        try
        {
            _stableSelectionBusy = true;
            if (_details.IsCurrentCellInEditMode)
            {
                try { _details.EndEdit(); } catch { _details.CancelEdit(); }
            }
            try { _details.CurrentCell = null; } catch { }

            ReconcileGeometryVisualState();
            OnObjectSelected(node);
            HighlightScopeForSelectedTreeObject();
            RefreshProductionSelectionFeedback();

            var renderedName = ReadRenderedDetailsName();
            if (!string.Equals(renderedName, model.Name, StringComparison.Ordinal))
            {
                UpdateDetails(node);
                renderedName = ReadRenderedDetailsName();
            }

            if (!string.Equals(renderedName, model.Name, StringComparison.Ordinal))
                throw new InvalidOperationException(
                    $"Details invariant failed: tree='{model.Name}', details='{renderedName ?? "<none>"}', source={source}.");

            _outline.Invalidate();
            _details.Invalidate();
        }
        finally
        {
            _stableSelectionBusy = false;
        }
    }

    /// <summary>
    /// Production extras without the former 120-ms UI polling loop. Chrome is attached
    /// only when the relevant state changes, so an imported CAD model cannot cause a
    /// permanent background reflow/repaint workload.
    /// </summary>
    internal void InitializeStableProductionInteractions()
    {
        if (_productionInteractionsInitialized) return;
        _productionInteractionsInitialized = true;

        InstallEmptyViewportCover();
        InstallScopeLegend();
        InstallNavigationControls();
        ConfigureDetailsSelectionExperience();
        KeyDown += HandleNavigationShortcut;

        Shown += (_, _) => RefreshProductionUiState();
        FormClosed += (_, _) => CloseOperationOverlay();
    }

    private void ReconcileGeometryVisualState()
    {
        // The generic legacy Delete action can remove either the imported Body or even the
        // Geometry root. Reconcile that tree state with the actual CAD/view state on the
        // very next selection event instead of leaving a ghost model visible.
        if (!_nodes.TryGetValue("Model", out var modelNode)) return;

        if (!_nodes.TryGetValue("Geometry", out var geometryNode) || geometryNode.TreeView != _outline)
        {
            _nodes.Remove("Geometry");
            geometryNode = MakeNode("Geometry", ObjectKind.Geometry, ObjectState.NeedsAttention, "Geometry");
            modelNode.Nodes.Insert(0, geometryNode);
        }

        // Remove stale dictionary entries for nodes that were physically deleted from the
        // TreeView. Core nodes still attached to the tree are preserved.
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

        if (_emptyViewportCover is not null)
        {
            _emptyViewportCover.Visible = true;
            _emptyViewportCover.BringToFront();
        }

        Log("GEOMETRY CLEARED: CAD mesh, preview, solver state and viewport were released together.");
    }

    private async Task RunStableSelectionSmokeIfRequestedAsync()
    {
        var args = Environment.GetCommandLineArgs();
        if (!args.Any(arg => string.Equals(arg, "--startup-smoke", StringComparison.OrdinalIgnoreCase))) return;

        var sequence = new[]
        {
            _nodes.GetValueOrDefault("Geometry"),
            FirstAnalysis(),
            AllNodes().FirstOrDefault(node => node.Tag is ModelObject { Kind: ObjectKind.SolutionInformation }),
            AllNodes().FirstOrDefault(node => node.Tag is ModelObject { Kind: ObjectKind.Result })
        }.Where(node => node is not null).Cast<TreeNode>().ToArray();

        foreach (var node in sequence)
        {
            _outline.SelectedNode = node;
            node.EnsureVisible();
            ActivateStableTreeNode(node, "stable-smoke-empty");
            if (node.Tag is not ModelObject model || !string.Equals(ReadRenderedDetailsName(), model.Name, StringComparison.Ordinal))
                throw new InvalidOperationException($"GUI smoke: Details did not follow {node.Text} before CAD import.");
        }

        // When Actions runs from the repository root, exercise the exact field scenario:
        // import the real cylinder, navigate away from Geometry, then delete the imported
        // body and require the CAD canvas/state to disappear with it.
        var cylinder = Path.Combine(
            Environment.CurrentDirectory,
            "windows",
            "AsterMax.MechanicalGui",
            "TestData",
            "CILINDRO-SIMPLE.stp");

        if (File.Exists(cylinder) && GmshCliMesher.FindExecutable() is not null)
        {
            await ImportCadStepAsync(cylinder);
            if (string.IsNullOrWhiteSpace(_geometryPath) || _nodes["Geometry"].Nodes.Count == 0)
                throw new InvalidOperationException("GUI smoke: real STEP import did not commit Geometry.");
            if (_cadCanvas is null || !_cadCanvas.Visible)
                throw new InvalidOperationException("GUI smoke: responsive CAD canvas is not visible after STEP import.");

            var solutionInformation = AllNodes().First(node => node.Tag is ModelObject { Kind: ObjectKind.SolutionInformation });
            _outline.SelectedNode = solutionInformation;
            ActivateStableTreeNode(solutionInformation, "stable-smoke-after-cad");
            if (!string.Equals(ReadRenderedDetailsName(), "Solution Information", StringComparison.Ordinal))
                throw new InvalidOperationException("GUI smoke: Details froze on Geometry after STEP import.");

            var importedBody = _nodes["Geometry"].Nodes.Cast<TreeNode>().First();
            _outline.SelectedNode = importedBody;
            DeleteSelected();
            Application.DoEvents();

            if (!string.IsNullOrWhiteSpace(_geometryPath))
                throw new InvalidOperationException("GUI smoke: deleting imported Geometry left _geometryPath active.");
            if (_cadCanvas is { Visible: true })
                throw new InvalidOperationException("GUI smoke: deleting imported Geometry left the CAD canvas visible.");
            if (_nodes["Geometry"].Nodes.Count != 0)
                throw new InvalidOperationException("GUI smoke: deleting imported Geometry left a body in the tree.");

            Log("PASS GUI CadImportNavigateDelete: imported STEP did not freeze Details and deletion released the CAD view.");
        }

        Log("PASS GUI StableSingleAfterSelect: Details follows TreeView.SelectedNode with no polling.");
    }
}
