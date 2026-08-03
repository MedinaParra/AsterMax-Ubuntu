namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private readonly ImageList _treeIcons = new();
    private readonly DataGridView _workflowChecklist = new();
    private readonly System.Windows.Forms.Timer _presentationTimer = new() { Interval = 700 };
    private bool _darkTheme;
    private string _lastWorkflowSignature = string.Empty;

    private void InitializePresentation()
    {
        BuildWorkflowRibbon();
        BuildWorkflowChecklistTab();
        InstallAppearanceMenu();
        ConfigureTreeIcons();
        ApplyTheme(false);
        RefreshWorkflowChecklist(true);
        _presentationTimer.Tick += (_, _) => { AssignTreeIcons(); RefreshWorkflowChecklist(); };
        _presentationTimer.Start();
        FormClosed += (_, _) => _presentationTimer.Dispose();
    }

    private void BuildWorkflowRibbon()
    {
        var page = RibbonPage("Workflow",
            Group("Guided Workflow", RButton("Next Required Step", () => _ = RunNextWorkflowStepAsync(), true), RButton("Validate Model", ShowWorkflowChecklist)),
            Group("Preprocessing", RButton("Import Geometry", ImportGeometry), RButton("Assign Material", AssignMaterial), RButton("Generate Mesh", GenerateMesh)),
            Group("Environment", RButton("Fixed Support", () => AddSupport("Fixed Support")), RButton("Force", () => AddLoad("Force")), RButton("Analysis Settings", () => SelectNode("Analysis Settings"))),
            Group("Solution", RButton("Equivalent Stress", () => AddResult("Equivalent Stress")), RButton("Solve", () => _ = SolveAsync(), true), RButton("Evaluate All", EvaluateResults)));
        _ribbon.TabPages.Insert(0, page);
        _ribbon.SelectedTab = page;
    }

    private void BuildWorkflowChecklistTab()
    {
        var tab = new TabPage("Workflow Checklist") { BackColor = Field, ForeColor = TextMain, Padding = new Padding(2) };
        ConfigureGrid(_workflowChecklist, true);
        _workflowChecklist.ReadOnly = true;
        _workflowChecklist.SelectionMode = DataGridViewSelectionMode.FullRowSelect;
        _workflowChecklist.Columns.Add(new DataGridViewTextBoxColumn { Name = "Stage", FillWeight = 22 });
        _workflowChecklist.Columns.Add(new DataGridViewTextBoxColumn { Name = "Object", FillWeight = 30 });
        _workflowChecklist.Columns.Add(new DataGridViewTextBoxColumn { Name = "Status", FillWeight = 18 });
        _workflowChecklist.Columns.Add(new DataGridViewTextBoxColumn { Name = "NextAction", HeaderText = "Next action", FillWeight = 30 });
        _workflowChecklist.CellDoubleClick += (_, e) => ExecuteChecklistRow(e.RowIndex);
        tab.Controls.Add(_workflowChecklist);
        _lowerTabs.TabPages.Insert(1, tab);
    }

    private void InstallAppearanceMenu()
    {
        var view = _menu.Items.OfType<ToolStripMenuItem>().FirstOrDefault(item => item.Text == "View");
        if (view is null) return;
        view.DropDownItems.Add(new ToolStripSeparator());
        var appearance = new ToolStripMenuItem("Appearance");
        var light = new ToolStripMenuItem("Light CAD theme") { Checked = true, CheckOnClick = true };
        var dark = new ToolStripMenuItem("Dark theme") { CheckOnClick = true };
        light.Click += (_, _) => { light.Checked = true; dark.Checked = false; ApplyTheme(false); };
        dark.Click += (_, _) => { dark.Checked = true; light.Checked = false; ApplyTheme(true); };
        appearance.DropDownItems.AddRange(new ToolStripItem[] { light, dark });
        view.DropDownItems.Add(appearance);
        view.DropDownItems.Add(new ToolStripMenuItem("Workflow Checklist", null, (_, _) => ShowWorkflowChecklist()));
        view.DropDownItems.Add(new ToolStripMenuItem("Reset Panel Layout", null, (_, _) => ApplyInitialSplitterLayout()));
    }

    private void ConfigureTreeIcons()
    {
        _treeIcons.ColorDepth = ColorDepth.Depth32Bit;
        _treeIcons.ImageSize = new Size(18, 18);
        _treeIcons.TransparentColor = Color.Transparent;
        _outline.ImageList = _treeIcons;
        RebuildTreeIcons();
    }

    private void RebuildTreeIcons()
    {
        _treeIcons.Images.Clear();
        var palette = CurrentPalette;
        foreach (var icon in new[] { "project", "geometry", "material", "settings", "contact", "selection", "mesh", "mesh-control", "analysis", "support", "load", "solution", "result", "probe", "chart", "warning", "check" })
            _treeIcons.Images.Add(icon, SvgIconRenderer.Render(icon, 18, palette.Text, palette.Accent));
        AssignTreeIcons();
    }

    private void AssignTreeIcons()
    {
        foreach (var node in AllNodes())
        {
            if (node.Tag is not ModelObject model) continue;
            var key = model.Kind switch
            {
                ObjectKind.Project or ObjectKind.Model => "project",
                ObjectKind.Geometry or ObjectKind.Body => "geometry",
                ObjectKind.Materials or ObjectKind.Material => "material",
                ObjectKind.CoordinateSystems or ObjectKind.CoordinateSystem or ObjectKind.AnalysisSettings => "settings",
                ObjectKind.Connections or ObjectKind.Contact => "contact",
                ObjectKind.NamedSelections or ObjectKind.NamedSelection => "selection",
                ObjectKind.Mesh => "mesh",
                ObjectKind.MeshControl => "mesh-control",
                ObjectKind.Analysis => "analysis",
                ObjectKind.Support => "support",
                ObjectKind.Load => "load",
                ObjectKind.Solution or ObjectKind.SolutionInformation => "solution",
                ObjectKind.Result => "result",
                ObjectKind.Probe => "probe",
                ObjectKind.Chart => "chart",
                _ => "project"
            };
            node.ImageKey = node.SelectedImageKey = key;
        }
    }

    private void ApplyCommandIcons()
    {
        var palette = CurrentPalette;
        ApplyButtonIcons(this, palette);
        ApplyToolStripIcons(_menu.Items, palette, 16);
        ApplyToolStripIcons(_graphicsTools.Items, palette, 16);
        RebuildTreeIcons();
    }

    private static void ApplyButtonIcons(Control parent, ThemePalette palette)
    {
        foreach (Control control in parent.Controls)
        {
            if (control is Button button && ResolveCommandIcon(button.Text) is { } icon)
            {
                button.Image?.Dispose();
                button.Image = SvgIconRenderer.Render(icon, button.Height >= 50 ? 25 : 18, palette.Text, palette.Accent);
                button.TextImageRelation = button.Height >= 50 ? TextImageRelation.ImageAboveText : TextImageRelation.ImageBeforeText;
                button.ImageAlign = ContentAlignment.MiddleCenter;
                button.Padding = button.Height >= 50 ? new Padding(2, 3, 2, 1) : new Padding(4, 0, 4, 0);
            }
            if (control.HasChildren) ApplyButtonIcons(control, palette);
        }
    }

    private static void ApplyToolStripIcons(ToolStripItemCollection items, ThemePalette palette, int size)
    {
        foreach (ToolStripItem item in items)
        {
            if (ResolveCommandIcon(item.Text) is { } icon)
            {
                item.Image?.Dispose();
                item.Image = SvgIconRenderer.Render(icon, size, palette.Text, palette.Accent);
                item.DisplayStyle = ToolStripItemDisplayStyle.ImageAndText;
            }
            if (item is ToolStripMenuItem menu) ApplyToolStripIcons(menu.DropDownItems, palette, size);
        }
    }

    private static string? ResolveCommandIcon(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        var text = value.Replace("&", string.Empty).Trim().ToLowerInvariant();
        if (text.Contains("new")) return "new";
        if (text.Contains("open")) return "open";
        if (text.Contains("save")) return "save";
        if (text.Contains("import")) return "import";
        if (text.Contains("material")) return "material";
        if (text.Contains("selection")) return "selection";
        if (text.Contains("mesh") || text is "generate" or "clear") return text.Contains("control") || text.Contains("sizing") || text.Contains("method") || text.Contains("inflation") ? "mesh-control" : "mesh";
        if (text.Contains("solve") || text.Contains("next required")) return "solve";
        if (text.Contains("support") || text.Contains("displacement") || text.Contains("cylindrical")) return "support";
        if (text.Contains("force") || text.Contains("pressure") || text.Contains("moment") || text.Contains("gravity") || text.Contains("load")) return "load";
        if (text.Contains("contact") || text.Contains("joint") || text.Contains("spring") || text.Contains("beam")) return "contact";
        if (text.Contains("modal")) return "modal";
        if (text.Contains("thermal")) return "thermal";
        if (text.Contains("static") || text.Contains("analysis")) return "analysis";
        if (text.Contains("result") || text.Contains("stress") || text.Contains("strain") || text.Contains("deformation") || text.Contains("evaluate")) return "result";
        if (text.Contains("probe") || text.Contains("reaction")) return "probe";
        if (text.Contains("chart") || text.Contains("graph")) return "chart";
        if (text.Contains("setting") || text.Contains("coordinate") || text.Contains("parameter") || text.Contains("appearance")) return "settings";
        if (text.Contains("export") || text.Contains("code_aster") || text.Contains(".comm") || text.Contains(".export")) return "export";
        if (text.Contains("validate") || text.Contains("checklist")) return "check";
        return null;
    }

    private ThemePalette CurrentPalette => _darkTheme ? ThemePalette.Dark : ThemePalette.Light;

    private void ApplyTheme(bool dark)
    {
        _darkTheme = dark;
        var palette = CurrentPalette;
        SuspendLayout();
        ApplyThemeRecursive(this, palette);
        _menu.Renderer = new ThemeRenderer(palette);
        _graphicsTools.Renderer = new ThemeRenderer(palette);
        _viewport.SetDarkTheme(dark);
        SvgIconRenderer.ClearCache();
        ApplyCommandIcons();
        ResumeLayout(true);
        _viewport.Invalidate();
        Invalidate(true);
        RefreshWorkflowChecklist(true);
        _statusMain.Text = dark ? "Dark theme enabled" : "Light CAD theme enabled";
    }

    private static void ApplyThemeRecursive(Control control, ThemePalette palette)
    {
        switch (control)
        {
            case MechanicalViewport: break;
            case Form: control.BackColor = palette.Background; control.ForeColor = palette.Text; break;
            case SplitContainer split: split.BackColor = palette.Border; split.Panel1.BackColor = palette.Panel; split.Panel2.BackColor = palette.Panel; break;
            case MenuStrip menu: menu.BackColor = palette.Chrome; menu.ForeColor = palette.Text; break;
            case StatusStrip status: status.BackColor = palette.Chrome; status.ForeColor = palette.Muted; break;
            case ToolStrip strip: strip.BackColor = palette.SecondaryPanel; strip.ForeColor = palette.Text; break;
            case TabPage: control.BackColor = palette.Panel; control.ForeColor = palette.Text; break;
            case TreeView tree: tree.BackColor = palette.Panel; tree.ForeColor = palette.Text; tree.LineColor = palette.Border; break;
            case DataGridView grid:
                grid.BackgroundColor = palette.Field; grid.GridColor = palette.Border;
                grid.DefaultCellStyle.BackColor = palette.Field; grid.DefaultCellStyle.ForeColor = palette.Text;
                grid.DefaultCellStyle.SelectionBackColor = palette.Selection; grid.DefaultCellStyle.SelectionForeColor = Color.Black;
                grid.ColumnHeadersDefaultCellStyle.BackColor = palette.SecondaryPanel; grid.ColumnHeadersDefaultCellStyle.ForeColor = palette.Text;
                break;
            case TextBoxBase textBox: textBox.BackColor = palette.Field; textBox.ForeColor = palette.Text; break;
            case Button button:
                var primary = button.Text.Contains("Solve", StringComparison.OrdinalIgnoreCase) || button.Text.Contains("Next Required", StringComparison.OrdinalIgnoreCase) || button.Text.Contains("Evaluate All", StringComparison.OrdinalIgnoreCase);
                button.BackColor = primary ? palette.Accent : palette.Button; button.ForeColor = primary ? Color.White : palette.Text;
                button.FlatAppearance.BorderColor = primary ? palette.AccentBorder : palette.Border;
                break;
            case Label label: label.ForeColor = label.Font.Bold ? palette.Text : palette.Muted; break;
            case FlowLayoutPanel: control.BackColor = palette.Panel; control.ForeColor = palette.Text; break;
            case TableLayoutPanel: control.BackColor = palette.Panel; control.ForeColor = palette.Text; break;
            case System.Windows.Forms.Panel: control.BackColor = palette.Panel; control.ForeColor = palette.Text; break;
        }
        foreach (Control child in control.Controls) ApplyThemeRecursive(child, palette);
    }

    private void ApplyInitialSplitterLayout()
    {
        var splitters = PresentationDescendants(this).OfType<SplitContainer>().ToArray();
        if (splitters.Length < 3) return;
        BeginInvoke(() =>
        {
            SetSafeSplitter(splitters[0], Math.Min(285, Math.Max(220, splitters[0].ClientSize.Width / 4)));
            SetSafeSplitter(splitters[1], Math.Max(430, splitters[1].ClientSize.Width - 310));
            SetSafeSplitter(splitters[2], Math.Max(300, splitters[2].ClientSize.Height - 210));
        });
    }

    private static IEnumerable<Control> PresentationDescendants(Control parent)
    {
        foreach (Control child in parent.Controls)
        {
            yield return child;
            foreach (var nested in PresentationDescendants(child)) yield return nested;
        }
    }

    private async Task RunNextWorkflowStepAsync()
    {
        if (_nodes.TryGetValue("Geometry", out var geometry) && geometry.Nodes.Count == 0) { ImportGeometry(); return; }
        if (!_meshGenerated) { GenerateMesh(); return; }
        if (!AllNodes().Any(node => node.Tag is ModelObject { Kind: ObjectKind.Support, State: not ObjectState.Suppressed })) { AddSupport("Fixed Support"); return; }
        if (!AllNodes().Any(node => node.Tag is ModelObject { Kind: ObjectKind.Load, State: not ObjectState.Suppressed })) { AddLoad("Force"); return; }
        if (!AllNodes().Any(node => node.Tag is ModelObject { Kind: ObjectKind.Result })) { AddResult("Equivalent Stress"); return; }
        if (!_solved) { await SolveAsync(); return; }
        EvaluateResults();
    }

    private void ShowWorkflowChecklist()
    {
        RefreshWorkflowChecklist(true);
        _lowerTabs.SelectedTab = _lowerTabs.TabPages.Cast<TabPage>().FirstOrDefault(page => page.Text == "Workflow Checklist");
    }

    private void RefreshWorkflowChecklist(bool force = false)
    {
        if (_nodes.Count == 0) return;
        var rows = GetWorkflowRows();
        var signature = string.Join('|', rows.Select(row => $"{row.Stage}:{row.Status}"));
        if (!force && signature == _lastWorkflowSignature) return;
        _lastWorkflowSignature = signature;
        _workflowChecklist.Rows.Clear();
        foreach (var row in rows)
        {
            var index = _workflowChecklist.Rows.Add(row.Stage, row.Object, row.Status, row.Action);
            _workflowChecklist.Rows[index].Tag = row.Key;
            _workflowChecklist.Rows[index].DefaultCellStyle.ForeColor = row.Complete ? CurrentPalette.Green : CurrentPalette.Warning;
        }
    }

    private IReadOnlyList<WorkflowRow> GetWorkflowRows()
    {
        var geometryReady = _nodes.TryGetValue("Geometry", out var geometry) && geometry.Nodes.Count > 0;
        var materialReady = geometryReady && geometry!.Nodes.Cast<TreeNode>().Any(node => node.Tag is ModelObject model && model.Properties.ContainsKey("Material"));
        var supportReady = AllNodes().Any(node => node.Tag is ModelObject { Kind: ObjectKind.Support, State: not ObjectState.Suppressed });
        var loadReady = AllNodes().Any(node => node.Tag is ModelObject { Kind: ObjectKind.Load, State: not ObjectState.Suppressed });
        var resultReady = AllNodes().Any(node => node.Tag is ModelObject { Kind: ObjectKind.Result });
        return new[]
        {
            Row("1. Decisions", "Analysis system and units", true, "Ready", "Review Project", "Project"),
            Row("2. Preprocessing", "Geometry", geometryReady, geometryReady ? "Imported" : "Required", geometryReady ? "Review geometry" : "Import Geometry", "Geometry"),
            Row("2. Preprocessing", "Material", materialReady, materialReady ? "Assigned" : "Required", materialReady ? "Review material" : "Assign Material", "Materials"),
            Row("2. Preprocessing", "Finite element mesh", _meshGenerated, _meshGenerated ? "Generated" : "Required", _meshGenerated ? "Review quality" : "Generate Mesh", "Mesh"),
            Row("3. Solution", "Support / constraint", supportReady, supportReady ? "Defined" : "Required", supportReady ? "Review supports" : "Insert Fixed Support", "support"),
            Row("3. Solution", "Load", loadReady, loadReady ? "Defined" : "Required", loadReady ? "Review loads" : "Insert Force", "load"),
            Row("4. Postprocessing", "Requested result", resultReady, resultReady ? "Defined" : "Recommended", resultReady ? "Review results" : "Insert Equivalent Stress", "result"),
            Row("4. Postprocessing", "Solved state", _solved, _solved ? "Solved" : "Pending", _solved ? "Evaluate and export" : "Solve", "Solution")
        };
    }

    private static WorkflowRow Row(string stage, string obj, bool complete, string status, string action, string key) =>
        new(stage, obj, complete, status, action, key);

    private void ExecuteChecklistRow(int rowIndex)
    {
        if (rowIndex < 0 || rowIndex >= _workflowChecklist.Rows.Count) return;
        switch (_workflowChecklist.Rows[rowIndex].Tag as string)
        {
            case "Geometry": ImportGeometry(); break;
            case "Materials": AssignMaterial(); break;
            case "Mesh": GenerateMesh(); break;
            case "support": AddSupport("Fixed Support"); break;
            case "load": AddLoad("Force"); break;
            case "result": AddResult("Equivalent Stress"); break;
            case "Solution": _ = SolveAsync(); break;
            case string key: SelectNode(key); break;
        }
    }

    private sealed record WorkflowRow(string Stage, string Object, bool Complete, string Status, string Action, string Key);

    private readonly record struct ThemePalette(
        Color Background,
        Color Panel,
        Color SecondaryPanel,
        Color Field,
        Color Chrome,
        Color Border,
        Color Text,
        Color Muted,
        Color Button,
        Color Selection,
        Color Accent,
        Color AccentBorder,
        Color Green,
        Color Warning)
    {
        public static ThemePalette Light => new(
            Color.FromArgb(242,245,249), Color.White, Color.FromArgb(235,240,246),
            Color.FromArgb(252,253,255), Color.FromArgb(247,249,252), Color.FromArgb(188,198,210),
            Color.FromArgb(33,42,52), Color.FromArgb(86,99,114), Color.FromArgb(240,244,249),
            Color.FromArgb(205,228,249), Color.FromArgb(0,114,198), Color.FromArgb(0,87,153),
            Color.FromArgb(34,139,85), Color.FromArgb(190,112,0));

        public static ThemePalette Dark => new(
            Color.FromArgb(27,30,35), Color.FromArgb(39,43,50), Color.FromArgb(49,54,63),
            Color.FromArgb(24,27,32), Color.FromArgb(20,22,26), Color.FromArgb(72,79,90),
            Color.FromArgb(235,238,242), Color.FromArgb(164,174,187), Color.FromArgb(49,54,63),
            Color.FromArgb(58,90,130), Color.FromArgb(38,143,255), Color.FromArgb(75,177,255),
            Color.FromArgb(74,200,126), Color.FromArgb(245,187,70));
    }

    private sealed class ThemeRenderer(ThemePalette palette) : ToolStripProfessionalRenderer(new ThemeColorTable(palette))
    {
        protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
        {
            e.TextColor = e.Item.Enabled ? palette.Text : palette.Muted;
            base.OnRenderItemText(e);
        }
    }

    private sealed class ThemeColorTable(ThemePalette palette) : ProfessionalColorTable
    {
        public override Color MenuStripGradientBegin => palette.Chrome;
        public override Color MenuStripGradientEnd => palette.Chrome;
        public override Color ToolStripGradientBegin => palette.SecondaryPanel;
        public override Color ToolStripGradientMiddle => palette.SecondaryPanel;
        public override Color ToolStripGradientEnd => palette.SecondaryPanel;
        public override Color ToolStripDropDownBackground => palette.Panel;
        public override Color ImageMarginGradientBegin => palette.SecondaryPanel;
        public override Color ImageMarginGradientMiddle => palette.SecondaryPanel;
        public override Color ImageMarginGradientEnd => palette.SecondaryPanel;
        public override Color MenuItemSelected => palette.Selection;
        public override Color MenuItemBorder => palette.Accent;
        public override Color MenuBorder => palette.Border;
        public override Color ButtonSelectedHighlight => palette.Selection;
        public override Color ButtonSelectedBorder => palette.Accent;
        public override Color SeparatorDark => palette.Border;
        public override Color SeparatorLight => palette.Panel;
    }
}
