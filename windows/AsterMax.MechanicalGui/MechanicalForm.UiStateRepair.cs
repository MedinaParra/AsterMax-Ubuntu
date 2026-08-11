namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private bool _uiStateRepairInstalled;
    private bool _selectionSyncInProgress;

    /// <summary>
    /// Installs only handle-safe, event-driven UI guards.
    /// No timer, no Application.Idle hook and no BeginInvoke from the constructor path.
    /// </summary>
    internal void InstallUiStateRepair()
    {
        if (_uiStateRepairInstalled) return;
        _uiStateRepairInstalled = true;

        ConfigureDetailsMinimumWidths();

        // WireEvents performs the normal synchronous selection update. This second pass
        // is intentionally synchronous too, but only after the Form handle exists. It
        // closes the field failure where a programmatic insert changed the blue tree row
        // while Details/status still described Geometry.
        _outline.AfterSelect += (_, e) =>
        {
            if (IsDisposed || !IsHandleCreated || e.Node is null) return;
            SynchronizeSelectionSurfaces(e.Node);
        };

        // Shown guarantees that the native window handle and child controls exist.
        // Do not call BeginInvoke here: the previous constructor-time subscription made
        // SelectNode("Project") queue work before a handle existed and caused the exact
        // "No se puede llamar a Invoke o BeginInvoke..." startup exception.
        Shown += (_, _) =>
        {
            if (IsDisposed || !IsHandleCreated) return;
            if (_outline.SelectedNode is { } selectedNode)
                SynchronizeSelectionSurfaces(selectedNode);
            RunStartupLoadDetailsRegressionIfRequested();
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

    private void SynchronizeSelectionSurfaces(TreeNode node)
    {
        if (_selectionSyncInProgress || _busy || _details.IsCurrentCellInEditMode ||
            node.Tag is not ModelObject selected) return;

        try
        {
            _selectionSyncInProgress = true;
            OnObjectSelected(node);
            HighlightScopeForSelectedTreeObject();
            RefreshProductionSelectionFeedback();

            // Explicit invalidation only. Never reflow splitters from selection code.
            _details.Invalidate();
            _outline.Invalidate();
            _viewport.Invalidate();
            Log($"UI SELECTION SYNC: '{selected.Name}'.");
        }
        finally
        {
            _selectionSyncInProgress = false;
        }
    }

    /// <summary>
    /// Windows startup regression for the three field failures:
    /// - no Invoke/BeginInvoke before a native handle exists,
    /// - Force/Support selection must own Details/status,
    /// - splitters must remain stable while messages are pumped.
    /// </summary>
    private void RunStartupLoadDetailsRegressionIfRequested()
    {
        var args = Environment.GetCommandLineArgs();
        if (!args.Any(arg => string.Equals(arg, "--startup-smoke", StringComparison.OrdinalIgnoreCase))) return;

        RequireUi(IsHandleCreated, "GUI smoke: startup regression ran before the Form handle existed.");
        ValidateStableLayout("initial");
        var before = CaptureSplitterState();

        var analysis = FirstAnalysis() ?? throw new InvalidOperationException("GUI smoke: Static Structural analysis is missing.");
        _outline.SelectedNode = analysis;
        SynchronizeSelectionSurfaces(analysis);
        AddLoad("Force");
        Application.DoEvents();

        if (_outline.SelectedNode?.Tag is not ModelObject { Kind: ObjectKind.Load } load || _outline.SelectedNode is not { } loadNode)
            throw new InvalidOperationException("GUI smoke: inserted Force did not become the selected tree object.");

        // Reproduce the user's stale panel deterministically and recover through the same
        // synchronous selected-node path used during normal operation.
        UpdateDetails(_nodes["Geometry"]);
        _statusSelection.Text = "Selected: Geometry";
        _contextTitle.Text = "Geometry\nGeometry";
        SynchronizeSelectionSurfaces(loadNode);
        Application.DoEvents();

        AssertSelectedObjectOwnsDetails(loadNode, load, requireLoadControls: true);
        ValidateStableLayout("after Force selection");

        // Also validate a support, because the second field screenshot showed Fixed
        // Support highlighted while Details/status still reported Geometry.
        AddSupport("Fixed Support");
        Application.DoEvents();
        if (_outline.SelectedNode?.Tag is not ModelObject { Kind: ObjectKind.Support } support || _outline.SelectedNode is not { } supportNode)
            throw new InvalidOperationException("GUI smoke: inserted Fixed Support did not become the selected tree object.");
        AssertSelectedObjectOwnsDetails(supportNode, support, requireLoadControls: false);

        for (var i = 0; i < 8; i++) Application.DoEvents();
        var after = CaptureSplitterState();
        RequireUi(before.ContentDistance == after.ContentDistance,
            $"GUI smoke: Outline splitter moved autonomously ({before.ContentDistance} -> {after.ContentDistance}).");
        RequireUi(before.RightDistance == after.RightDistance,
            $"GUI smoke: Details splitter moved autonomously ({before.RightDistance} -> {after.RightDistance}).");
        RequireUi(before.CenterDistance == after.CenterDistance,
            $"GUI smoke: Graphics splitter moved autonomously ({before.CenterDistance} -> {after.CenterDistance}).");

        Log($"PASS GUI HandleSafeStableLayoutAndSelection: Details={_details.ClientSize.Width}px, Value={_details.Columns[1].Width}px, selected={support.Name}.");
    }

    private void AssertSelectedObjectOwnsDetails(TreeNode node, ModelObject model, bool requireLoadControls)
    {
        SynchronizeSelectionSurfaces(node);
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
            $"GUI smoke ({stage}): Value column is hidden/collapsed (width={(_details.Columns.Count >= 2 ? _details.Columns[1].Width : 0)}px)." );
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
