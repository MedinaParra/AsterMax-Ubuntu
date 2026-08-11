namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    /// <summary>
    /// Builds the shell without assigning splitter distances while the controls still
    /// have their WinForms design-time default size (roughly 150x100). Assigning values
    /// such as 900 at that point throws ArgumentOutOfRangeException and causes a silent
    /// startup exit in a WinExe application.
    /// </summary>
    private void BuildSafeLayout()
    {
        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 5,
            BackColor = Bg,
            Margin = Padding.Empty,
            Padding = Padding.Empty
        };
        // Define the only column as 100% at construction time. Never mutate the root
        // layout while the CAD canvas is painting.
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 27));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 126));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 25));
        Controls.Add(root);

        _menu.Dock = DockStyle.Fill;
        _menu.BackColor = Color.FromArgb(20, 22, 26);
        _menu.ForeColor = TextMain;
        _menu.Renderer = new DarkRenderer();
        root.Controls.Add(_menu, 0, 0);

        _ribbon.Dock = DockStyle.Fill;
        _ribbon.Padding = new Point(14, 5);
        root.Controls.Add(_ribbon, 0, 1);

        BuildWorkflowBar();
        root.Controls.Add(_workflow, 0, 2);

        var content = NewSplitter(Orientation.Vertical);
        root.Controls.Add(content, 0, 3);
        content.Panel1.Controls.Add(BuildOutlinePanel());

        var right = NewSplitter(Orientation.Vertical);
        content.Panel2.Controls.Add(right);

        var center = NewSplitter(Orientation.Horizontal);
        right.Panel1.Controls.Add(center);
        center.Panel1.Controls.Add(BuildGraphicsPanel());
        center.Panel2.Controls.Add(BuildLowerTabs());
        right.Panel2.Controls.Add(BuildDetailsPanel());

        _status.Dock = DockStyle.Fill;
        _status.BackColor = Color.FromArgb(20, 22, 25);
        _status.ForeColor = TextMuted;
        _status.SizingGrip = false;
        _statusMain.Spring = true;
        _statusMain.TextAlign = ContentAlignment.MiddleLeft;
        _statusSelection.BorderSides = ToolStripStatusLabelBorderSides.Left;
        _statusSolver.BorderSides = ToolStripStatusLabelBorderSides.Left;
        _status.Items.AddRange(new ToolStripItem[] { _statusMain, _statusSelection, _statusSolver });
        root.Controls.Add(_status, 0, 4);

        // Shown is already handle-safe and the final client size is available. There is no
        // reason to queue another BeginInvoke; keeping this synchronous removes another
        // asynchronous layout path from the application.
        Shown += (_, _) =>
        {
            content.Panel1MinSize = 200;
            content.Panel2MinSize = 540;
            right.Panel1MinSize = 420;
            right.Panel2MinSize = 240;
            center.Panel1MinSize = 280;
            center.Panel2MinSize = 140;

            SetSafeSplitter(content, Math.Min(285, Math.Max(220, content.ClientSize.Width / 4)));
            SetSafeSplitter(right, Math.Max(430, right.ClientSize.Width - 310));
            SetSafeSplitter(center, Math.Max(300, center.ClientSize.Height - 210));
            _statusMain.Text = "Ready — stable layout validated";
        };
    }

    private static SplitContainer NewSplitter(Orientation orientation) => new()
    {
        Dock = DockStyle.Fill,
        Orientation = orientation,
        SplitterWidth = 5,
        BackColor = Border,
        IsSplitterFixed = false
    };

    private static void SetSafeSplitter(SplitContainer splitter, int requested)
    {
        var extent = splitter.Orientation == Orientation.Vertical
            ? splitter.ClientSize.Width
            : splitter.ClientSize.Height;

        // Respect both Panel1MinSize and Panel2MinSize. This is deterministic and never
        // needs a timer to repair a live layout.
        var minimum = Math.Max(1, splitter.Panel1MinSize);
        var maximum = extent - splitter.SplitterWidth - Math.Max(1, splitter.Panel2MinSize);
        if (maximum < minimum) return;
        splitter.SplitterDistance = Math.Clamp(requested, minimum, maximum);
    }
}
