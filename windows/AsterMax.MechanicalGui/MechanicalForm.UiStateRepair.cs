using System.Runtime.CompilerServices;

namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private bool _uiStateRepairInstalled;
    private System.Windows.Forms.Timer? _uiStateRepairTimer;

    internal void InstallUiStateRepair()
    {
        if (_uiStateRepairInstalled) return;
        _uiStateRepairInstalled = true;

        EnsureRootUsesFullWidth();
        ConfigureDetailsMinimumWidths();

        void InitialRepair()
        {
            if (IsDisposed || !IsHandleCreated) return;
            BeginInvoke(() =>
            {
                RepairResponsiveDetailsLayout(force: true);
                RepairSelectionDetailsIfNeeded();
                RunStartupLoadDetailsRegressionIfRequested();
            });
        }

        if (Visible && IsHandleCreated)
            InitialRepair();
        else
            Shown += (_, _) => InitialRepair();

        SizeChanged += (_, _) =>
        {
            if (!IsHandleCreated || IsDisposed) return;
            BeginInvoke(() => RepairResponsiveDetailsLayout(force: false));
        };

        _uiStateRepairTimer = new System.Windows.Forms.Timer { Interval = 150 };
        _uiStateRepairTimer.Tick += (_, _) =>
        {
            RepairSelectionDetailsIfNeeded();
            RepairResponsiveDetailsLayout(force: false);
        };
        _uiStateRepairTimer.Start();

        FormClosed += (_, _) =>
        {
            if (_uiStateRepairTimer is null) return;
            _uiStateRepairTimer.Stop();
            _uiStateRepairTimer.Dispose();
            _uiStateRepairTimer = null;
        };
    }

    /// <summary>
    /// The safe-startup layout originally declared one TableLayoutPanel column without
    /// assigning it a percent style. On some DPI/window combinations WinForms retained
    /// the preferred width of the nested splitters and left unused space at the right,
    /// compressing Details until the Value column effectively disappeared.
    /// </summary>
    private void EnsureRootUsesFullWidth()
    {
        if (_ribbon.Parent is not TableLayoutPanel root || root.ColumnCount != 1) return;
        if (root.ColumnStyles.Count == 0)
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
        else
        {
            root.ColumnStyles[0].SizeType = SizeType.Percent;
            root.ColumnStyles[0].Width = 100F;
        }
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
    /// Keeps a usable Details width without continuously overriding a user's splitter
    /// preference. Reflow is forced once when the form is shown and later only if the
    /// panel has actually collapsed below a usable size.
    /// </summary>
    private void RepairResponsiveDetailsLayout(bool force)
    {
        EnsureRootUsesFullWidth();
        ConfigureDetailsMinimumWidths();

        var detailsHost = _details.Parent;
        var splitterPanel = detailsHost?.Parent as SplitterPanel;
        var splitter = splitterPanel?.Parent as SplitContainer;
        if (splitter is null || splitter.Orientation != Orientation.Vertical) return;

        var extent = splitter.ClientSize.Width;
        if (extent <= splitter.SplitterWidth + 240) return;

        // At normal desktop widths reserve about 25% for Details, clamped to a
        // practical Mechanical-style range. Smaller windows still retain >=240 px.
        var desiredDetailsWidth = extent >= 900
            ? Math.Clamp((int)Math.Round(extent * 0.25), 300, 380)
            : Math.Clamp((int)Math.Round(extent * 0.32), 240, 320);

        var currentlyCollapsed = _details.ClientSize.Width < 240 ||
                                 (_details.Columns.Count >= 2 && _details.Columns[1].Width < 110);
        if (!force && !currentlyCollapsed) return;

        var requested = extent - splitter.SplitterWidth - desiredDetailsWidth;
        SetSafeSplitter(splitter, requested);
        splitter.PerformLayout();
        _details.PerformLayout();
    }

    /// <summary>
    /// TreeView can visually move selection while a programmatic insertion path misses
    /// the normal AfterSelect refresh. The authoritative check is the selected node versus
    /// the Name currently rendered in Details. If they disagree, rebuild every dependent
    /// selection surface from the actual TreeView.SelectedNode.
    /// </summary>
    private void RepairSelectionDetailsIfNeeded()
    {
        if (_busy || _details.IsCurrentCellInEditMode || _outline.SelectedNode?.Tag is not ModelObject selected) return;

        string? renderedName = null;
        foreach (DataGridViewRow row in _details.Rows)
        {
            if (!string.Equals(row.Cells[0].Value?.ToString(), "Name", StringComparison.OrdinalIgnoreCase)) continue;
            renderedName = row.Cells[1].Value?.ToString();
            break;
        }

        var contextMatches = _contextTitle.Text.Contains(selected.Name, StringComparison.OrdinalIgnoreCase);
        if (string.Equals(renderedName, selected.Name, StringComparison.Ordinal) && contextMatches) return;

        var selectedNode = _outline.SelectedNode;
        OnObjectSelected(selectedNode);
        HighlightScopeForSelectedTreeObject();
        RefreshProductionSelectionFeedback();
        Log($"UI STATE REPAIR: synchronized Details with selected object '{selected.Name}'.");
    }

    /// <summary>
    /// The normal Windows startup smoke now contains the exact regression reported from
    /// the field: the tree points to Force while Details is deliberately left on Geometry.
    /// A release is rejected if synchronization or the Details value column cannot recover.
    /// </summary>
    private void RunStartupLoadDetailsRegressionIfRequested()
    {
        var args = Environment.GetCommandLineArgs();
        if (!args.Any(arg => string.Equals(arg, "--startup-smoke", StringComparison.OrdinalIgnoreCase))) return;

        var analysis = FirstAnalysis() ?? throw new InvalidOperationException("GUI load-details smoke: Static Structural analysis is missing.");
        _outline.SelectedNode = analysis;
        OnObjectSelected(analysis);
        AddLoad("Force");
        Application.DoEvents();

        if (_outline.SelectedNode?.Tag is not ModelObject { Kind: ObjectKind.Load } load)
            throw new InvalidOperationException("GUI load-details smoke: inserted Force did not become the selected tree object.");

        // Reproduce the user's screenshot deterministically: Force remains selected in
        // the Outline while the right side is stale on Geometry.
        UpdateDetails(_nodes["Geometry"]);
        _statusSelection.Text = "Selected: Geometry";
        _contextTitle.Text = "Geometry\nGeometry";
        RepairSelectionDetailsIfNeeded();
        RepairResponsiveDetailsLayout(force: true);
        Application.DoEvents();

        var properties = _details.Rows.Cast<DataGridViewRow>()
            .Select(row => row.Cells[0].Value?.ToString() ?? string.Empty)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        RequireUi(properties.Contains("Magnitude"), "GUI load-details smoke: Magnitude control disappeared.");
        RequireUi(properties.Contains("Direction"), "GUI load-details smoke: Direction control disappeared.");
        RequireUi(properties.Contains("Geometry"), "GUI load-details smoke: Geometry scope control disappeared.");
        RequireUi(properties.Contains("Define By"), "GUI load-details smoke: Define By control disappeared.");
        RequireUi(_details.ClientSize.Width >= 240,
            $"GUI load-details smoke: Details collapsed to {_details.ClientSize.Width}px.");
        RequireUi(_details.Columns.Count >= 2 && _details.Columns[1].Visible && _details.Columns[1].Width >= 110,
            $"GUI load-details smoke: Value column is hidden/collapsed (width={(_details.Columns.Count >= 2 ? _details.Columns[1].Width : 0)}px)." );
        RequireUi(_statusSelection.Text.Contains(load.Name, StringComparison.OrdinalIgnoreCase) ||
                  _statusSelection.Text.Contains("select a face", StringComparison.OrdinalIgnoreCase),
            $"GUI load-details smoke: selection feedback stayed stale: '{_statusSelection.Text}'.");

        Log($"PASS GUI LoadDetails_RemainsVisibleAfterStepWorkflow: Details={_details.ClientSize.Width}px, Value={_details.Columns[1].Width}px, selected={load.Name}.");
    }

    private static void RequireUi(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}

internal static class MechanicalUiStateRepairBootstrap
{
    private static bool _hooked;

    [ModuleInitializer]
    internal static void Initialize()
    {
        if (_hooked) return;
        _hooked = true;
        Application.Idle += HandleApplicationIdle;
    }

    private static void HandleApplicationIdle(object? sender, EventArgs e)
    {
        var form = Application.OpenForms.OfType<MechanicalForm>().FirstOrDefault();
        if (form is null || form.IsDisposed) return;
        form.InstallUiStateRepair();
        Application.Idle -= HandleApplicationIdle;
    }
}
