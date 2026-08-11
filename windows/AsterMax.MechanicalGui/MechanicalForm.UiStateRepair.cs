namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private bool _simpleSelectionControllerInstalled;
    private bool _selectionActivationInProgress;

    /// <summary>
    /// Deterministic WinForms selection controller.
    ///
    /// TreeView.SelectedNode is the single selection source of truth. We deliberately do
    /// not use timers, Application.Idle, BeginInvoke or splitter repair here. Before a
    /// TreeView selection changes we commit any active Details edit and render the target
    /// object synchronously. A left-click confirmation performs the same idempotent render
    /// once more after the native TreeView has completed its own selection bookkeeping.
    /// </summary>
    internal void InstallSimpleSelectionController()
    {
        if (_simpleSelectionControllerInstalled) return;
        _simpleSelectionControllerInstalled = true;

        ConfigureDetailsMinimumWidths();

        // BEFORE the normal AfterSelect subscriber in WireEvents can run, make sure the
        // DataGridView is not holding an edit transaction that could abort Rows.Clear().
        _outline.BeforeSelect += (_, e) => ActivateTreeNode(e.Node, "before-select");

        // Explicit left-click fallback. This is intentionally synchronous and makes a
        // mouse click authoritative even if Windows sends an unusual TreeView selection
        // notification sequence on a particular machine/DPI configuration.
        _outline.NodeMouseClick += (_, e) =>
        {
            if (e.Button != MouseButtons.Left) return;
            ActivateTreeNode(e.Node, "mouse-click");
        };

        // Shown runs only after native handles exist. No BeginInvoke is required.
        Shown += (_, _) =>
        {
            if (IsDisposed || !IsHandleCreated) return;
            ActivateTreeNode(_outline.SelectedNode, "shown");
            RunStartupSelectionRegressionIfRequested();
        };
    }

    private void ConfigureDetailsMinimumWidths()
    {
        if (_details.Columns.Count < 2) return;
        _details.Columns[0].MinimumWidth = 110;
        _details.Columns[1].MinimumWidth = 140;
        _details.Columns[0].FillWeight = 43;
        _details.Columns[1].FillWeight = 57;
    }

    /// <summary>
    /// Render every UI surface from one TreeNode. No deferred work is scheduled.
    /// </summary>
    private void ActivateTreeNode(TreeNode? node, string source)
    {
        if (_selectionActivationInProgress || IsDisposed || node?.Tag is not ModelObject model) return;

        try
        {
            _selectionActivationInProgress = true;

            // Never abandon a selection change just because the property table was in edit
            // mode. Commit the cell first, then allow UpdateDetails to rebuild the rows.
            if (_details.IsCurrentCellInEditMode)
            {
                try { _details.EndEdit(); } catch { _details.CancelEdit(); }
            }
            try { _details.CurrentCell = null; } catch { }

            OnObjectSelected(node);
            HighlightScopeForSelectedTreeObject();
            RefreshProductionSelectionFeedback();

            // Validate the most important invariant immediately. If a legacy code path
            // changed the grid behind us, rebuild it once synchronously from the same node.
            var renderedName = ReadRenderedDetailsName();
            if (!string.Equals(renderedName, model.Name, StringComparison.Ordinal))
            {
                UpdateDetails(node);
                renderedName = ReadRenderedDetailsName();
            }

            if (!string.Equals(renderedName, model.Name, StringComparison.Ordinal))
                throw new InvalidOperationException(
                    $"Details selection invariant failed: tree='{model.Name}', details='{renderedName ?? "<none>"}', source={source}.");

            _outline.Invalidate();
            _details.Invalidate();
            _viewport.Invalidate();
            Log($"UI SELECT [{source}]: {model.Name}");
        }
        finally
        {
            _selectionActivationInProgress = false;
        }
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

    /// <summary>
    /// CI regression for the exact field failures reported from the real Windows build.
    /// It walks multiple nodes, including Solution Information, and requires Details/status
    /// to follow the selected node every time. The test also verifies that the property
    /// panel can recover from an active cell edit without deferred Invoke/BeginInvoke work.
    /// </summary>
    private void RunStartupSelectionRegressionIfRequested()
    {
        var args = Environment.GetCommandLineArgs();
        if (!args.Any(arg => string.Equals(arg, "--startup-smoke", StringComparison.OrdinalIgnoreCase))) return;

        RequireUi(IsHandleCreated, "GUI smoke: selection regression ran before the Form handle existed.");
        ValidateStableLayout("initial");
        var before = CaptureSplitterState();

        var analysis = FirstAnalysis() ?? throw new InvalidOperationException("GUI smoke: Static Structural analysis is missing.");
        SelectAndActivateForSmoke(analysis);

        AddLoad("Force");
        Application.DoEvents();
        var loadNode = _outline.SelectedNode ?? throw new InvalidOperationException("GUI smoke: Force selection is missing.");
        if (loadNode.Tag is not ModelObject { Kind: ObjectKind.Load } load)
            throw new InvalidOperationException("GUI smoke: inserted Force did not become the selected tree object.");
        ActivateTreeNode(loadNode, "smoke-force");
        AssertSelectedObjectOwnsDetails(loadNode, load, requireLoadControls: true);

        AddSupport("Fixed Support");
        Application.DoEvents();
        var supportNode = _outline.SelectedNode ?? throw new InvalidOperationException("GUI smoke: Fixed Support selection is missing.");
        if (supportNode.Tag is not ModelObject { Kind: ObjectKind.Support } support)
            throw new InvalidOperationException("GUI smoke: inserted Fixed Support did not become the selected tree object.");
        ActivateTreeNode(supportNode, "smoke-support");
        AssertSelectedObjectOwnsDetails(supportNode, support, requireLoadControls: false);

        // Exact node visible in the latest field screenshot.
        var solutionInformation = AllNodes().FirstOrDefault(node =>
            node.Tag is ModelObject { Kind: ObjectKind.SolutionInformation })
            ?? throw new InvalidOperationException("GUI smoke: Solution Information node is missing.");
        SelectAndActivateForSmoke(solutionInformation);
        AssertDetailsName(solutionInformation);

        var totalDeformation = AllNodes().FirstOrDefault(node =>
            node.Tag is ModelObject { Kind: ObjectKind.Result } &&
            node.Text.Equals("Total Deformation", StringComparison.OrdinalIgnoreCase));
        if (totalDeformation is not null)
        {
            SelectAndActivateForSmoke(totalDeformation);
            AssertDetailsName(totalDeformation);
        }

        var geometry = _nodes["Geometry"];
        SelectAndActivateForSmoke(geometry);
        AssertDetailsName(geometry);

        // Selecting the same node again must still refresh Details. This covers STEP import
        // committing new geometry while Geometry was already selected before the import.
        if (geometry.Tag is ModelObject geometryModel)
        {
            var originalName = geometryModel.Name;
            ActivateTreeNode(geometry, "smoke-same-node-refresh");
            RequireUi(string.Equals(ReadRenderedDetailsName(), originalName, StringComparison.Ordinal),
                "GUI smoke: re-activating the same selected node did not refresh Details.");
        }

        for (var i = 0; i < 4; i++) Application.DoEvents();
        var after = CaptureSplitterState();
        RequireUi(before.ContentDistance == after.ContentDistance,
            $"GUI smoke: Outline splitter moved autonomously ({before.ContentDistance} -> {after.ContentDistance}).");
        RequireUi(before.RightDistance == after.RightDistance,
            $"GUI smoke: Details splitter moved autonomously ({before.RightDistance} -> {after.RightDistance}).");
        RequireUi(before.CenterDistance == after.CenterDistance,
            $"GUI smoke: Graphics splitter moved autonomously ({before.CenterDistance} -> {after.CenterDistance}).");

        Log("PASS GUI DeterministicSelectionController: Geometry, Force, Fixed Support, Solution Information and Result followed the selected tree node.");
    }

    private void SelectAndActivateForSmoke(TreeNode node)
    {
        _outline.SelectedNode = node;
        node.EnsureVisible();
        ActivateTreeNode(node, "smoke-select");
        Application.DoEvents();
    }

    private void AssertDetailsName(TreeNode node)
    {
        if (node.Tag is not ModelObject model)
            throw new InvalidOperationException("GUI smoke: selected node has no model object.");
        RequireUi(string.Equals(ReadRenderedDetailsName(), model.Name, StringComparison.Ordinal),
            $"GUI smoke: Details stayed on '{ReadRenderedDetailsName()}' while tree selection is '{model.Name}'.");
        RequireUi(_statusSelection.Text.Contains(model.Name, StringComparison.OrdinalIgnoreCase),
            $"GUI smoke: status stayed stale: '{_statusSelection.Text}' while selected={model.Name}.");
    }

    private void AssertSelectedObjectOwnsDetails(TreeNode node, ModelObject model, bool requireLoadControls)
    {
        ActivateTreeNode(node, "smoke-assert");
        var rows = _details.Rows.Cast<DataGridViewRow>()
            .ToDictionary(
                row => row.Cells[0].Value?.ToString() ?? string.Empty,
                row => row.Cells.Count > 1 ? row.Cells[1].Value?.ToString() ?? string.Empty : string.Empty,
                StringComparer.OrdinalIgnoreCase);

        RequireUi(rows.TryGetValue("Name", out var renderedName) && string.Equals(renderedName, model.Name, StringComparison.Ordinal),
            $"GUI smoke: Details belongs to '{renderedName}' while tree selection is '{model.Name}'.");
        RequireUi(rows.ContainsKey("Geometry"), $"GUI smoke: Geometry scoping control disappeared for {model.Name}.");
        RequireUi(rows.ContainsKey("Scoping Method"), $"GUI smoke: Scoping Method disappeared for {model.Name}.");
        if (requireLoadControls)
        {
            RequireUi(rows.ContainsKey("Magnitude"), "GUI smoke: Magnitude control disappeared.");
            RequireUi(rows.ContainsKey("Direction"), "GUI smoke: Direction control disappeared.");
            RequireUi(rows.ContainsKey("Define By"), "GUI smoke: Define By control disappeared.");
        }
        RequireUi(_statusSelection.Text.Contains(model.Name, StringComparison.OrdinalIgnoreCase),
            $"GUI smoke: status stayed stale: '{_statusSelection.Text}' while selected={model.Name}.");
    }

    private void ValidateStableLayout(string stage)
    {
        var root = _ribbon.Parent as TableLayoutPanel
                   ?? throw new InvalidOperationException($"GUI smoke ({stage}): root TableLayoutPanel is missing.");
        var content = FindOutlineSplitter()
                      ?? throw new InvalidOperationException($"GUI smoke ({stage}): Outline splitter is missing.");
        var right = FindDetailsSplitter()
                    ?? throw new InvalidOperationException($"GUI smoke ({stage}): Details splitter is missing.");
        var center = FindCenterSplitter()
                     ?? throw new InvalidOperationException($"GUI smoke ({stage}): Graphics splitter is missing.");

        RequireUi(Math.Abs(root.ClientSize.Width - ClientSize.Width) <= 4,
            $"GUI smoke ({stage}): root width {root.ClientSize.Width}px does not fill form width {ClientSize.Width}px.");
        RequireUi(content.Panel1.ClientSize.Width >= 190,
            $"GUI smoke ({stage}): Outline collapsed to {content.Panel1.ClientSize.Width}px.");
        RequireUi(right.Panel2.ClientSize.Width >= 230,
            $"GUI smoke ({stage}): Details host collapsed to {right.Panel2.ClientSize.Width}px.");
        RequireUi(center.Panel1.ClientSize.Height >= 270,
            $"GUI smoke ({stage}): Graphics viewport collapsed to {center.Panel1.ClientSize.Height}px high.");
        RequireUi(center.Panel2.ClientSize.Height >= 130,
            $"GUI smoke ({stage}): lower tabs collapsed to {center.Panel2.ClientSize.Height}px high.");
        RequireUi(_details.ClientSize.Width >= 220,
            $"GUI smoke ({stage}): Details grid collapsed to {_details.ClientSize.Width}px.");
        RequireUi(_details.Columns.Count >= 2 && _details.Columns[1].Visible && _details.Columns[1].Width >= 110,
            $"GUI smoke ({stage}): Value column is hidden/collapsed (width={(_details.Columns.Count >= 2 ? _details.Columns[1].Width : 0)}px).");
    }

    private (int ContentDistance, int RightDistance, int CenterDistance) CaptureSplitterState()
    {
        var content = FindOutlineSplitter() ?? throw new InvalidOperationException("GUI smoke: Outline splitter is missing.");
        var right = FindDetailsSplitter() ?? throw new InvalidOperationException("GUI smoke: Details splitter is missing.");
        var center = FindCenterSplitter() ?? throw new InvalidOperationException("GUI smoke: Graphics splitter is missing.");
        return (content.SplitterDistance, right.SplitterDistance, center.SplitterDistance);
    }

    private SplitContainer? FindOutlineSplitter() =>
        (_outline.Parent?.Parent as SplitterPanel)?.Parent as SplitContainer;

    private SplitContainer? FindDetailsSplitter() =>
        (_details.Parent?.Parent as SplitterPanel)?.Parent as SplitContainer;

    private SplitContainer? FindCenterSplitter() =>
        (_lowerTabs.Parent as SplitterPanel)?.Parent as SplitContainer;

    private static void RequireUi(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
