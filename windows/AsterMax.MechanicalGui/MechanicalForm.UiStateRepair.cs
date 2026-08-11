namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private bool _uiStateRepairInstalled;

    /// <summary>
    /// Installs only event-driven UI guards. This deliberately contains no recurring
    /// timer and never changes splitter distances while the user is working. The previous
    /// timer-based repair path could re-enter selection/layout during CAD painting and was
    /// responsible for fragmented panels and repeated viewport paint artifacts.
    /// </summary>
    internal void InstallUiStateRepair()
    {
        if (_uiStateRepairInstalled) return;
        _uiStateRepairInstalled = true;

        ConfigureDetailsMinimumWidths();

        // WireEvents already performs the normal selection update synchronously. This
        // second, deferred pass runs once per actual tree selection and guarantees that a
        // programmatic insert (Force/Support/etc.) cannot leave Details on the old object.
        _outline.AfterSelect += (_, e) =>
        {
            var selectedNode = e.Node;
            if (selectedNode is null || IsDisposed) return;
            BeginInvoke(() =>
            {
                if (IsDisposed || !ReferenceEquals(_outline.SelectedNode, selectedNode)) return;
                SynchronizeSelectionSurfaces(selectedNode);
            });
        };

        Shown += (_, _) => BeginInvoke(() =>
        {
            if (IsDisposed) return;
            if (_outline.SelectedNode is { } selectedNode)
                SynchronizeSelectionSurfaces(selectedNode);
            RunStartupLoadDetailsRegressionIfRequested();
        });
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
        if (_busy || _details.IsCurrentCellInEditMode || node.Tag is not ModelObject selected) return;

        OnObjectSelected(node);
        HighlightScopeForSelectedTreeObject();
        RefreshProductionSelectionFeedback();

        // OnObjectSelected may populate several grids and alter viewport flags. A single
        // invalidation is enough; no recurring reflow/repaint loop is allowed here.
        _details.Invalidate();
        _outline.Invalidate();
        _viewport.Invalidate();
        Log($"UI SELECTION SYNC: '{selected.Name}'.");
    }

    /// <summary>
    /// Structural regression for the exact two field failures reported by the user:
    /// 1) Force visually selected while Details remained on Geometry.
    /// 2) layout fragmentation / collapsed Details after the repair mechanism ran.
    /// The smoke test rejects a release if either state can be reproduced.
    /// </summary>
    private void RunStartupLoadDetailsRegressionIfRequested()
    {
        var args = Environment.GetCommandLineArgs();
        if (!args.Any(arg => string.Equals(arg, "--startup-smoke", StringComparison.OrdinalIgnoreCase))) return;

        ValidateStableLayout("initial");
        var before = CaptureSplitterState();

        var analysis = FirstAnalysis() ?? throw new InvalidOperationException("GUI smoke: Static Structural analysis is missing.");
        _outline.SelectedNode = analysis;
        SynchronizeSelectionSurfaces(analysis);
        AddLoad("Force");
        Application.DoEvents();

        if (_outline.SelectedNode?.Tag is not ModelObject { Kind: ObjectKind.Load } load)
            throw new InvalidOperationException("GUI smoke: inserted Force did not become the selected tree object.");

        var loadNode = _outline.SelectedNode;

        // Reproduce the stale panel from the field report, then repair only through the
        // selected-node synchronization path. No splitter or root-layout mutation occurs.
        UpdateDetails(_nodes["Geometry"]);
        _statusSelection.Text = "Selected: Geometry";
        _contextTitle.Text = "Geometry\nGeometry";
        SynchronizeSelectionSurfaces(loadNode);
        Application.DoEvents();

        var properties = _details.Rows.Cast<DataGridViewRow>()
            .Select(row => row.Cells[0].Value?.ToString() ?? string.Empty)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        RequireUi(properties.Contains("Magnitude"), "GUI smoke: Magnitude control disappeared.");
        RequireUi(properties.Contains("Direction"), "GUI smoke: Direction control disappeared.");
        RequireUi(properties.Contains("Geometry"), "GUI smoke: Geometry scope control disappeared.");
        RequireUi(properties.Contains("Define By"), "GUI smoke: Define By control disappeared.");
        RequireUi(_statusSelection.Text.Contains(load.Name, StringComparison.OrdinalIgnoreCase) ||
                  _statusSelection.Text.Contains("select a face", StringComparison.OrdinalIgnoreCase),
            $"GUI smoke: selection feedback stayed stale: '{_statusSelection.Text}'.");

        ValidateStableLayout("after Force selection");

        // Pump messages repeatedly and ensure the layout does not drift by itself. This
        // specifically guards against reintroducing timer-based splitter manipulation.
        for (var i = 0; i < 8; i++) Application.DoEvents();
        var after = CaptureSplitterState();
        RequireUi(before.ContentDistance == after.ContentDistance,
            $"GUI smoke: Outline splitter moved autonomously ({before.ContentDistance} -> {after.ContentDistance}).");
        RequireUi(before.RightDistance == after.RightDistance,
            $"GUI smoke: Details splitter moved autonomously ({before.RightDistance} -> {after.RightDistance}).");
        RequireUi(before.CenterDistance == after.CenterDistance,
            $"GUI smoke: Graphics splitter moved autonomously ({before.CenterDistance} -> {after.CenterDistance}).");

        Log($"PASS GUI StableLayoutAndLoadDetails: Details={_details.ClientSize.Width}px, Value={_details.Columns[1].Width}px, selected={load.Name}.");
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
